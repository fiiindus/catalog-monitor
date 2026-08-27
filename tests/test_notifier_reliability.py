import os
import sys
import types
import unittest
from unittest.mock import Mock, patch

try:
    import requests
except ModuleNotFoundError:
    requests = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    requests.RequestException = RequestException
    requests.ConnectionError = RequestException
    requests.JSONDecodeError = ValueError
    requests.post = Mock()
    sys.modules["requests"] = requests

import notifier


class NotifierReliabilityTests(unittest.TestCase):
    def test_missing_webhook_is_fatal_when_alerts_exist(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DISCORD_WEBHOOK manquant"):
                notifier.send_discord([{"name": "OP17"}])

    @patch("notifier.time.sleep")
    @patch("notifier.requests.post")
    def test_rate_limit_is_retried(self, post, sleep):
        limite = Mock(status_code=429, headers={})
        limite.json.return_value = {"retry_after": 0.25}
        succes = Mock(status_code=204, headers={})
        post.side_effect = [limite, succes]

        notifier.envoyer_payload_discord(
            "https://discord.example/webhook",
            {"embeds": []},
        )

        self.assertEqual(2, post.call_count)
        sleep.assert_called_once_with(0.25)

    @patch("notifier.time.sleep")
    @patch("notifier.requests.post")
    def test_server_failure_is_fatal_after_retries(self, post, sleep):
        post.side_effect = notifier.requests.ConnectionError("offline")

        with self.assertRaisesRegex(RuntimeError, "plusieurs essais"):
            notifier.envoyer_payload_discord(
                "https://discord.example/webhook",
                {"embeds": []},
            )

        self.assertEqual(notifier.MAX_DISCORD_ATTEMPTS, post.call_count)
        self.assertEqual(notifier.MAX_DISCORD_ATTEMPTS - 1, sleep.call_count)

    @patch("notifier.requests.post")
    def test_non_retryable_error_is_immediately_fatal(self, post):
        post.return_value = Mock(status_code=400, headers={}, text="bad")

        with self.assertRaisesRegex(RuntimeError, "statut 400"):
            notifier.envoyer_payload_discord(
                "https://discord.example/webhook",
                {"embeds": []},
            )

        post.assert_called_once()

    def test_embed_urls_and_lengths_are_sanitized(self):
        embed = notifier.construire_embed(
            {
                "name": "x" * 400,
                "link": "javascript:alert(1)",
                "image": "not-a-url",
            }
        )

        self.assertEqual(256, len(embed["title"]))
        self.assertNotIn("url", embed)
        self.assertNotIn("thumbnail", embed)


if __name__ == "__main__":
    unittest.main()
