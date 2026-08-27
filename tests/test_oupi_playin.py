import json
import unittest
from unittest.mock import patch

from cible import CIBLE_PRIORITAIRE
from scanners import oupi, playin


class OupiScannerTests(unittest.TestCase):
    def test_parses_priority_case_even_when_sold_out(self):
        html = f"""
        <article class="product-miniature">
          <a class="thumbnail" itemprop="url"
             href="/fr/case-scelle-de-display/7368-case-prioritaire-francais.html">
            <img itemprop="image" src="/case.jpg">
          </a>
          <div class="product-title"><h6 itemprop="name">
            Case Scellée de 12 Display {CIBLE_PRIORITAIRE} (Français) - One Piece Card Game
          </h6></div>
          <div class="product-price-and-shipping"><span class="price">1 437,12 €</span></div>
          <div>Précommande : Disponibilité fin août 2026</div>
          <button data-button-action="add-to-cart"
                  class="tvproduct-out-of-stock disable"
                  data-original-title="Out Of Stock" disabled></button>
        </article>
        """

        produits = oupi.extraire_produits(html, source="priority_focus")

        self.assertEqual(1, len(produits))
        produit = next(iter(produits.values()))
        self.assertEqual("SOLD OUT", produit["status"])
        self.assertEqual("fin août 2026", produit["availability"])
        self.assertEqual("VF", produit["language"])
        self.assertTrue(produit["notify_when_referenced"])

    def test_excludes_ordinary_sleeves_and_japanese_products(self):
        self.assertFalse(
            oupi.produit_surveille(
                "Protège-cartes Luffy - One Piece Card Game"
            )
        )
        self.assertFalse(
            oupi.produit_surveille(
                f"Display {CIBLE_PRIORITAIRE} (Japonais) - One Piece Card Game"
            )
        )

    def test_keeps_accessory_with_exclusive_promo(self):
        self.assertTrue(
            oupi.produit_surveille(
                "Tapis de jeu One Piece avec carte promo exclusive"
            )
        )

    def test_preorder_route_failure_does_not_abort_main_catalogue(self):
        catalogue_html = """
        <article class="product-miniature">
          <a class="thumbnail" itemprop="url"
             href="/fr/display-one-piece/9999-display-op-16.html">
            <img itemprop="image" src="/display.jpg">
          </a>
          <div class="product-title"><h6 itemprop="name">
            Display OP-16 Boite de Booster (Français) - One Piece Card Game
          </h6></div>
          <div class="product-price-and-shipping"><span class="price">119,76 €</span></div>
          <button data-button-action="add-to-cart"></button>
        </article>
        """

        appels = []

        def charger(url, autoriser_vide=False):
            appels.append(url)
            if url == oupi.CATALOGUE_URL:
                return catalogue_html
            if url == oupi.PREORDER_URL:
                raise RuntimeError("503 Service Unavailable")
            if url == oupi.PRIORITY_SEARCH_URL:
                return "<html><body>Aucun résultat</body></html>"
            raise AssertionError(f"URL inattendue: {url}")

        with patch.object(oupi, "charger_page", side_effect=charger):
            produits = oupi.scan()

        self.assertEqual(1, len(produits))
        produit = next(iter(produits.values()))
        self.assertEqual("catalogue", produit["source"])
        self.assertEqual(oupi.CATALOGUE_URL, appels[0])
        self.assertIn(oupi.PREORDER_URL, appels)

    def test_auxiliary_source_does_not_overwrite_catalogue_product(self):
        lien = "https://oupi.eu/fr/display-one-piece/1-test.html"
        produit_catalogue = {
            "site": "Oupi",
            "name": f"Display {CIBLE_PRIORITAIRE} One Piece Card Game",
            "price": "100,00 €",
            "status": "SOLD OUT",
            "availability": "",
            "link": lien,
            "image": "",
            "language": "VF",
            "source": "catalogue",
            "notify_when_referenced": True,
        }
        produits = {lien: produit_catalogue.copy()}
        html = f"""
        <article class="product-miniature">
          <a class="thumbnail" itemprop="url" href="{lien}"></a>
          <div class="product-title"><h6 itemprop="name">
            Display {CIBLE_PRIORITAIRE} One Piece Card Game
          </h6></div>
          <span class="price">120,00 €</span>
          <button data-button-action="add-to-cart"></button>
        </article>
        """

        with patch.object(oupi, "charger_page", return_value=html):
            ajoutes = oupi.ajouter_source_optionnelle(
                produits,
                oupi.PREORDER_URL,
                source="preorders",
            )

        self.assertEqual(0, ajoutes)
        self.assertEqual("catalogue", produits[lien]["source"])
        self.assertEqual("SOLD OUT", produits[lien]["status"])


