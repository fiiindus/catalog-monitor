import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import premium_bandai_health as health
import premium_bandai_watch as watch
from scanners import premium_bandai as pb

LINK = 'https://p-bandai.com/us/item/N2873815002'
NAME = 'ONE PIECE CARD GAME Japanese 4th Anniversary Set'


def product(status='SOLD OUT', link=LINK):
    return dict(site=watch.NOM, name=NAME, link=link, status=status,
                orderable=pb.est_commandable(status), notify_when_referenced=True)


def card(link='/us/item/N2873815002', status='OUT OF STOCK'):
    return f'<div class="o-search-product"><a class="c-product__link" href="{link}"><p class="c-product__title">{NAME}</p><span>{status}</span></a></div>'


class ScannerReliabilityTests(unittest.TestCase):
    def browser_context(self):
        browser = Mock()
        page = browser.new_page.return_value
        page.goto.return_value = None
        page.content.return_value = f'<h1>{NAME}</h1><button>OUT OF STOCK</button>'
        context = Mock()
        context.__enter__ = Mock(return_value=Mock(chromium=Mock(launch=Mock(return_value=browser))))
        context.__exit__ = Mock(return_value=False)
        return context, browser

    def test_failed_first_page_never_skips_newest_items(self):
        context, browser = self.browser_context()
        with patch.object(pb, 'sync_playwright', return_value=context), \
                patch.object(pb, 'charger_page_catalogue', side_effect=[TimeoutError(), TimeoutError(), card(), card()]) as load:
            produits, errors = pb.scan_avec_diagnostic()
        self.assertEqual(4, load.call_count)
        self.assertTrue(all('offset=0' in call.args[1] for call in load.call_args_list))
        self.assertEqual('SOLD OUT', produits[LINK]['status'])
        self.assertEqual(1, len(errors))
        browser.close.assert_called_once()

    def test_partial_catalogue_keeps_absent_history_and_checks_anniversary(self):
        context, browser = self.browser_context()
        old_link = 'https://p-bandai.com/us/item/N123'
        old = {old_link: product('PREORDER', old_link)}
        with patch.object(pb, 'sync_playwright', return_value=context), \
                patch.object(pb, 'charger_page_catalogue', side_effect=[TimeoutError(), TimeoutError(), card(), card()]), \
                patch.object(pb, 'extraire_detail', side_effect=[product('PREORDER'), RuntimeError()]):
            produits, errors = pb.scan_avec_diagnostic(old)
        self.assertEqual('PREORDER', produits[LINK]['status'])
        self.assertEqual(old[old_link], produits[old_link])
        self.assertEqual(2, len(errors))

    def test_repeated_and_truncated_pagination_are_degraded(self):
        context, _ = self.browser_context()
        with patch.object(pb, 'sync_playwright', return_value=context), \
                patch.object(pb, 'PAGE_SIZE', 1), \
                patch.object(pb, 'MAX_PAGES', 2), \
                patch.object(pb, 'charger_page_catalogue', return_value=card()):
            _, errors = pb.scan_avec_diagnostic()
        self.assertEqual(3, len(errors))
        self.assertTrue(all('Pagination répétée' in error for error in errors))
        with patch.object(pb, 'sync_playwright', return_value=context), \
                patch.object(pb, 'PAGE_SIZE', 1), \
                patch.object(pb, 'MAX_PAGES', 1), \
                patch.object(pb, 'charger_page_catalogue', return_value=card()):
            _, errors = pb.scan_avec_diagnostic()
        self.assertTrue(all('Limite de pagination' in error for error in errors))

    def test_tracking_links_share_identity_and_external_links_are_ignored(self):
        products = {}
        pb.extraire_page(card('/us/item/N2873815002?utm_source=mail#top'), products)
        pb.extraire_page(card('https://other.example/us/item/N2873815002'), products)
        self.assertEqual([LINK], list(products))

    def test_disabled_buy_button_never_claims_orderability(self):
        html = f'<h1>{NAME}</h1><button disabled>Add to cart</button>'
        with self.assertRaises(pb.ScanIncomplet):
            pb.extraire_detail(html, LINK)
        html += '<button>OUT OF STOCK</button>'
        self.assertEqual('SOLD OUT', pb.extraire_detail(html, LINK)['status'])

    def test_anniversary_real_detail_dom_reports_closed_stock(self):
        html = (Path(__file__).parent / 'fixtures' / 'premium_bandai_anniversary_detail.html').read_text(encoding='utf-8')
        produit = pb.extraire_detail(html, LINK)
        self.assertEqual(NAME, produit['name'])
        self.assertEqual('SOLD OUT', produit['status'])
        self.assertFalse(produit['orderable'])

    def test_unknown_listing_does_not_rearm_known_preorder(self):
        context, _ = self.browser_context()
        with patch.object(pb, 'sync_playwright', return_value=context), \
                patch.object(pb, 'charger_page_catalogue', return_value=card(status='')), \
                patch.object(pb, 'extraire_detail', side_effect=pb.ScanIncomplet('unknown')):
            produits, errors = pb.scan_avec_diagnostic({LINK: product('PREORDER')})
        self.assertEqual('PREORDER', produits[LINK]['status'])
        self.assertTrue(produits[LINK]['orderable'])
        self.assertTrue(errors)


