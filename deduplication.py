import hashlib
import json
import os

from integrite import normaliser_identite_lien


FICHIER_ALERTES_ENVOYEES = "alertes_envoyees.json"


def charger_etat(chemin=FICHIER_ALERTES_ENVOYEES):
    if not os.path.exists(chemin):
        return {}
    try:
        with open(chemin, "r", encoding="utf-8") as fichier:
            etat = json.load(fichier)
    except (OSError, json.JSONDecodeError) as erreur:
        raise RuntimeError(
            f"État de déduplication illisible : {chemin}"
        ) from erreur
    if not isinstance(etat, dict):
        raise RuntimeError(f"État de déduplication invalide : {chemin}")
    return etat


def sauvegarder_etat(etat, chemin=FICHIER_ALERTES_ENVOYEES):
    chemin = os.fspath(chemin)
    temporaire = chemin + ".tmp"
    with open(temporaire, "w", encoding="utf-8") as fichier:
        json.dump(etat, fichier, indent=2, ensure_ascii=False, sort_keys=True)
        fichier.write("\n")
    os.replace(temporaire, chemin)


def identite_alerte(alerte):
    lien = normaliser_identite_lien(alerte.get("link", ""))
    if lien:
        return lien
    return "nom:" + str(alerte.get("site", "")) + ":" + str(
        alerte.get("name", "")
    )


def empreinte_alerte(alerte):
    donnees = {
        "identity": identite_alerte(alerte),
        "type": str(alerte.get("type_alerte", "")),
        "status": str(alerte.get("status", "")),
        "availability": str(alerte.get("availability", "")),
    }
    contenu = json.dumps(
        donnees,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(contenu).hexdigest()


def filtrer_alertes(alertes, etat):
    resultat = []
    empreintes_du_passage = set()

    for alerte in alertes:
        identite = identite_alerte(alerte)
        empreinte = empreinte_alerte(alerte)
        deja_envoyee = etat.get(identite, {}).get("fingerprint") == empreinte

        if deja_envoyee or empreinte in empreintes_du_passage:
            print(
                "🔕 Alerte déjà remise, doublon supprimé :",
                alerte.get("name", "Produit inconnu"),
            )
            continue

        empreintes_du_passage.add(empreinte)
        resultat.append(alerte)

    return resultat


def _statuts_courants(stock):
    statuts = {}
    for produits in stock.values():
        for lien, produit in produits.items():
            statuts[normaliser_identite_lien(lien)] = produit.get("status")
    return statuts


def mettre_a_jour_etat(etat, alertes_envoyees, stock):
    statuts = _statuts_courants(stock)
    nouvel_etat = {
        identite: entree
        for identite, entree in etat.items()
        if identite not in statuts
        or statuts.get(identite) == entree.get("status")
    }

    for alerte in alertes_envoyees:
        identite = identite_alerte(alerte)
        nouvel_etat[identite] = {
            "fingerprint": empreinte_alerte(alerte),
            "status": alerte.get("status", ""),
            "type": alerte.get("type_alerte", ""),
            "name": alerte.get("name", ""),
        }

    return nouvel_etat
