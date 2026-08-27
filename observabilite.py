import threading
import time
from collections import Counter

from integrite import normaliser_identite_lien


_ETAT = threading.local()


def commencer_mesure():
    _ETAT.requetes = 0
    _ETAT.debut = time.monotonic()


def noter_requete(nombre=1):
    _ETAT.requetes = int(getattr(_ETAT, "requetes", 0)) + int(nombre)


def lire_mesure():
    debut = getattr(_ETAT, "debut", time.monotonic())
    return {
        "duration_seconds": max(0.0, time.monotonic() - debut),
        "requests": int(getattr(_ETAT, "requetes", 0)),
    }


def _index(produits):
    return {
        normaliser_identite_lien(lien): produit
        for lien, produit in produits.items()
    }


def calculer_evolution(ancien, nouveau):
    ancien_index = _index(ancien if isinstance(ancien, dict) else {})
    nouveau_index = _index(nouveau)
    anciens_liens = set(ancien_index)
    nouveaux_liens = set(nouveau_index)
    communs = anciens_liens & nouveaux_liens
    changements_statut = sum(
        ancien_index[lien].get("status")
        != nouveau_index[lien].get("status")
        for lien in communs
    )
    return {
        "added": len(nouveaux_liens - anciens_liens),
        "removed": len(anciens_liens - nouveaux_liens),
        "status_changes": changements_statut,
    }


def journaliser_reussite(nom, produits, precedent):
    mesure = lire_mesure()
    evolution = calculer_evolution(precedent, produits)
    statuts = Counter(
        produit.get("status", "ABSENT")
        for produit in produits.values()
    )
    resume_statuts = ", ".join(
        f"{statut}:{nombre}"
        for statut, nombre in sorted(statuts.items())
    ) or "aucun"
    print(
        f"📊 {nom} | durée={mesure['duration_seconds']:.1f}s "
        f"| pages/requêtes={mesure['requests']} "
        f"| statuts={resume_statuts} "
        f"| évolution=+{evolution['added']}/-{evolution['removed']}"
        f"/Δ{evolution['status_changes']}"
    )


def journaliser_echec(nom, erreur):
    mesure = lire_mesure()
    print(
        f"📊 {nom} | échec après {mesure['duration_seconds']:.1f}s "
        f"| pages/requêtes={mesure['requests']} | erreur={erreur}"
    )

