import json
import os
import re
from urllib.parse import urlsplit, urlunsplit

from cible import CIBLE_PRIORITAIRE, est_cible_prioritaire
from scanners.politique import normaliser


# Nom conservé pour compatibilité avec l'historique existant. Le contenu suit
# désormais la cible prioritaire configurée dans config.json.
FICHIER_ETAT = "op17_missing.json"
SEUIL_DISPARITION = 2


def charger_etat():
    if not os.path.exists(FICHIER_ETAT):
        return {}

    try:
        with open(FICHIER_ETAT, "r", encoding="utf-8") as fichier:
            etat = json.load(fichier)
    except (OSError, json.JSONDecodeError) as erreur:
        raise RuntimeError(
            f"L'état de suivi des disparitions {CIBLE_PRIORITAIRE} est illisible"
        ) from erreur

    if not isinstance(etat, dict):
        raise RuntimeError(
            f"L'état de suivi des disparitions {CIBLE_PRIORITAIRE} est invalide"
        )

    return etat


def sauvegarder_etat(etat):
    fichier_temporaire = FICHIER_ETAT + ".tmp"

    with open(fichier_temporaire, "w", encoding="utf-8") as fichier:
        json.dump(etat, fichier, indent=2, ensure_ascii=False)
        fichier.write("\n")

    os.replace(fichier_temporaire, FICHIER_ETAT)


def normaliser_lien(lien):
    parties = urlsplit(str(lien or "").strip())
    if not parties.scheme or not parties.netloc:
        return str(lien or "").strip()

    return urlunsplit(
        (
            parties.scheme.casefold(),
            parties.netloc.casefold(),
            re.sub(r"/+", "/", parties.path).rstrip("/"),
            "",
            "",
        )
    )


def cle_produit(boutique, lien, produit):
    lien_normalise = normaliser_lien(lien or produit.get("link", ""))
    if lien_normalise:
        return boutique + "|" + lien_normalise

    return boutique + "|nom:" + normaliser(produit.get("name", ""))


def indexer_op17(stock):
    """Alias historique : indexe la cible prioritaire configurée."""
    index = {}

    for boutique, produits in (stock or {}).items():
        if not isinstance(produits, dict):
            continue

        for lien, produit in produits.items():
            if not isinstance(produit, dict):
                continue

            if not est_cible_prioritaire(produit.get("name", "")):
                continue

            cle = cle_produit(boutique, lien, produit)
            index[cle] = {
                "boutique": boutique,
                "produit": produit,
            }

    return index


def analyser_disparitions(ancien, nouveau, etat=None):
    etat = charger_etat() if etat is None else etat
    ancien_cible = indexer_op17(ancien)
    nouveau_cible = indexer_op17(nouveau)
    candidats = {}

    for cle, entree in etat.items():
        if not isinstance(entree, dict):
            continue

        produit = entree.get("produit")
        boutique = entree.get("boutique")
        if isinstance(produit, dict) and isinstance(boutique, str):
            # Un état d'une ancienne cible ne doit pas survivre au changement
            # de priority_set.
            if not est_cible_prioritaire(produit.get("name", "")):
                continue

            candidats[cle] = {
                "boutique": boutique,
                "produit": produit,
                "compteur": max(0, int(entree.get("compteur", 0))),
                "alerte_envoyee": bool(entree.get("alerte_envoyee")),
            }

    for cle, entree in ancien_cible.items():
        candidats.setdefault(
            cle,
            {
                **entree,
                "compteur": 0,
                "alerte_envoyee": False,
            },
        )

    alertes = []
    nouvel_etat = {}

    for cle, entree in candidats.items():
        if cle in nouveau_cible:
            continue

        alerte_envoyee = entree["alerte_envoyee"]
        if alerte_envoyee:
            compteur = SEUIL_DISPARITION
        else:
            compteur = min(
                entree["compteur"] + 1,
                SEUIL_DISPARITION,
            )

        produit = dict(entree["produit"])
        boutique = entree["boutique"]

        if compteur >= SEUIL_DISPARITION and not alerte_envoyee:
            produit.update(
                {
                    "boutique": boutique,
                    "status": "REMOVED",
                    "type_alerte": (
                        f"PRODUIT {CIBLE_PRIORITAIRE} RETIRÉ DU CATALOGUE"
                    ),
                    "priority": 10000,
                    "priority_target": CIBLE_PRIORITAIRE,
                }
            )
            alertes.append(produit)
            alerte_envoyee = True

        nouvel_etat[cle] = {
            "boutique": boutique,
            "produit": entree["produit"],
            "compteur": compteur,
            "alerte_envoyee": alerte_envoyee,
        }

    return alertes, nouvel_etat
