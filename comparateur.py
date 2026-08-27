import json
import re
from urllib.parse import urlparse

from cible import CIBLE_PRIORITAIRE, est_cible_prioritaire


CONFIG_FILE = "config.json"
PRIORITY_SET_BONUS = 1000


def charger_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fichier:
            return json.load(fichier)
    except FileNotFoundError:
        return {}


def detect_category(name):
    name = name.upper()

    if "CASE" in name:
        return "CASE"

    if (
        "DISPLAY" in name
        or "BOOSTER BOX" in name
        or "BOÎTE DE BOOSTERS" in name
        or "BOITE DE BOOSTERS" in name
        or re.search(
            r"\bBO[IÎ]TE\s+DE\s+\d+\s+(?:EXTRA\s+|PREMIUM\s+)?BOOSTERS?\b",
            name,
        )
    ):
        return "DISPLAY"

    if "PRB" in name or "PREMIUM BOOSTER" in name:
        return "PRB"

    if any(
        marqueur in name
        for marqueur in (
            "PREMIUM CARD",
            "ANNIVERSARY",
            "ANNIVERSAIRE",
            "COLLECTION",
            "GOODS SET",
            "PLAYMAT",
            "BINDER",
            "CARTE PROMO",
            "CARTE PROMOTIONNELLE",
            "PROMO CARD",
            "PROMOTIONAL CARD",
        )
    ):
        return "PROMO"

    if "CARTON" in name or "BLISTER" in name or "SLEEVED BOOSTER" in name:
        return "BOOSTER_CARTON"

    if "DOUBLE PACK" in name or "DP-" in name:
        return "DOUBLE_PACK"

    if "STARTER" in name or "ST-" in name or "DECK" in name:
        return "STARTER"

    return "OTHER"


def detect_language(name):
    name = str(name or "").upper()

    if (
        "FRANCAISE" in name
        or "FRANÇAISE" in name
        or "FRANCAIS" in name
        or "FRANÇAIS" in name
        or "FRENCH" in name
        or re.search(r"(?:^|[^A-Z])VF(?:[^A-Z]|$)", name)
    ):
        return "VF"

    if (
        "ANGLAISE" in name
        or "ANGLAIS" in name
        or "ENGLISH" in name
        or re.search(r"(?:^|[^A-Z])ENG(?:[^A-Z]|$)", name)
        or re.search(r"(?:^|[^A-Z])EN(?:[^A-Z]|$)", name)
    ):
        return "EN"

    if (
        "JAPONAISE" in name
        or "JAPONAIS" in name
        or "JAPANESE" in name
        or re.search(r"(?:^|[^A-Z])JP(?:[^A-Z]|$)", name)
    ):
        return "JP"

    return "OTHER"


def est_op17(name):
    """Alias historique conservé pour les tests et appels existants."""
    return est_cible_prioritaire(name)


def enrichir_produit(produit, config):
    name = produit.get("name", "")
    category = detect_category(name)
    langues_configurees = config.get("priority", {}).get("languages", {})
    language = produit.get("language")

    if language not in langues_configurees:
        language = detect_language(name)

    category_score = (
        config.get("priority", {}).get("categories", {}).get(category, 0)
    )
    language_score = langues_configurees.get(language, 0)
    priorite_cible = est_cible_prioritaire(name)

    produit["category"] = category
    produit["language"] = language
    produit["priority_target"] = CIBLE_PRIORITAIRE if priorite_cible else ""
    produit["priority"] = (
        category_score
        + language_score
        + (PRIORITY_SET_BONUS if priorite_cible else 0)
    )
    return produit


def alerte_disponibilite_autorisee(produit):
    if produit.get("site") != "Premium Bandai US":
        return True
    return produit.get("orderable") is True


def est_alerte_statut(status):
    return status in ["AVAILABLE", "PREORDER", "COMING_SOON"]


def normaliser_lien(lien):
    if not lien:
        return ""
    parsed_url = urlparse(str(lien))
    path = parsed_url.path.strip("/")
    return path or str(lien).strip("/")


def creer_index_liens(produits):
    index = {}
    for lien, produit in produits.items():
        lien_normalise = normaliser_lien(lien)
        if lien_normalise:
            index[lien_normalise] = produit
    return index


def utilise_anciens_liens_ultrajeux(boutique, ancien_boutique):
    if boutique != "UltraJeux":
        return False
    return any(
        not str(lien).startswith(("https://", "http://"))
        for lien in ancien_boutique
    )


def ajouter_alerte(alertes, produit, boutique, type_alerte, message_log):
    produit["type_alerte"] = type_alerte
    produit["boutique"] = boutique
    alertes.append(produit)
    print(message_log, produit.get("name", "Produit inconnu"))


def disponibilite_normalisee(produit):
    return re.sub(
        r"\s+",
        " ",
        str(produit.get("availability", "") or ""),
    ).strip().casefold()


