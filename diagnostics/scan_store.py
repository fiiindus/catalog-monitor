import argparse
import importlib
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from boutiques import BOUTIQUES
from integrite import charger_stock_precedent, valider_scan


def trouver_boutique(scanner):
    for boutique in BOUTIQUES:
        if (
            boutique["scanner"] == scanner
            or boutique["nom"].casefold() == scanner.casefold()
        ):
            return boutique

    disponibles = ", ".join(boutique["scanner"] for boutique in BOUTIQUES)
    raise SystemExit(
        f"Scanner inconnu: {scanner}. Valeurs disponibles: {disponibles}"
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Lance un scanner réel puis applique les règles d'intégrité "
            "de production."
        ),
    )
    parser.add_argument(
        "scanner",
        help="Nom de module du scanner, par exemple premium_bandai ou philibert.",
    )
    args = parser.parse_args()

    boutique = trouver_boutique(args.scanner)
    module = importlib.import_module(f"scanners.{boutique['scanner']}")

    print(f"🔎 Diagnostic live : {boutique['nom']}")
    produits = module.scan()
    valider_scan(
        boutique,
        produits,
        charger_stock_precedent(),
    )

    print(f"✅ {boutique['nom']} : {len(produits)} produit(s) validé(s)")

    for produit in produits.values():
        print(
            "-",
            produit.get("name", "Produit inconnu"),
            "|",
            produit.get("status", "UNKNOWN"),
            "|",
            produit.get("price", "Prix inconnu"),
        )


if __name__ == "__main__":
    main()
