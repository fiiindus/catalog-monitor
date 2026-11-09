"""Temporary read-only diagnostics on a GitHub-hosted runner."""
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import unittest
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


PHILIBERT = "https://www.philibertnet.com/fr/17214-one-piece-le-jeu-de-cartes"
OUPI = "https://oupi.eu/fr/382-one-piece"
USER_AGENT = "Mozilla/5.0 (compatible; onepiece-stock-tracker/1.0)"


def describe(source, status, url, html):
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    print(
        f"PROBE {source}: status={status} url={urlsplit(url).netloc}{urlsplit(url).path} "
        f"bytes={len(html)} title={title[:90]!r} "
        f"philibert={len(soup.select('.product-card[data-pid]'))} "
        f"oupi={len(soup.select('article.product-miniature'))}",
        flush=True,
    )


def probe_http(name, url, headers):
    try:
        response = requests.get(url, headers=headers, timeout=18)
        describe(name, response.status_code, response.url, response.text)
    except requests.RequestException as error:
        print(f"PROBE {name}: {type(error).__name__}", flush=True)


class RunnerAccessDiagnostics(unittest.TestCase):
    def test_report_public_catalogue_access(self):
        http_headers = {"User-Agent": USER_AGENT}
        reader_headers = {
            "X-Respond-With": "html",
            "X-Target-Selector": "#products",
            "X-Timeout": "15",
            "X-No-Cache": "true",
        }
        cases = [
            ("philibert-http-p1", PHILIBERT + "?p=1", http_headers),
            ("philibert-http-root", PHILIBERT, http_headers),
            ("oupi-http", OUPI, http_headers),
            ("oupi-http-page1", OUPI + "?page=1", http_headers),
            ("oupi-www", OUPI.replace("https://", "https://www."), http_headers),
            ("oupi-controller", "https://oupi.eu/index.php?controller=category&id_category=382&id_lang=1", http_headers),
            ("oupi-preorders", "https://oupi.eu/fr/413-precommande-one-piece", http_headers),
            ("oupi-reader", "https://r.jina.ai/" + OUPI, reader_headers),
        ]
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(lambda case: probe_http(*case), cases))

        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium", "--only-shell"],
            check=True,
            timeout=75,
        )
        with sync_playwright() as playwright:
            with playwright.chromium.launch(headless=True) as browser:
                for name, url in (("philibert-browser", PHILIBERT + "?p=1"), ("oupi-browser", OUPI)):
                    page = browser.new_page(locale="fr-FR")
                    try:
                        response = page.goto(url, wait_until="domcontentloaded", timeout=18000)
                        page.wait_for_timeout(3000)
                        describe(name, response.status if response else None, page.url, page.content())
                    except Exception as error:
                        print(f"PROBE {name}: {type(error).__name__}", flush=True)
                    finally:
                        page.close()
