from collections import Counter
import importlib
import re
import subprocess
import sys
import unittest

from boutiques import BOUTIQUES
from integrite import charger_stock_precedent, valider_scan
from notifier import construire_embed


class LivePrimaryShops(unittest.TestCase):
    def test_primary_shops_against_live_catalogues(self):
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium", "--only-shell"],
            check=True,
            timeout=90,
        )
        previous = charger_stock_precedent()
        for slug in ("ultrajeux", "parkage"):
            with self.subTest(scanner=slug):
                boutique = next(b for b in BOUTIQUES if b["scanner"] == slug)
                module = importlib.import_module("scanners." + slug)
                results = valider_scan(boutique, module.scan(), previous)
                eb05 = [p for p in results.values() if re.search(r"\bEB[- ]?05\b", p["name"], re.I)]
                tins = [p for p in results.values() if re.search(r"\bTS[- ]?03\b", p["name"], re.I)]
                self.assertTrue(eb05)
                self.assertTrue(tins)
                if slug == "parkage":
                    self.assertTrue(all(module.BASE_URL + url in results for url in module.TIN_PACK_TS03.values()))
                for p in eb05 + tins:
                    self.assertTrue(construire_embed(p).get("thumbnail"))
                print(f"PRIMARY PROBE {slug}: {len(results)} produits; EB05={len(eb05)}, TS03={len(tins)}, {dict(Counter(p['status'] for p in results.values()))}", flush=True)
