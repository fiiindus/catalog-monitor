import unittest
from unittest.mock import patch

import observabilite


def produit(lien, status):
    return {
        "name": lien,
        "link": lien,
        "status": status,
    }


class ObservabiliteTests(unittest.TestCase):
    def test_counts_requests_and_catalogue_evolution(self):
        observabilite.commencer_mesure()
        observabilite.noter_requete()
        observabilite.noter_requete(2)
        mesure = observabilite.lire_mesure()

        self.assertEqual(3, mesure["requests"])

        ancien = {
            "https://example.com/a": produit(
                "https://example.com/a",
                "SOLD OUT",
            ),
            "https://example.com/b": produit(
                "https://example.com/b",
                "AVAILABLE",
            ),
        }
        nouveau = {
            "https://example.com/a": produit(
                "https://example.com/a",
                "AVAILABLE",
            ),
            "https://example.com/c": produit(
                "https://example.com/c",
                "SOLD OUT",
            ),
        }

        self.assertEqual(
            {"added": 1, "removed": 1, "status_changes": 1},
            observabilite.calculer_evolution(ancien, nouveau),
        )

    @patch("builtins.print")
    def test_success_log_contains_status_distribution(self, print_mock):
        observabilite.commencer_mesure()
        produits = {
            "https://example.com/a": produit(
                "https://example.com/a",
                "AVAILABLE",
            ),
            "https://example.com/b": produit(
                "https://example.com/b",
                "SOLD OUT",
            ),
        }

        observabilite.journaliser_reussite("Boutique", produits, {})

        message = print_mock.call_args.args[0]
        self.assertIn("AVAILABLE:1", message)
        self.assertIn("SOLD OUT:1", message)
        self.assertIn("pages/requêtes=0", message)


if __name__ == "__main__":
    unittest.main()
