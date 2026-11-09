from collections import Counter
import unittest

from boutiques import BOUTIQUES
from integrite import charger_stock_precedent, valider_scan
from notifier import construire_embed
from scanners import parkage_cartes as parkage


class LiveParkageSingles(unittest.TestCase):
    def test_live_public_catalogue_and_discord_thumbnails(self):
        boutique = next(b for b in BOUTIQUES if b["scanner"] == "parkage_cartes")
        produits = valider_scan(boutique, parkage.scan(), charger_stock_precedent())
        self.assertTrue(produits)
        types = Counter(p["card_details"].split(" · ", 1)[0] for p in produits.values())
        self.assertEqual(set(parkage.RARITIES.values()), set(types))
        for carte in produits.values():
            self.assertTrue(construire_embed(carte).get("thumbnail"))
        self.assertEqual("Leader alternatif · EB05 · Near mint",
                         produits[parkage.BASE_URL + "/fr/1147754"]["card_details"])
        self.assertNotIn(parkage.BASE_URL + "/fr/1142334", produits)
        print(f"PARKAGE SINGLES LIVE: {len(produits)} cartes, {dict(types)}", flush=True)
