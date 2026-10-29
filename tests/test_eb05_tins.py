from datetime import date
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup

from integrite import valider_scan
from notifier import construire_embed
from scanners import parkage, ultrajeux


FIXTURES = Path(__file__).parent / "fixtures"


class UltraJeuxReleaseTests(unittest.TestCase):
    def test_orderable_release_is_preorder_then_available_on_release_day(self):
        for today, expected in (
            (date(2026, 10, 29), "PREORDER"),
            (date(2026, 10, 30), "AVAILABLE"),
            (date(2026, 10, 31), "AVAILABLE"),
        ):
            with self.subTest(today=today):
                self.assertEqual(expected, ultrajeux.detect_status(
                    "Sortie le 30/10/2026", orderable=True, today=today,
                ))

    def test_release_date_alone_does_not_claim_product_is_orderable(self):
        self.assertEqual("COMING_SOON", ultrajeux.detect_status(
            "Sortie le 30/10/2026",
        ))

    def test_stock_restrictions_take_precedence_over_order_button(self):
        for text, expected in (
            ("Indisponible Sortie le 30/10/2026", "SOLD OUT"),
            ("Disponible en magasin Sortie le 30/10/2026", "STORE_ONLY"),
        ):
            self.assertEqual(expected, ultrajeux.detect_status(text, orderable=True))

    def test_disabled_or_unrelated_buttons_are_not_order_controls(self):
        for control in (
            '<input type="submit" value="Ajouter" disabled>',
            '<button aria-disabled="true">Ajouter</button>',
            '<button>Prévenez-moi</button>',
        ):
            html = '<form><input name="op" value="danspanier">' + control + '</form>'
            self.assertFalse(ultrajeux.can_order(BeautifulSoup(html, "lxml")))
        self.assertFalse(ultrajeux.can_order(BeautifulSoup(
            '<button>Ajouter</button>', "lxml",
        )))

    def test_real_eb05_and_tin_listing_passes_scan_validation(self):
        html = (FIXTURES / "ultrajeux_eb05_tins.html").read_text()
        playwright = MagicMock()
        page = playwright.chromium.launch.return_value.new_page.return_value
        page.content.return_value = html
        with patch.object(ultrajeux, "sync_playwright") as factory:
            factory.return_value.__enter__.return_value = playwright
            products = ultrajeux.scan()
        self.assertEqual(8, len(products))
        self.assertEqual(6, sum("TS03" in p["name"] for p in products.values()))
        self.assertTrue(all(p["status"] in {"PREORDER", "AVAILABLE"}
                            for p in products.values()))
        for product in products.values():
            self.assertIn("static.ultrajeux.com/images/produits/", product["image"])
            self.assertEqual(
                {"url": product["image"]},
                construire_embed(product)["thumbnail"],
            )
        self.assertIs(products, valider_scan({"nom": "UltraJeux"}, products, {}))

    def test_photo_is_preferred_over_flag_even_inside_product_link(self):
        soup = BeautifulSoup('''<div><a><img src="/images/pays/fr.png"></a>
            <p class="image"><img class="produit_scan" src="/placeholder.gif"
                data-src="/images/produits/normal/33535.jpg"></p></div>''', "lxml")
        self.assertEqual(
            "https://www.ultrajeux.com/images/produits/normal/33535.jpg",
            ultrajeux.extract_image(soup.find("a"), soup),
        )

    def test_flags_and_badges_are_not_used_when_photo_is_missing(self):
        soup = BeautifulSoup('''<div><a><img src="/images/pays/fr.png"></a>
            <img src="/images/icon_new_orange.png"></div>''', "lxml")
        self.assertEqual("", ultrajeux.extract_image(soup.find("a"), soup))

    def test_tin_code_variants_and_language_filters(self):
        for name in ("TS03 Tin Pack : Luffy", "TS-03 : Hancock", "TS 03 : Shanks"):
            self.assertTrue(ultrajeux.is_tcg_product(name))
        self.assertFalse(ultrajeux.is_tcg_product("TS03 Tin Pack Japanese"))
        self.assertFalse(ultrajeux.is_tcg_product("Carte à l'unité TS03-001"))


class ParkagePreorderCardTests(unittest.TestCase):
    def test_preorder_without_shop_stock_is_extracted_by_full_scanner(self):
        name = "One Piece Card Game Tin Pack Set - TS-03 : Vol.3 (Random Type)"
        path = "/fr/1144380-one-piece-card-game-tin-pack-set-ts-03-vol-3-random-type"
        # Parkage hides its shop-stock selector for preorders (isPreorder=true).
        html = f'''<article><a href="{path}">{name}</a>
            <a>Anglais</a><a>Type de Produit: Packs &amp; Produits spéciaux</a>
            <span>22,90 €</span><button>Précommander</button></article>'''
        soup = BeautifulSoup(html, "lxml")
        card = parkage.trouver_carte_produit(soup.find("a"))
        self.assertIsNotNone(card)
        self.assertEqual("PREORDER", parkage.detecter_statut(card.get_text(" ")))
        playwright = MagicMock()
        page = playwright.chromium.launch.return_value.new_page.return_value
        page.content.side_effect = ["", html, ""]
        with patch.object(parkage, "sync_playwright") as factory:
            factory.return_value.__enter__.return_value = playwright
            products = parkage.scan()
        product = products[parkage.BASE_URL + path]
        self.assertEqual("PREORDER", product["status"])
        self.assertEqual("EN", product["language"])
        self.assertEqual("22,90 €", product["price"])
        self.assertIs(products, valider_scan({"nom": "Parkage"}, products, {}))


if __name__ == "__main__":
    unittest.main()
