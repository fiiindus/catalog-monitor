import types
import unittest
from unittest.mock import Mock

from confirmation import (
    confirmer_transitions,
    confirmer_url,
    extraire_statut_structure,
)


LIEN = "https://example.com/product"


def produit(status):
    return {
        "name": "Produit",
        "link": LIEN,
        "status": status,
        "priority": 3,
    }


class ConfirmationTests(unittest.TestCase):
    def test_extracts_schema_org_availability(self):
        html = """
        <script type="application/ld+json">
        {"@type":"Product","offers":{"availability":"https://schema.org/InStock"}}
        </script>
        """
        self.assertEqual("AVAILABLE", extraire_statut_structure(html))

    def test_generic_confirmation_uses_only_product_url(self):
        response = Mock()
        response.text = (
            '<meta itemprop="availability" '
            'content="https://schema.org/OutOfStock">'
        )
        get = Mock(return_value=response)

        self.assertEqual("SOLD OUT", confirmer_url(produit("AVAILABLE"), get))
        get.assert_called_once()
        response.raise_for_status.assert_called_once()

    def test_conclusive_detail_page_rejects_false_restock(self):
        module = types.SimpleNamespace(
            confirmer_disponibilite=lambda item: "SOLD OUT"
        )
        nouveau = {"Boutique": {LIEN: produit("AVAILABLE")}}
        ancien = {"Boutique": {LIEN: produit("SOLD OUT")}}

        confirmer_transitions(
            [{"nom": "Boutique", "scanner": "test"}],
            ancien,
            nouveau,
            importer=lambda nom: module,
        )

        self.assertEqual("SOLD OUT", nouveau["Boutique"][LIEN]["status"])

    def test_unchanged_available_product_is_not_requested_again(self):
        confirmer = Mock(return_value="AVAILABLE")
        module = types.SimpleNamespace(confirmer_disponibilite=confirmer)
        nouveau = {"Boutique": {LIEN: produit("AVAILABLE")}}
        ancien = {"Boutique": {LIEN: produit("AVAILABLE")}}

        confirmer_transitions(
            [{"nom": "Boutique", "scanner": "test"}],
            ancien,
            nouveau,
            importer=lambda nom: module,
        )

        confirmer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