class FreshnessTests(unittest.TestCase):
    def test_fifteen_minute_boundary_and_incident_deduplication(self):
        now = datetime(2026, 10, 2, 20, tzinfo=timezone.utc)
        notify = Mock()
        state = {'last_complete_at': (now - timedelta(seconds=899)).isoformat()}
        state, stale = health.verifier(state, now, notify)
        self.assertFalse(stale)
        state, stale = health.verifier(state, now + timedelta(seconds=1), notify)
        self.assertTrue(stale)
        state, _ = health.verifier(state, now + timedelta(minutes=10), notify)
        self.assertEqual(1, notify.call_count)
        state['last_complete_at'] = now.isoformat()
        state, stale = health.verifier(state, now, notify)
        self.assertFalse(stale)
        self.assertEqual(2, notify.call_count)

    def test_degraded_scan_cannot_refresh_complete_timestamp(self):
        now = datetime(2026, 10, 2, 20, tzinfo=timezone.utc)
        notify = Mock()
        old = (now - timedelta(hours=1)).isoformat()
        state = health.enregistrer_scan({'last_complete_at': old}, ['timeout'], now, notify)
        state = health.enregistrer_scan(state, ['timeout'], now, notify)
        self.assertEqual(old, state['last_complete_at'])
        self.assertEqual(1, notify.call_count)
        state = health.enregistrer_scan(state, [], now, notify)
        self.assertEqual(now.isoformat(), state['last_complete_at'])
        self.assertEqual(2, notify.call_count)

    def test_missing_invalid_or_future_timestamp_is_not_healthy(self):
        now = datetime.now(timezone.utc)
        for value in (None, 'invalid', '2026-10-02T20:00:00', (now + timedelta(minutes=1)).isoformat()):
            with self.subTest(value=value):
                _, stale = health.verifier({'last_complete_at': value}, now, Mock())
                self.assertTrue(stale)


class DedicatedWatchTests(unittest.TestCase):
    def test_dry_run_never_writes_state_or_sends_discord(self):
        with patch.object(watch, 'charger_stock_precedent', return_value={watch.NOM: {}}), \
                patch.object(watch, 'charger_etat', return_value={}), \
                patch.object(watch.premium_bandai, 'scan_avec_diagnostic', return_value=({LINK: product()}, ['timeout'])), \
                patch.object(watch, 'valider_scan', side_effect=lambda b,p,s:p), \
                patch.object(watch, 'comparer', return_value=[]), \
                patch.object(watch, 'send_discord') as send, \
                patch.object(watch, 'sauvegarder') as stock, \
                patch.object(watch, 'sauvegarder_etat') as state:
            self.assertEqual(['timeout'], watch.surveiller(dry_run=True))
        send.assert_not_called()
        stock.assert_not_called()
        state.assert_not_called()

    def test_partial_discord_delivery_is_acknowledged_before_later_failure(self):
        second_link = 'https://p-bandai.com/us/item/N2'
        first, second = product('PREORDER'), product('PREORDER', second_link)
        for alert in (first, second):
            alert['type_alerte'] = 'NOUVELLE PRÉCOMMANDE'
        with patch.object(watch, 'charger_stock_precedent', return_value={watch.NOM: {}}), \
                patch.object(watch, 'charger_etat', return_value={}), \
                patch.object(watch.premium_bandai, 'scan_avec_diagnostic', return_value=({LINK: first, second_link: second}, [])), \
                patch.object(watch, 'valider_scan', side_effect=lambda b,p,s:p), \
                patch.object(watch, 'confirmer_transitions'), \
                patch.object(watch, 'comparer', return_value=[first, second]), \
                patch.object(watch, 'send_discord', side_effect=[None, RuntimeError('Discord failure')]), \
                patch.object(watch, 'sauvegarder_etat') as state, \
                patch.object(watch, 'sauvegarder') as stock:
            with self.assertRaises(RuntimeError):
                watch.surveiller()
        self.assertEqual(1, state.call_count)
        self.assertIn(LINK, state.call_args.args[0])
        self.assertNotIn(second_link, state.call_args.args[0])
        stock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
