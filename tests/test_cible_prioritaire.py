import json
import tempfile
import unittest
from pathlib import Path

from cible import CIBLE_PRIORITAIRE, charger_cible_prioritaire, est_cible_prioritaire
from scanners import carte_one_piece, figurines_goodies, oupi, parkage, playin


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

    def test_priority_search_urls_use_configured_target(self):
        self.assertIn(CIBLE_PRIORITAIRE, figurines_goodies.PRIORITY_SEARCH_URL)
        self.assertIn(CIBLE_PRIORITAIRE, parkage.PRIORITY_SEARCH_URL)
        self.assertIn(CIBLE_PRIORITAIRE, oupi.PRIORITY_SEARCH_URL)
        self.assertIn(CIBLE_PRIORITAIRE, carte_one_piece.PRIORITY_SEARCH_URL)
        self.assertTrue(playin.est_op17(f"Display {CIBLE_PRIORITAIRE} VF"))


if __name__ == "__main__":
    unittest.main()
