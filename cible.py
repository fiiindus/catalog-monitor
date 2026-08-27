import json
import re


CONFIG_FILE = "config.json"
DEFAULT_PRIORITY_SET = "OP17"


def charger_cible_prioritaire(chemin=CONFIG_FILE):
    try:
        with open(chemin, "r", encoding="utf-8") as fichier:
            config = json.load(fichier)
    except FileNotFoundError:
        return DEFAULT_PRIORITY_SET

    cible = str(config.get("priority_set", DEFAULT_PRIORITY_SET)).strip().upper()
    if not re.fullmatch(r"[A-Z]{1,4}\s*-?\s*\d{2}", cible):
        raise RuntimeError(f"Cible prioritaire invalide dans {chemin}: {cible}")

    return re.sub(r"[\s-]+", "", cible)


CIBLE_PRIORITAIRE = charger_cible_prioritaire()


def motif_cible(cible=None):
    cible = str(cible or CIBLE_PRIORITAIRE).strip().upper()
    correspondance = re.fullmatch(r"([A-Z]{1,4})\s*-?\s*(\d{2})", cible)
    if correspondance is None:
        raise RuntimeError(f"Cible prioritaire invalide: {cible}")

    prefixe, numero = correspondance.groups()
    return rf"\b{re.escape(prefixe)}\s*-?\s*{numero}\b"


def est_cible_prioritaire(texte, cible=None):
    return re.search(
        motif_cible(cible),
        str(texte or ""),
        flags=re.IGNORECASE,
    ) is not None
