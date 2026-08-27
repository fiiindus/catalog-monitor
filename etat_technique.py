import json
import os


FICHIER_PANNES = "boutiques_unavailable.json"
FICHIER_CHUTES = "catalogue_drop_state.json"


def _charger(chemin):
    if not os.path.exists(chemin):
        return {}

    try:
        with open(chemin, "r", encoding="utf-8") as fichier:
            valeur = json.load(fichier)
    except (OSError, json.JSONDecodeError) as erreur:
        raise RuntimeError(f"État technique illisible : {chemin}") from erreur

    if not isinstance(valeur, dict):
        raise RuntimeError(f"État technique invalide : {chemin}")

    return valeur


def _sauvegarder(chemin, valeur):
    temporaire = chemin + ".tmp"
    with open(temporaire, "w", encoding="utf-8") as fichier:
        json.dump(valeur, fichier, indent=2, ensure_ascii=False, sort_keys=True)
        fichier.write("\n")
    os.replace(temporaire, chemin)


def charger_pannes():
    return _charger(FICHIER_PANNES)


def sauvegarder_pannes(etat):
    _sauvegarder(FICHIER_PANNES, etat)


def charger_chutes():
    return _charger(FICHIER_CHUTES)


def sauvegarder_chutes(etat):
    _sauvegarder(FICHIER_CHUTES, etat)


def mettre_a_jour_pannes(boutiques, erreurs_finales, etat_precedent):
    erreurs_par_nom = {
        boutique["nom"]: erreur
        for boutique, erreur in erreurs_finales
    }
    nouvel_etat = {}
    nouvelles_pannes = []
    retablissements = []

    for boutique in boutiques:
        nom = boutique["nom"]
        erreur = erreurs_par_nom.get(nom)
        etait_en_panne = nom in etat_precedent

        if erreur is not None:
            nouvel_etat[nom] = {
                "error": str(erreur),
            }
            if (
                not etait_en_panne
                and not boutique.get("suppress_technical_alert", False)
            ):
                nouvelles_pannes.append((nom, erreur))
            continue

        if etait_en_panne:
            retablissements.append(nom)

    return nouvel_etat, nouvelles_pannes, retablissements


def enregistrer_chute_candidate(
    etat,
    nom,
    nombre,
    precedent,
    signature=None,
    raison="catalogue",
):
    entree_precedente = etat.get(nom, {})
    dernier_nombre = int(entree_precedente.get("count", -1))
    tolerance = max(2, round(max(nombre, dernier_nombre, 1) * 0.10))
    meme_signature = (
        bool(signature)
        and signature == entree_precedente.get("signature")
        and raison == entree_precedente.get("reason")
    )

    if meme_signature or (
        not signature
        and dernier_nombre >= 0
        and abs(nombre - dernier_nombre) <= tolerance
    ):
        confirmations = int(entree_precedente.get("confirmations", 0)) + 1
    else:
        confirmations = 1

    etat[nom] = {
        "count": int(nombre),
        "previous_count": int(precedent),
        "confirmations": confirmations,
        "signature": signature or "",
        "reason": raison,
    }
    return confirmations