def comparer(nouveau):
    config = charger_config()

    try:
        with open("ancien_stock.json", "r", encoding="utf-8") as fichier:
            ancien = json.load(fichier)
    except FileNotFoundError:
        ancien = {}

    alertes = []
    print("🔎 Comparaison du stock")
    print("--------------------")

    for boutique, produits in nouveau.items():
        initialisation_boutique = boutique not in ancien
        ancien_boutique = ancien.get(boutique, {})
        ancien_index = creer_index_liens(ancien_boutique)
        migration_ultrajeux = utilise_anciens_liens_ultrajeux(
            boutique,
            ancien_boutique,
        )

        if migration_ultrajeux:
            print("🔧 Migration des liens UltraJeux")
        if initialisation_boutique:
            print("🧱 Initialisation de la boutique :", boutique)

        for lien, produit in produits.items():
            produit = enrichir_produit(produit, config)
            ancien_produit = ancien_boutique.get(lien)

            if ancien_produit is None:
                ancien_produit = ancien_index.get(normaliser_lien(lien))

            nouveau_status = produit.get("status")
            alerte_referencement_forcee = (
                bool(produit.get("notify_when_referenced"))
                or est_cible_prioritaire(produit.get("name", ""))
            )

            if ancien_produit is None:
                if migration_ultrajeux:
                    print(
                        "🧱 Référence ajoutée sans alerte :",
                        produit.get("name", "Produit inconnu"),
                    )
                    continue

                if (
                    initialisation_boutique
                    and nouveau_status != "COMING_SOON"
                    and not alerte_referencement_forcee
                ):
                    print(
                        "🧱 Référence ajoutée sans alerte :",
                        produit.get("name", "Produit inconnu"),
                    )
                    continue

                if (
                    (
                        est_alerte_statut(nouveau_status)
                        and alerte_disponibilite_autorisee(produit)
                    )
                    or alerte_referencement_forcee
                ):
                    if nouveau_status == "PREORDER":
                        ajouter_alerte(
                            alertes,
                            produit,
                            boutique,
                            "NOUVELLE PRÉCOMMANDE",
                            "🟣 PRÉCOMMANDE :",
                        )
                    elif (
                        nouveau_status == "COMING_SOON"
                        or nouveau_status not in {"AVAILABLE", "PREORDER"}
                    ):
                        ajouter_alerte(
                            alertes,
                            produit,
                            boutique,
                            "NOUVEAU PRODUIT RÉFÉRENCÉ",
                            "🟠 RÉFÉRENCÉ :",
                        )
                    else:
                        ajouter_alerte(
                            alertes,
                            produit,
                            boutique,
                            "NOUVEAU PRODUIT DISPONIBLE",
                            "🟢 DISPONIBLE :",
                        )
                continue

            if (
                est_alerte_statut(nouveau_status)
                and not alerte_disponibilite_autorisee(produit)
                and not est_cible_prioritaire(produit.get("name", ""))
            ):
                print(
                    "🔕 Premium Bandai non commandable :",
                    produit.get("name", "Produit inconnu"),
                )
                continue

            ancien_status = ancien_produit.get("status")

            if ancien_status == "COMING_SOON" and nouveau_status == "AVAILABLE":
                ajouter_alerte(
                    alertes,
                    produit,
                    boutique,
                    "PRODUIT ANNONCÉ MAINTENANT DISPONIBLE",
                    "🟢 DISPONIBLE APRÈS ANNONCE :",
                )
            elif ancien_status == "PREORDER" and nouveau_status == "AVAILABLE":
                ajouter_alerte(
                    alertes,
                    produit,
                    boutique,
                    "PRÉCOMMANDE MAINTENANT DISPONIBLE",
                    "🟢 DISPONIBLE APRÈS PRÉCOMMANDE :",
                )
            elif ancien_status != "AVAILABLE" and nouveau_status == "AVAILABLE":
                ajouter_alerte(
                    alertes,
                    produit,
                    boutique,
                    "RETOUR EN STOCK",
                    "🔄 RETOUR EN STOCK :",
                )
            elif ancien_status != "PREORDER" and nouveau_status == "PREORDER":
                ajouter_alerte(
                    alertes,
                    produit,
                    boutique,
                    "NOUVELLE PRÉCOMMANDE",
                    "🟣 PRÉCOMMANDE :",
                )
            elif ancien_status != "COMING_SOON" and nouveau_status == "COMING_SOON":
                ajouter_alerte(
                    alertes,
                    produit,
                    boutique,
                    "PRODUIT DÉSORMAIS ANNONCÉ",
                    "🟠 ANNONCÉ :",
                )
            elif (
                ancien_status in {"COMING_SOON", "PREORDER", "SOLD OUT"}
                and nouveau_status in {"COMING_SOON", "PREORDER", "SOLD OUT"}
                and disponibilite_normalisee(ancien_produit)
                != disponibilite_normalisee(produit)
                and disponibilite_normalisee(produit)
            ):
                ajouter_alerte(
                    alertes,
                    produit,
                    boutique,
                    "DATE DE DISPONIBILITÉ MISE À JOUR",
                    "📅 DISPONIBILITÉ MODIFIÉE :",
                )

    print("--------------------")
    print("✅ Comparaison terminée")
    alertes.sort(key=lambda produit: produit.get("priority", 0), reverse=True)
    return alertes
