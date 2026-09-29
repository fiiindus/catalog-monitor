"""Fast Premium Bandai pass sharing stock and alert history with the main scan."""

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


NOM = "Premium Bandai US"


def surveiller():
    boutique = next(b for b in BOUTIQUES if b["nom"] == NOM)
    precedent = charger_stock_precedent()
    produits = valider_scan(boutique, premium_bandai.scan(), precedent)
    courant = {**precedent, NOM: produits}
    confirmer_transitions([boutique], precedent, {NOM: produits})

    alertes = filtrer_alertes(comparer({NOM: produits}), charger_etat())
    if alertes:
        send_discord(alertes)

    etat = mettre_a_jour_etat(charger_etat(), alertes, courant)
    sauvegarder(courant)
    sauvegarder_etat(etat)
    print(f"✅ Premium Bandai : {len(produits)} référence(s), "
          f"{len(alertes)} alerte(s)")


if __name__ == "__main__":
    surveiller()
