from pathlib import Path
import unittest

from bs4 import BeautifulSoup

from scanners import (
    carte_one_piece,
    figurines_goodies,
    oupi,
    parkage,
    philibert,
    playin,
    premium_bandai,
    ultrajeux,
)


FIXTURES = Path(__file__).parent / "fixtures"


def fixture(nom):
    return (FIXTURES / nom).read_text(encoding="utf-8")


class HtmlFixtureTests(unittest.TestCase):
    def test_figurines_goodies_available_fixture(self):
        produits = {}
        figurines_goodies.extraire_page(
            fixture("figurines_goodies_available.html"),
            produits,
        )
        self.assertEqual("AVAILABLE", next(iter(produits.values()))["status"])

    def test_ultrajeux_store_only_fixture(self):
        texte = BeautifulSoup(
            fixture("ultrajeux_store_only.html"),
            "lxml",
        ).get_text(" ", strip=True)
        self.assertEqual("STORE_ONLY", ultrajeux.detect_status(texte))

    def test_premium_bandai_closed_fixture(self):
        produits = {}
        premium_bandai.extraire_page(
            fixture("premium_bandai_closed.html"),
            produits,
        )
        produit = next(iter(produits.values()))
        self.assertEqual("SOLD OUT", produit["status"])
        self.assertFalse(produit["orderable"])

    def test_parkage_store_only_fixture(self):
        texte = BeautifulSoup(
            fixture("parkage_store_only.html"),
            "lxml",
        ).get_text(" ", strip=True)
        self.assertEqual("STORE_ONLY", parkage.detecter_statut(texte))

    def test_philibert_coming_soon_fixture(self):
        soup = BeautifulSoup(
            fixture("philibert_coming_soon.html"),
            "lxml",
        )
        labels = soup.select_one(".label").get_text(" ", strip=True)
        stock = soup.select_one(".stock").get_text(" ", strip=True)
        self.assertEqual(
            "COMING_SOON",
            philibert.detecter_statut(labels, stock),
        )

    def test_carte_one_piece_preorder_fixture(self):
        produit = carte_one_piece.extraire_produit_json_ld(
            fixture("carte_one_piece_preorder.html")
        )
        self.assertEqual(
            "PREORDER",
            carte_one_piece.detecter_statut(produit, True),
        )

    def test_oupi_sold_out_fixture(self):
        produits = oupi.extraire_produits(fixture("oupi_sold_out.html"))
        self.assertEqual("SOLD OUT", next(iter(produits.values()))["status"])

    def test_playin_preorder_fixture(self):
        texte = BeautifulSoup(
            fixture("playin_preorder.html"),
            "lxml",
        ).get_text(" ", strip=True)
        self.assertEqual("PREORDER", playin.detecter_statut(texte))


if __name__ == "__main__":
    unittest.main()
