import subprocess
import sys
import unittest

from boutiques import BOUTIQUES
from integrite import charger_stock_precedent, valider_scan
from scanners import philibert


class LivePhilibertDiagnostics(unittest.TestCase):
    def test_philibert_catalogue_on_hosted_runner(self):
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium", "--only-shell"],
            check=True,
            timeout=75,
        )
        boutique = next(b for b in BOUTIQUES if b["scanner"] == "philibert")
        produits = philibert.scan()
        produits = valider_scan(boutique, produits, charger_stock_precedent())
        self.assertTrue(produits)
        print(f"PROBE Philibert: {len(produits)} produits validés sur GitHub", flush=True)
