import unittest
from unittest.mock import Mock

import notifier
from comparateur import alerte_disponibilite_autorisee
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

    def test_ordinary_playmats_are_excluded(self):
        self.assertFalse(
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

    def test_single_chinese_card_stays_excluded(self):
        self.assertFalse(
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


if __name__ == "__main__":
    unittest.main()
