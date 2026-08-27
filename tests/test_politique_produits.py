import unittest

from scanners.politique import est_op17, produit_autorise


class PolitiqueProduitsTests(unittest.TestCase):
    def test_sealed_product_is_allowed(self):
        self.assertTrue(
            produit_autorise(
                "One Piece Card Game OP17 Display 24 boosters VF"
            )
        )

    def test_single_cards_and_asian_languages_are_rejected(self):
        self.assertFalse(
            produit_autorise("Carte Ã  l'unitÃ© OP17-001")
        )
        self.assertFalse(
            produit_autorise("OP17 Booster Box Japanese")
        )

    def test_accessory_needs_an_explicit_promo_card(self):
        self.assertFalse(
            produit_autorise("One Piece OP17 Tapis de jeu")
        )
        self.assertTrue(
            produit_autorise(
                "One Piece OP17 Tapis de jeu avec carte promo exclusive"
            )
        )

    def test_op17_variants_are_recognized(self):
        for valeur in ("OP17", "OP-17", "OP 17", "op-17 display"):
            with self.subTest(valeur=valeur):
                self.assertTrue(est_op17(valeur))


if __name__ == "__main__":
    unittest.main()
