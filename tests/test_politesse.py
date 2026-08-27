import os
import unittest
from unittest.mock import patch

from scanners.politesse import temporiser_demarrage


class PolitesseTests(unittest.TestCase):
    @patch("scanners.politesse.time.sleep")
    @patch("scanners.politesse._RANDOM.uniform", return_value=3.25)
    def test_start_jitter_delays_without_network_call(
        self,
        random_uniform,
        sleep,
    ):
        attente = temporiser_demarrage("Boutique")

        self.assertEqual(3.25, attente)
        random_uniform.assert_called_once_with(0.75, 8.0)
        sleep.assert_called_once_with(3.25)

    @patch("scanners.politesse.time.sleep")
    def test_start_jitter_can_be_disabled_for_diagnostics(self, sleep):
        with patch.dict(
            os.environ,
            {"TRACKER_DISABLE_START_JITTER": "1"},
        ):
            self.assertEqual(0.0, temporiser_demarrage("Boutique"))

        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
