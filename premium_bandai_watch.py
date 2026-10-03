"""Premium Bandai pass preserving partial discoveries and shared alert history."""

import argparse

from boutiques import BOUTIQUES
from comparateur import comparer
from confirmation import confirmer_transitions
from deduplication import (
    charger_etat,
    filtrer_alertes,
    mettre_a_jour_etat,
    sauvegarder_etat,
)
from integrite import charger_stock_precedent, valider_scan
from mise_a_jour_stock import sauvegarder
from notifier import send_discord
from scanners import premium_bandai
from premium_bandai_health import STATE_FILE, enregistrer_scan, maintenant


NOM = "Premium Bandai US"


def surveiller(dry_run=False):
    boutique = next(b for b in BOUTIQUES if b["nom"] == NOM)
    precedent = charger_stock_precedent()
    sante = charger_etat(STATE_FILE)
    try:
        produits, erreurs = premium_bandai.scan_avec_diagnostic(precedent.get(NOM, {}))
        produits = valider_scan(boutique, produits, precedent)
    except Exception as erreur:
        if not dry_run:
            sante = enregistrer_scan(sante, [type(erreur).__name__], maintenant())
            sauvegarder_etat(sante, STATE_FILE)
        raise
    courant = {**precedent, NOM: produits}
    if not dry_run:
        confirmer_transitions([boutique], precedent, {NOM: produits})

    alertes = filtrer_alertes(comparer({NOM: produits}), charger_etat())
    if dry_run:
        print(f"Diagnostic sans envoi : {len(produits)} références, {len(alertes)} alertes possibles")
        print("Sources :", erreurs or "complètes")
        return erreurs

    # Acknowledge each successful delivery so a later failure cannot resend it.
    etat = charger_etat()
    for alerte in alertes:
        send_discord([alerte])
        etat = mettre_a_jour_etat(etat, [alerte], {})
        sauvegarder_etat(etat)

    etat = mettre_a_jour_etat(etat, alertes, courant)
    sauvegarder(courant)
    sauvegarder_etat(etat)
    print(f"✅ Premium Bandai : {len(produits)} référence(s), "
          f"{len(alertes)} alerte(s)")
    sante = enregistrer_scan(sante, erreurs, maintenant())
    sauvegarder_etat(sante, STATE_FILE)
    return erreurs


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    erreurs = surveiller(args.dry_run)
    if erreurs and not args.dry_run:
        raise SystemExit(2)
