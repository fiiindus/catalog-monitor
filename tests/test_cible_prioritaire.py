import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cible import charger_cible_prioritaire, est_cible_prioritaire


class PriorityTargetTests(unittest.TestCase):
    def test_loads_and_normalizes_configured_target(self):
        with tempfile.TemporaryDirectory() as repertoire:
            chemin = Path(repertoire) / "config.json"
            chemin.write_text(
                json.dumps({"priority_set": "op-18"}),
                encoding="utf-8",
            )
            self.assertEqual("OP18", charger_cible_prioritaire(str(chemin)))

    def test_target_detection_accepts_hyphen_and_spacing(self):
        self.assertTrue(est_cible_prioritaire("Display OP-18 anglais", "OP18"))
        self.assertTrue(est_cible_prioritaire("Display OP 18 VF", "OP18"))
        self.assertFalse(est_cible_prioritaire("Display OP17 VF", "OP18"))

    def test_invalid_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as repertoire:
            chemin = Path(repertoire) / "config.json"
            chemin.write_text(
                json.dumps({"priority_set": "whatever"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "Cible prioritaire invalide"):
                charger_cible_prioritaire(str(chemin))

    def test_priority_can_be_disabled_explicitly_or_by_omission(self):
        with tempfile.TemporaryDirectory() as repertoire:
            chemin = Path(repertoire) / "config.json"
            for config in ({"priority_set": None}, {}):
                chemin.write_text(json.dumps(config), encoding="utf-8")
                self.assertIsNone(charger_cible_prioritaire(chemin))

    def test_disabled_target_does_not_match_an_extension(self):
        with patch("cible.CIBLE_PRIORITAIRE", None):
            self.assertFalse(est_cible_prioritaire("Display OP17 VF"))
            self.assertTrue(est_cible_prioritaire("Display OP17 VF", "OP17"))


if __name__ == "__main__":
    unittest.main()
