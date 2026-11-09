import json
import unittest
from unittest.mock import Mock, mock_open, patch

from comparateur import comparer
from notifier import construire_embed
from scanners import parkage_cartes as parkage


def fiche(rarete, traitements=(), identifiant=1147754):
    return {
        "id": identifiant,
        "name": "EB03-001 Nefertari Vivi",
        "lang": "fr",
        "price": 59.90,
        "canSelling": True,
        "isStock": True,
        "isPreorder": False,
        "isPreorderWithStock": False,
        "image_url_1": "products/eb05/eb03-001b.jpg",
        "state_fr": "Near mint",
        "taxonomies": [
            {"name": "product_type_id", "values": [{"id": parkage.CARTE_A_L_UNITE}]},
            {"name": "rarity_id", "values": [{"id": rarete}]},
            {"name": "treatment_id", "values": [
                {"id": code, "name_fr": nom} for code, nom in traitements
            ]},
            {"name": "set_id", "values": [{"abreviation": "EB05"}]},
        ],
    }


class ParkageCartesTests(unittest.TestCase):
    def test_filters_all_three_rarities_by_treatment(self):
        alt = (parkage.ALTERNATIVE_ART, "Alternative Art")
        manga = (98765, "Manga Rare")
        reprint = (12906, "Réimpression")
        cases = (
            (parkage.LEADER, (alt, reprint), True),
            (parkage.LEADER, (reprint,), False),
            (parkage.SECRET_RARE, (), True),
            (parkage.SUPER_RARE, (), True),
            (parkage.SUPER_RARE, (reprint,), True),
            (parkage.SECRET_RARE, (alt,), False),
            (parkage.SUPER_RARE, (alt,), False),
            (parkage.SECRET_RARE, (manga,), False),
            (parkage.SUPER_RARE, (manga,), False),
            (42, (alt,), False),
        )
        for rarete, traitements, attendu in cases:
            with self.subTest(rarete=rarete, traitements=traitements):
                self.assertEqual(attendu, bool(parkage.extraire_carte(fiche(rarete, traitements))))

    def test_initial_catalogue_is_silent_then_a_new_card_has_a_photo(self):
        carte = parkage.extraire_carte(fiche(
            parkage.LEADER, ((parkage.ALTERNATIVE_ART, "Alternative Art"),)
        ))
        stock = {parkage.BOUTIQUE: {carte["link"]: carte}}
        config = {"priority": {"languages": {"VF": 1}}}
        with patch("comparateur.charger_config", return_value=config):
            with patch("comparateur.open", mock_open(read_data="{}")):
                self.assertEqual([], comparer(stock))
            precedent = json.dumps({parkage.BOUTIQUE: {}})
            with patch("comparateur.open", mock_open(read_data=precedent)):
                alertes = comparer(stock)

        self.assertEqual(1, len(alertes))
        self.assertEqual("NOUVEAU PRODUIT DISPONIBLE", alertes[0]["type_alerte"])
        embed = construire_embed(alertes[0])
        self.assertIn("Leader alternatif · EB05 · Near mint", embed["description"])
        self.assertEqual({"url": parkage.IMAGE_URL + "products/eb05/eb03-001b.jpg"},
                         embed["thumbnail"])

    def test_store_only_stock_does_not_trigger_an_alert(self):
        carte = fiche(parkage.SUPER_RARE)
        carte["canSelling"] = False
        self.assertIsNone(parkage.extraire_carte(carte))

    def test_does_not_accept_duplicated_pages_as_a_complete_catalogue(self):
        session = Mock()
        reponse = session.get.return_value
        reponse.json.return_value = {
            "type": "success", "data": {"count": 2, "list": [fiche(parkage.LEADER)]},
        }
        with patch.object(parkage, "PAGE_SIZE", 1):
            with self.assertRaisesRegex(RuntimeError, "dupliqué"):
                list(parkage.lire_recherche(session, {"rarity_id": parkage.LEADER}))


if __name__ == "__main__":
    unittest.main()
