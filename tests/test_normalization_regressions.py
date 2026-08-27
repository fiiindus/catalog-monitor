import unittest

from comparateur import detect_language
from scanners import figurines_goodies


class LanguageNormalizationTests(unittest.TestCase):
    def test_french_phrase_is_not_misread_as_english_code(self):
        self.assertEqual(
            "VF",
            detect_language("One Piece OP17 Display - En Français"),
        )

    def test_common_language_labels_are_detected(self):
        cases = {
            "One Piece Display VF": "VF",
            "One Piece Display French": "VF",
            "One Piece Display English": "EN",
            "One Piece Display EN": "EN",
            "One Piece Display Japanese": "JP",
            "One Piece Display JP": "JP",
        }

        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(expected, detect_language(name))


class FigurinesGoodiesEncodingTests(unittest.TestCase):
    def test_accented_preorder_is_detected(self):
        html = """
        <div>
          <a href="/produit-op17.html">
            ONE PIECE BOOSTER DISPLAY OP-17 VF
          </a>
          <span>PRÉCOMMANDE</span>
          <span>149,90 €</span>
        </div>
        """
        products = {}

        figurines_goodies.extraire_page(html, products)

        self.assertEqual(1, len(products))
        product = next(iter(products.values()))
        self.assertEqual("PREORDER", product["status"])


if __name__ == "__main__":
    unittest.main()
