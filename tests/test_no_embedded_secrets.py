import unittest
from pathlib import Path


class EmbeddedSecretTests(unittest.TestCase):
    def test_no_discord_webhook_is_embedded_in_source(self):
        repository = Path(__file__).resolve().parents[1]
        signature = "discord.com/api/" + "webhooks/"
        offenders = []

        for suffix in ("*.py", "*.yml", "*.yaml", "*.json"):
            for path in repository.rglob(suffix):
                if path.resolve() == Path(__file__).resolve():
                    continue
                if signature in path.read_text(encoding="utf-8"):
                    offenders.append(str(path.relative_to(repository)))

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
