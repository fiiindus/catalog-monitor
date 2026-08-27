import json
import os
import tempfile
import unittest
from pathlib import Path

from cible import CIBLE_PRIORITAIRE
from comparateur import comparer, enrichir_produit


LIEN = "https://example.com/produit-test"
LIEN_CIBLE = "https://example.com/priority-target"


def creer_produit(
    status,
    name="ONE PIECE CARD GAME Booster Box",
    availability="",
    notify_when_referenced=False,
):
    return {
        "site": "Boutique Test",
        "name": name,
        "price": "10,00 €",
        "status": status,
        "availability": availability,
        "language": "VF",
        "notify_when_referenced": notify_when_referenced,
        "link": LIEN_CIBLE if CIBLE_PRIORITAIRE in name else LIEN,
        "image": "",
    }


class ComparatorTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.old_cwd = Path.cwd()
        os.chdir(self.tempdir.name)
        self.addCleanup(os.chdir, self.old_cwd)

        self.config = {
            "priority_set": CIBLE_PRIORITAIRE,
            "priority": {
                "categories": {"DISPLAY": 5, "DOUBLE_PACK": 3},
                "languages": {"EN": 3, "VF": 1, "OTHER": -1},
            },
        }
        Path("config.json").write_text(
            json.dumps(self.config),
            encoding="utf-8",
        )
        Path("ancien_stock.json").write_text("{}", encoding="utf-8")

    def test_initial_store_is_silent_for_already_available_product(self):
        stock = {"Boutique Test": {LIEN: creer_produit("AVAILABLE")}}
        self.assertEqual([], comparer(stock))

    def test_priority_target_is_reported_even_when_sold_out(self):
        stock = {
            "Boutique Test": {
                LIEN_CIBLE: creer_produit(
                    "SOLD OUT",
                    f"{CIBLE_PRIORITAIRE} - Boite de 24 Boosters",
                )
            }
        }
        alertes = comparer(stock)
        self.assertEqual(1, len(alertes))
        self.assertEqual("NOUVEAU PRODUIT RÉFÉRENCÉ", alertes[0]["type_alerte"])
        self.assertEqual(CIBLE_PRIORITAIRE, alertes[0]["priority_target"])

    def test_restock_is_reported(self):
        Path("ancien_stock.json").write_text(
            json.dumps(
                {"Boutique Test": {LIEN: creer_produit("SOLD OUT")}},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        stock = {"Boutique Test": {LIEN: creer_produit("AVAILABLE")}}
        alertes = comparer(stock)
        self.assertEqual("RETOUR EN STOCK", alertes[0]["type_alerte"])

    def test_availability_date_change_is_reported(self):
        Path("ancien_stock.json").write_text(
            json.dumps(
                {
                    "Boutique Test": {
                        LIEN_CIBLE: creer_produit(
                            "COMING_SOON",
                            f"{CIBLE_PRIORITAIRE} - Boite de 24 Boosters",
                            "Aout",
                        )
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        stock = {
            "Boutique Test": {
                LIEN_CIBLE: creer_produit(
                    "COMING_SOON",
                    f"{CIBLE_PRIORITAIRE} - Boite de 24 Boosters",
                    "Septembre",
                )
            }
        }
        alertes = comparer(stock)
        self.assertEqual(
            "DATE DE DISPONIBILITÉ MISE À JOUR",
            alertes[0]["type_alerte"],
        )

    def test_priority_target_bonus_preserves_category_order(self):
        cible_display = enrichir_produit(
            creer_produit(
                "COMING_SOON",
                f"{CIBLE_PRIORITAIRE} - Boite de 24 Boosters",
            ),
            self.config,
        )
        cible_double_pack = enrichir_produit(
            creer_produit(
                "COMING_SOON",
                f"{CIBLE_PRIORITAIRE} - Booster Double Pack",
            ),
            self.config,
        )
        autre_cible = "OP01" if CIBLE_PRIORITAIRE != "OP01" else "OP02"
        autre_display = enrichir_produit(
            {
                **creer_produit(
                    "AVAILABLE",
                    f"{autre_cible} - Boite de 24 Boosters",
                ),
                "language": "EN",
            },
            self.config,
        )

        self.assertGreater(cible_display["priority"], cible_double_pack["priority"])
        self.assertGreater(cible_double_pack["priority"], autre_display["priority"])


if __name__ == "__main__":
    unittest.main()
