import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import notifier
from comparateur import alerte_disponibilite_autorisee, comparer
from deduplication import filtrer_alertes, mettre_a_jour_etat
from scanners import premium_bandai


class PremiumBandaiNotificationTests(unittest.TestCase):
    def test_closed_preorders_are_not_orderable(self):
        status = premium_bandai.detecter_statut("PRE-ORDER CLOSED")

        self.assertEqual("SOLD OUT", status)
        self.assertFalse(premium_bandai.est_commandable(status))

    def test_open_preorders_are_orderable(self):
        status = premium_bandai.detecter_statut("PRE-ORDERS OPEN")

        self.assertEqual("PREORDER", status)
        self.assertTrue(premium_bandai.est_commandable(status))

    def test_available_wording_is_orderable(self):
        for wording in (
            "IN STOCK",
            "ADD TO CART",
            "BUY NOW",
            "AVAILABLE NOW",
        ):
            with self.subTest(wording=wording):
                status = premium_bandai.detecter_statut(wording)
                self.assertEqual("AVAILABLE", status)
                self.assertTrue(premium_bandai.est_commandable(status))

    def test_detail_page_prefers_purchase_button_status(self):
        html = """
        <main>
          <h1>ONE PIECE CARD GAME Premium Card Collection</h1>
          <button>SORRY, OUT OF STOCK</button>
        </main>
        """
        self.assertEqual(
            "SOLD OUT",
            premium_bandai.detecter_statut_detail(html),
        )

    def test_comparator_blocks_non_orderable_premium_bandai_items(self):
        self.assertFalse(
            alerte_disponibilite_autorisee(
                {
                    "site": "Premium Bandai US",
                    "status": "PREORDER",
                    "orderable": False,
                }
            )
        )
        self.assertTrue(
            alerte_disponibilite_autorisee(
                {
                    "site": "Premium Bandai US",
                    "status": "PREORDER",
                    "orderable": True,
                }
            )
        )

    def test_all_card_game_references_are_monitored(self):
        self.assertTrue(
            premium_bandai.produit_surveille(
                "ONE PIECE CARD GAME Official Playmat Limited Edition vol.6"
            )
        )

    def test_ace_sabo_luffy_collection_is_monitored(self):
        self.assertTrue(
            premium_bandai.produit_surveille(
                "ONE PIECE CARD GAME Premium Card Collection -Ace & Sabo & Luffy-"
            )
        )

    def test_chinese_anniversary_set_is_monitored_on_premium_bandai(self):
        self.assertTrue(
            premium_bandai.produit_surveille(
                "ONE PIECE CARD GAME Chinese 3rd Anniversary Set"
            )
        )

    def test_single_chinese_card_is_monitored(self):
        self.assertTrue(
            premium_bandai.produit_surveille(
                "ONE PIECE CARD GAME Chinese Single Card OP17-001"
            )
        )

    def test_first_catalogue_page_waits_for_products(self):
        page = Mock()
        page.content.return_value = "<html>catalogue ready</html>"

        html = premium_bandai.charger_page_catalogue(
            page,
            "https://example.com/catalogue",
            exiger_produits=True,
        )

        page.goto.assert_called_once_with(
            "https://example.com/catalogue",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        page.wait_for_selector.assert_called_once_with(
            premium_bandai.PRODUCT_SELECTOR,
            state="attached",
            timeout=premium_bandai.PRODUCT_WAIT_TIMEOUT_MS,
        )
        page.wait_for_timeout.assert_called_once_with(
            premium_bandai.FIRST_PAGE_SETTLE_MS
        )
        self.assertEqual("<html>catalogue ready</html>", html)

    def test_later_catalogue_page_can_be_empty(self):
        page = Mock()
        page.content.return_value = "<html>empty final page</html>"

        html = premium_bandai.charger_page_catalogue(
            page,
            "https://example.com/catalogue?offset=100",
            exiger_produits=False,
        )

        page.wait_for_selector.assert_not_called()
        page.wait_for_timeout.assert_called_once_with(
            premium_bandai.NEXT_PAGE_SETTLE_MS
        )
        self.assertEqual("<html>empty final page</html>", html)

    def test_later_page_waits_until_products_change(self):
        page = Mock()
        ancien_html = (
            '<div class="o-search-product">'
            '<a class="c-product__link" href="/us/item/N1"></a>'
            '</div>'
        )
        nouvel_html = (
            '<div class="o-search-product">'
            '<a class="c-product__link" href="/us/item/N2"></a>'
            '</div>'
        )
        page.content.side_effect = [ancien_html, nouvel_html]

        html = premium_bandai.charger_page_catalogue(
            page,
            "https://example.com/catalogue?offset=20",
            exiger_produits=False,
            liens_precedents={"https://p-bandai.com/us/item/N1"},
        )

        self.assertEqual(nouvel_html, html)
        self.assertEqual(2, page.content.call_count)
        self.assertEqual(
            [
                (premium_bandai.NEXT_PAGE_SETTLE_MS,),
                (premium_bandai.NEXT_PAGE_POLL_MS,),
            ],
            [call.args for call in page.wait_for_timeout.call_args_list],
        )

    def test_email_sender_is_removed(self):
        self.assertFalse(hasattr(notifier, "send_email"))

    def test_broad_sources_do_not_filter_shop_series_or_status(self):
        self.assertEqual(3, len(premium_bandai.URL_TEMPLATES))
        self.assertTrue(any("/us/search?keyword=" in url
                            for url in premium_bandai.URL_TEMPLATES))
        for url in premium_bandai.URL_TEMPLATES:
            self.assertIn("_f_productStatuses=Waiting,On,End", url)
            self.assertNotIn("_f_shops", url)
            self.assertNotIn("_f_series", url)

    def test_japanese_4th_anniversary_discovery_and_transition_once(self):
        lien = "https://p-bandai.com/us/item/N2873815002"
        nom = "ONE PIECE CARD GAME Japanese 4th Anniversary Set"
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp:
            try:
                os.chdir(temp)
                Path("ancien_stock.json").write_text(
                    json.dumps({"Premium Bandai US": {}}), encoding="utf-8"
                )
                etat = {}
                for wording, expected, expected_type in (
                    ("COMING SOON", "COMING_SOON", "NOUVEAU PRODUIT RÉFÉRENCÉ"),
                    ("PRE-ORDERS OPEN", "PREORDER", "NOUVELLE PRÉCOMMANDE"),
                    ("PRE-ORDERS OPEN", "PREORDER", None),
                ):
                    html = f"""
                    <div class="o-search-product"><a class="c-product__link"
                        href="/us/item/N2873815002">
                      <span class="c-product__title">{nom}</span>
                      <span>{wording}</span>
                    </a></div>"""
                    produits = {}
                    premium_bandai.extraire_page(html, produits)
                    self.assertEqual(expected, produits[lien]["status"])
                    alertes = filtrer_alertes(
                        comparer({"Premium Bandai US": produits}), etat
                    )
                    self.assertEqual(
                        [expected_type] if expected_type else [],
                        [alerte["type_alerte"] for alerte in alertes],
                    )
                    stock = {"Premium Bandai US": produits}
                    etat = mettre_a_jour_etat(etat, alertes, stock)
                    Path("ancien_stock.json").write_text(
                        json.dumps(stock), encoding="utf-8"
                    )
            finally:
                os.chdir(original_cwd)

    def test_new_anniversary_reference_alerts_for_unknown_and_sold_out(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp:
            try:
                os.chdir(temp)
                Path("ancien_stock.json").write_text(
                    json.dumps({"Premium Bandai US": {}}), encoding="utf-8"
                )
                for status in ("UNKNOWN", "SOLD OUT"):
                    with self.subTest(status=status):
                        link = "https://p-bandai.com/us/item/N2873815002"
                        product = {
                            "site": "Premium Bandai US",
                            "name": "ONE PIECE CARD GAME Japanese 4th Anniversary Set",
                            "link": link,
                            "status": status,
                            "orderable": False,
                            "notify_when_referenced": True,
                        }
                        alerts = comparer({"Premium Bandai US": {link: product}})
                        self.assertEqual(
                            ["NOUVEAU PRODUIT RÉFÉRENCÉ"],
                            [alert["type_alerte"] for alert in alerts],
                        )
            finally:
                os.chdir(original_cwd)

    def test_scanner_finds_japanese_4th_anniversary_from_unfiltered_page(self):
        html = """<div class="o-search-product">
          <a class="c-product__link" href="/us/item/N2873815002">
            <p class="c-product__title">ONE PIECE CARD GAME Japanese 4th Anniversary Set</p>
            <span>OUT OF STOCK</span>
          </a></div>"""
        browser = Mock()
        browser.new_page.return_value.content.return_value = (
            '<h1>ONE PIECE CARD GAME Japanese 4th Anniversary Set</h1>'
            '<button>OUT OF STOCK</button>')
        browser.new_page.return_value.goto.return_value = None
        context = Mock()
        context.__enter__ = Mock(return_value=Mock(chromium=Mock(
            launch=Mock(return_value=browser))))
        context.__exit__ = Mock(return_value=False)

        with patch.object(premium_bandai, "sync_playwright", return_value=context), \
             patch('integrite.charger_stock_precedent', return_value={}), \
             patch.object(premium_bandai, "charger_page_catalogue",
                          side_effect=[html, html, html]) as charger:
            produits = premium_bandai.scan()

        produit = produits["https://p-bandai.com/us/item/N2873815002"]
        self.assertEqual("SOLD OUT", produit["status"])
        self.assertTrue(produit["notify_when_referenced"])
        self.assertEqual(3, charger.call_count)
        for call in charger.call_args_list:
            self.assertIn("_f_productStatuses=Waiting,On,End", call.args[1])


if __name__ == "__main__":
    unittest.main()
