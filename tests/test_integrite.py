import json
import unittest
from unittest.mock import mock_open, patch

from integrite import (
    ChuteCatalogueSuspecte,
    RecoupementCatalogueSuspect,
    charger_stock_precedent,
    normaliser_identite_lien,
    valider_scan,
)


def produit(numero):
    lien = f"https://example.com/{numero}"
    return lien, {
        "name": f"Produit {numero}",
        "link": lien,
        "status": "SOLD OUT",
    }


class IntegrityTests(unittest.TestCase):
    def test_empty_link_has_no_catalogue_identity(self):
        self.assertEqual("", normaliser_identite_lien(""))

    def test_rejects_empty_catalogue_by_default(self):
        with self.assertRaisesRegex(RuntimeError, "catalogue vide"):
            valider_scan({"nom": "Boutique"}, {}, {})

    def test_allows_explicitly_empty_catalogue(self):
        self.assertEqual(
            {},
            valider_scan(
                {"nom": "Précommandes", "allow_empty": True},
                {},
                {},
            ),
        )

    def test_rejects_abnormal_count_drop(self):
        ancien = dict(produit(i) for i in range(100))
        nouveau = dict(produit(i) for i in range(20))

        with self.assertRaisesRegex(RuntimeError, "seuil de sécurité"):
            valider_scan(
                {"nom": "Boutique", "minimum_count_ratio": 0.5},
                nouveau,
                {"Boutique": ancien},
            )

    def test_malformed_reduced_catalogue_is_rejected_before_drop_quarantine(self):
        ancien = dict(produit(i) for i in range(100))
        nouveau = dict(produit(i) for i in range(20))
        nouveau["https://example.com/0"]["status"] = "BROKEN"

        with self.assertRaisesRegex(RuntimeError, "statut inconnu") as contexte:
            valider_scan(
                {"nom": "Boutique"},
                nouveau,
                {"Boutique": ancien},
            )

        self.assertNotIsInstance(contexte.exception, ChuteCatalogueSuspecte)

    def test_default_threshold_is_stricter_than_before(self):
        ancien = dict(produit(i) for i in range(100))
        nouveau = dict(produit(i) for i in range(60))

        with self.assertRaises(ChuteCatalogueSuspecte) as contexte:
            valider_scan(
                {"nom": "Boutique"},
                nouveau,
                {"Boutique": ancien},
            )

        self.assertEqual(100, contexte.exception.precedent)
        self.assertEqual(60, contexte.exception.courant)
        self.assertIs(nouveau, contexte.exception.produits)

    def test_accepts_normal_count_variation_with_explicit_ratio(self):
        ancien = dict(produit(i) for i in range(100))
        nouveau = dict(produit(i) for i in range(60))

        self.assertIs(
            nouveau,
            valider_scan(
                {"nom": "Boutique", "minimum_count_ratio": 0.5},
                nouveau,
                {"Boutique": ancien},
            ),
        )

    def test_rejects_same_size_catalogue_with_unrelated_products(self):
        ancien = dict(produit(i) for i in range(20))
        nouveau = dict(produit(i) for i in range(100, 120))

        with self.assertRaises(RecoupementCatalogueSuspect):
            valider_scan(
                {"nom": "Boutique"},
                nouveau,
                {"Boutique": ancien},
            )

    def test_accepts_catalogue_with_strong_reference_overlap(self):
        ancien = dict(produit(i) for i in range(20))
        nouveau = dict(produit(i) for i in range(2, 22))

        self.assertIs(
            nouveau,
            valider_scan(
                {"nom": "Boutique"},
                nouveau,
                {"Boutique": ancien},
            ),
        )

    def test_rejects_premium_bandai_partial_catalogue(self):
        ancien = dict(produit(i) for i in range(52))
        nouveau = dict(produit(i) for i in range(43))

        with self.assertRaisesRegex(RuntimeError, "seuil de sécurité"):
            valider_scan(
                {
                    "nom": "Premium Bandai US",
                    "minimum_count_ratio": 0.85,
                },
                nouveau,
                {"Premium Bandai US": ancien},
            )

    def test_accepts_premium_bandai_small_variation(self):
        ancien = dict(produit(i) for i in range(52))
        nouveau = dict(produit(i) for i in range(48))

        self.assertIs(
            nouveau,
            valider_scan(
                {
                    "nom": "Premium Bandai US",
                    "minimum_count_ratio": 0.85,
                },
                nouveau,
                {"Premium Bandai US": ancien},
            ),
        )

    def test_rejects_incoherent_link(self):
        with self.assertRaisesRegex(RuntimeError, "lien incohérent"):
            valider_scan(
                {"nom": "Boutique"},
                {
                    "https://example.com/key": {
                        "name": "Produit",
                        "link": "https://example.com/other",
                        "status": "AVAILABLE",
                    }
                },
                {},
            )

    def test_rejects_a_catalogue_with_too_many_unknown_statuses(self):
        produits = dict(produit(i) for i in range(10))
        produits["https://example.com/0"]["status"] = "UNKNOWN"
        produits["https://example.com/1"]["status"] = "UNKNOWN"

        with self.assertRaisesRegex(RuntimeError, "trop de statuts UNKNOWN"):
            valider_scan({"nom": "Boutique"}, produits, {})

    def test_quarantines_even_one_ambiguous_status_by_default(self):
        produits = dict(produit(i) for i in range(20))
        produits["https://example.com/0"]["status"] = "UNKNOWN"

        with self.assertRaisesRegex(RuntimeError, "trop de statuts UNKNOWN"):
            valider_scan({"nom": "Boutique"}, produits, {})

    def test_unknown_status_tolerance_requires_explicit_configuration(self):
        produits = dict(produit(i) for i in range(20))
        produits["https://example.com/0"]["status"] = "UNKNOWN"

        self.assertIs(
            produits,
            valider_scan(
                {"nom": "Boutique", "maximum_unknown_ratio": 0.05},
                produits,
                {},
            ),
        )

    def test_loads_and_validates_previous_stock(self):
        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps({"Boutique": {}})),
        ):
            self.assertEqual(
                {"Boutique": {}},
                charger_stock_precedent("stock.json"),
            )


if __name__ == "__main__":
    unittest.main()