class PlayinScannerTests(unittest.TestCase):
    def test_parses_priority_from_server_item_list(self):
        item_list = {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "item": {
                        "@type": "Product",
                        "name": f"Double Pack Set 12 {CIBLE_PRIORITAIRE} - One Piece FR",
                        "url": "/fr/produit/663250/double-pack-priority-fr",
                        "image": "https://media.play-in.com/priority.jpg",
                        "offers": {
                            "@type": "Offer",
                            "price": 0,
                            "availability": "https://schema.org/OutOfStock",
                        },
                    },
                }
            ],
        }
        chunk = json.dumps(
            item_list,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        html = (
            "<script>self.__next_f.push("
            + json.dumps([1, chunk])
            + ")</script>"
        )

        produits = playin.extraire_produits_json_ld(html)

        self.assertEqual(1, len(produits))
        produit = next(iter(produits.values()))
        self.assertEqual("COMING_SOON", produit["status"])
        self.assertEqual("Non disponible", produit["price"])
        self.assertTrue(produit["notify_when_referenced"])

    def test_parses_priority_from_server_flight_data(self):
        donnees = {
            "__typename": "SealedProduct",
            "_id": 663251,
            "transName": f"Display de 24 boosters {CIBLE_PRIORITAIRE} - One Piece FR",
            "sellPrice": 179.9,
            "imageUrl": "https://media.play-in.com/priority.jpg",
            "releasedAt": "2026-08-27T00:00:00+02:00",
            "sellable": False,
            "inWarehouse": False,
            "inStore": False,
            "inRestocking": False,
            "category": {
                "__typename": "ProductCategory",
                "transName": "Display One Piece",
            },
        }
        chunk = (
            'c1:["$","li","663251",{'
            '"product":' + json.dumps(donnees) + ','
            '"href":"/fr/produit/663251/display-priority-one-piece-fr"'
            '}]'
        )
        html = (
            "<script>self.__next_f.push("
            + json.dumps([1, chunk])
            + ")</script>"
        )

        produits = playin.extraire_produits_flight(html)

        self.assertEqual(1, len(produits))
        produit = next(iter(produits.values()))
        self.assertEqual("COMING_SOON", produit["status"])
        self.assertEqual("27/08/2026", produit["availability"])
        self.assertEqual("VF", produit["language"])
        self.assertTrue(produit["notify_when_referenced"])

        self.assertEqual(
            "27/08/2026",
            playin.extraire_disponibilite_detail(html, 663251),
        )

    def test_parses_announced_priority_and_release_date(self):
        html = f"""
        <ul class="grid--template_productCatalog">
        <li class="tile--type_catalogItem"
            title="Display de 24 boosters {CIBLE_PRIORITAIRE} - One Piece FR">
          <div>À venir</div><div>Bientôt disponible</div>
          <a href="/fr/produit/663251/display-priority-one-piece-fr">
            Display de 24 boosters {CIBLE_PRIORITAIRE} - One Piece FR
          </a>
          <p>Sortie prévue le 27/08/2026</p>
          <img src="https://media.play-in.com/priority.jpg">
        </li></ul>
        """

        produits = playin.extraire_produits(html)

        self.assertEqual(1, len(produits))
        produit = next(iter(produits.values()))
        self.assertEqual("COMING_SOON", produit["status"])
        self.assertEqual("27/08/2026", produit["availability"])
        self.assertEqual("VF", produit["language"])
        self.assertTrue(produit["notify_when_referenced"])

    def test_store_only_is_not_reported_as_shippable(self):
        html = """
        <ul class="grid--template_productCatalog">
        <li class="tile--type_catalogItem"
            title="Deck de démarrage ST-33 - One Piece EN">
          <a href="/fr/produit/1/deck-st-33-one-piece-en">Deck ST-33</a>
          <span>Retrait magasin uniquement</span><span>24,90 €</span>
        </li></ul>
        """

        produit = next(iter(playin.extraire_produits(html).values()))
        self.assertEqual("STORE_ONLY", produit["status"])
        self.assertEqual("STORE_ONLY", produit["delivery"])

    def test_excludes_korean_products_and_ordinary_playmats(self):
        self.assertFalse(
            playin.produit_surveille(
                "Booster Pillars of Strength OPK03 - One Piece KO"
            )
        )
        self.assertFalse(
            playin.produit_surveille(
                "Tapis de jeu Fruits du Démon - One Piece"
            )
        )


if __name__ == "__main__":
    unittest.main()
