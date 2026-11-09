import json
import re


CONFIG_FILE = "config.json"


def charger_cible_prioritaire(chemin=CONFIG_FILE):
    try:
        with open(chemin, "r", encoding="utf-8") as fichier:
            config = json.load(fichier)
    except FileNotFoundError:
        return None

    valeur = config.get("priority_set")
    if valeur is None:
        return None

    cible = str(valeur).strip().upper()
    if not re.fullmatch(r"[A-Z]{1,4}\s*-?\s*\d{2}", cible):
        raise RuntimeError(f"Cible prioritaire invalide dans {chemin}: {cible}")

    return re.sub(r"[\s-]+", "", cible)


CIBLE_PRIORITAIRE = charger_cible_prioritaire()


def motif_cible(cible=None):
    cible = CIBLE_PRIORITAIRE if cible is None else cible
    if cible is None:
        return None
    cible = str(cible).strip().upper()
    correspondance = re.fullmatch(r"([A-Z]{1,4})\s*-?\s*(\d{2})", cible)
    if correspondance is None:
        raise RuntimeError(f"Cible prioritaire invalide: {cible}")

    prefixe, numero = correspondance.groups()
    return rf"\b{re.escape(prefixe)}\s*-?\s*{numero}\b"


def est_cible_prioritaire(texte, cible=None):
    motif = motif_cible(cible)
    return motif is not None and re.search(
        motif,
        str(texte or ""),
        flags=re.IGNORECASE,
    ) is not None
