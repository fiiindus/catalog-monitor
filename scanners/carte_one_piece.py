import json
import re
from datetime import date
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from cible import CIBLE_PRIORITAIRE, est_cible_prioritaire
from observabilite import noter_requete
from scanners.politique import produit_autorise


BASE_URL = "https://carteonepiece.fr"
PREORDER_URL = "https://carteonepiece.fr/pages/articles-en-precommandes"
PRIORITY_SEARCH_URL = (
    "https://carteonepiece.fr/search"
    f"?q={quote('title:' + CIBLE_PRIORITAIRE)}&type=product"
)

EMPTY_PREORDER_MARKERS = (
    "AUCUNE PRÉCOMMANDE EN COURS",
    "AUCUNE PRECOMMANDE EN COURS",
)
NO_SEARCH_RESULT_MARKERS = (
    "AUCUN RÉSULTAT TROUVÉ",
    "AUCUN RESULTAT TROUVE",
)

EXCLUDED_PRODUCT_MARKERS = (
    "FIGURE", "FIGURINE", "PELUCHE", "PLUSH", "T-SHIRT", "VÊTEMENT",
    "VETEMENT", "CARTE À L'UNITÉ", "CARTE A L'UNITE", "CARTE INDIVIDUELLE",
    "CARTE SEULE", "CARTE GRADÉE", "CARTE GRADEE", "CARTE LEADER",
    "CARTE PERSONNAGE", "CARTE ÉVÈNEMENT", "CARTE EVENEMENT", "CARTE EVENT",
    "PARALLÈLE", "PARALLELE", "BGS ", "PSA ", "CGC ",
)
ACCESSORY_MARKERS = (
    "TAPIS DE JEU", "PLAYMAT", "PROTÈGE-CARTES", "PROTEGE-CARTES",
    "PROTECTIONS DE CARTES", "CARD SLEEVES", "SLEEVES",
)
PROMO_CARD_MARKERS = (
    "CARTE PROMO", "CARTE PROMOTIONNELLE", "CARTE EXCLUSIVE", "PROMO CARD",
    "PROMOTIONAL CARD", "EXCLUSIVE CARD", "INCLUT UNE CARTE", "AVEC CARTE",
    "INCLUDES CARD", "WITH CARD",
)
SEALED_PRODUCT_MARKERS = (
    "DISPLAY", "BOOSTER BOX", "BOOSTER", "DOUBLE PACK", "STARTER DECK",
    "DECK SET", "DECK DE DÉMARRAGE", "DECK DE DEMARRAGE", "BLISTER",
    "COFFRET", "COLLECTION", "GOODS SET", "PREMIUM CARD", "DEVIL FRUIT",
    "BOÎTE", "BOITE", "CARTON", "CASE",
)
EXCLUDED_LANGUAGE_MARKERS = (
    "JAPONAIS", "JAPONAISE", "JAPANESE", " JAP ", "CHINOIS", "CHINOISE",
    "CHINESE", "CORÉEN", "COREEN", "KOREAN",
)

MONTHS = {
    "JANVIER": 1, "FÉVRIER": 2, "FEVRIER": 2, "MARS": 3, "AVRIL": 4,
    "MAI": 5, "JUIN": 6, "JUILLET": 7, "AOÛT": 8, "AOUT": 8,
    "SEPTEMBRE": 9, "OCTOBRE": 10, "NOVEMBRE": 11, "DÉCEMBRE": 12,
    "DECEMBRE": 12,
}
MONTH_PATTERN = "|".join(sorted(MONTHS, key=len, reverse=True))


def nettoyer_texte(texte):
    return re.sub(r"\s+", " ", str(texte or "").replace("\u00a0", " ")).strip()


def normaliser_lien_produit(lien):
    lien_absolu = urljoin(BASE_URL, str(lien or ""))
    parties = urlsplit(lien_absolu)
    if "/products/" not in parties.path:
        return ""
    return urlunsplit((
        parties.scheme,
        parties.netloc,
        parties.path.rstrip("/"),
        "",
        "",
    ))


def extraire_liens_produits(html_page):
    soup = BeautifulSoup(html_page, "lxml")
    zone_principale = soup.select_one("main") or soup
    liens = []
    for element in zone_principale.select('a[href*="/products/"]'):
        lien = normaliser_lien_produit(element.get("href", ""))
        if lien and lien not in liens:
            liens.append(lien)
    return liens


def page_precommandes_vide(html_page):
    texte = nettoyer_texte(
        BeautifulSoup(html_page, "lxml").get_text(" ", strip=True)
    ).upper()
    return any(marqueur in texte for marqueur in EMPTY_PREORDER_MARKERS)


def recherche_sans_resultat(html_page):
    texte = nettoyer_texte(
        BeautifulSoup(html_page, "lxml").get_text(" ", strip=True)
    ).upper()
    return any(marqueur in texte for marqueur in NO_SEARCH_RESULT_MARKERS)


def extraire_fermeture(html_page):
    texte = nettoyer_texte(
        BeautifulSoup(html_page, "lxml").get_text(" ", strip=True)
    )
    correspondance = re.search(
        r"BOUTIQUE\s+FERMÉE\s+DU\s+"
        r"(\d{1,2}\s+[A-ZÉÈÊËÀÂÄÎÏÔÖÙÛÜÇ]+)\s+AU\s+"
        r"(\d{1,2}\s+[A-ZÉÈÊËÀÂÄÎÏÔÖÙÛÜÇ]+\s+20\d{2})",
        texte,
        flags=re.IGNORECASE,
    )
    if not correspondance:
        return ""
    return nettoyer_texte(correspondance.group(1)) + " au " + nettoyer_texte(
        correspondance.group(2)
    )


def iterer_objets_json(valeur):
    if isinstance(valeur, dict):
        yield valeur
        for enfant in valeur.values():
            yield from iterer_objets_json(enfant)
    elif isinstance(valeur, list):
        for enfant in valeur:
            yield from iterer_objets_json(enfant)


def extraire_produit_json_ld(html_page):
    soup = BeautifulSoup(html_page, "lxml")
    for script in soup.select('script[type="application/ld+json"]'):
        contenu = script.string or script.get_text()
        if not contenu:
            continue
        try:
            donnees = json.loads(contenu)
        except json.JSONDecodeError:
            continue
        for objet in iterer_objets_json(donnees):
            if (
                objet.get("@type") == "Product"
                and objet.get("name")
                and objet.get("offers")
            ):
                return objet
    return {}


def normaliser_offres(produit_json):
    offres = produit_json.get("offers", [])
    if isinstance(offres, dict):
        return [offres]
    if isinstance(offres, list):
        return [offre for offre in offres if isinstance(offre, dict)]
    return []


def offre_en_stock(produit_json):
    disponibilites = [
        str(offre.get("availability", "")).upper()
        for offre in normaliser_offres(produit_json)
    ]
    if any("INSTOCK" in disponibilite for disponibilite in disponibilites):
        return True
    if any("OUTOFSTOCK" in disponibilite for disponibilite in disponibilites):
        return False
    return None


def extraire_prix(produit_json):
    prix = []
    for offre in normaliser_offres(produit_json):
        try:
            prix.append(float(offre.get("price")))
        except (TypeError, ValueError):
            continue
    if not prix:
        return "Non disponible"
    return f"{min(prix):.2f} €".replace(".", ",")


def extraire_disponibilite(description):
    texte = nettoyer_texte(description)
    correspondance = re.search(
        r"(?:DATE\s+DE\s+SORTIE|SORTIE\s+PRÉVUE|SORTIE\s+PREVUE|"
        r"DISPONIBILITÉ|DISPONIBILITE)\s*:?\s*"
        r"((?:FIN\s+|DÉBUT\s+|DEBUT\s+|COURANT\s+)?(?:[0-3]?\d\s+)?"
        rf"(?:{MONTH_PATTERN})(?:\s+20\d{{2}})?)",
        texte,
        flags=re.IGNORECASE,
    )
    return nettoyer_texte(correspondance.group(1)) if correspondance else ""


def date_encore_a_venir(disponibilite):
    disponibilite = nettoyer_texte(disponibilite).upper()
    correspondance = re.search(
        rf"(?:(\d{{1,2}})\s+)?({MONTH_PATTERN})\s+(20\d{{2}})",
        disponibilite,
        flags=re.IGNORECASE,
    )
    if not correspondance:
        return False
    jour = int(correspondance.group(1) or 28)
    mois = MONTHS[correspondance.group(2).upper()]
    annee = int(correspondance.group(3))
    return (annee, mois, jour) >= (date.today().year, date.today().month, date.today().day)


def detecter_langue(texte):
    texte = " " + nettoyer_texte(texte).upper() + " "
    if " ANGLAIS " in texte or " ENGLISH " in texte or " ENG " in texte:
        return "EN"
    if (
        " FRANÇAIS " in texte
        or " FRANCAIS " in texte
        or " FRENCH " in texte
        or " VF " in texte
        or " FR " in texte
    ):
        return "VF"
    return "OTHER"


def produit_surveille(nom, description=""):
    if not produit_autorise(nom, description):
        return False

    texte = " " + nettoyer_texte(nom + " " + description).upper() + " "
    signature_tcg = (
        "ONE PIECE" in texte
        or re.search(r"\b(?:OP|EB|PRB|ST|DP|DF|LD)\s*-?\s*\d{2}\b", texte)
        is not None
    )
    if not signature_tcg:
        return False
    if any(marqueur in texte for marqueur in EXCLUDED_LANGUAGE_MARKERS):
        return False
    if any(marqueur in texte for marqueur in EXCLUDED_PRODUCT_MARKERS):
        return False
    if re.search(r"\b(?:OP|EB|PRB)\d{2}-\d{3}\b", texte):
        return False

    est_accessoire = any(marqueur in texte for marqueur in ACCESSORY_MARKERS)
    contient_carte_promo = any(marqueur in texte for marqueur in PROMO_CARD_MARKERS)
    if est_accessoire and not contient_carte_promo:
        return False

    est_produit_scelle = any(
        marqueur in texte for marqueur in SEALED_PRODUCT_MARKERS
    )
    return est_produit_scelle or contient_carte_promo


def detecter_statut(produit_json, source_precommandes, disponibilite=""):
    en_stock = offre_en_stock(produit_json)
    texte = nettoyer_texte(
        str(produit_json.get("name", ""))
        + " "
        + str(produit_json.get("description", ""))
    ).upper()
    est_precommande = (
        source_precommandes
        or "PRÉCOMMANDE" in texte
        or "PRECOMMANDE" in texte
        or date_encore_a_venir(disponibilite)
    )

    if en_stock is True:
        return "PREORDER" if est_precommande else "AVAILABLE"
    if en_stock is False:
        return "SOLD OUT"
    if est_precommande:
        return "COMING_SOON"
    return "UNKNOWN"


def charger_produit(page, lien, source_precommandes):
    noter_requete()
    page.goto(lien, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1200)
    produit_json = extraire_produit_json_ld(page.content())
    if not produit_json:
        raise RuntimeError("Données produit Shopify introuvables : " + lien)

    nom = nettoyer_texte(produit_json.get("name", ""))
    description = nettoyer_texte(produit_json.get("description", ""))
    if not produit_surveille(nom, description):
        return None

    disponibilite = extraire_disponibilite(description)
    images = produit_json.get("image", [])
    if isinstance(images, str):
        images = [images]

    lien_canonique = normaliser_lien_produit(produit_json.get("url", lien))
    return {
        "site": "Carte One Piece",
        "name": nom,
        "price": extraire_prix(produit_json),
        "status": detecter_statut(
            produit_json,
            source_precommandes,
            disponibilite,
        ),
        "availability": disponibilite,
        "link": lien_canonique,
        "image": images[0] if images else "",
        "language": detecter_langue(nom + " " + description),
        "description": description,
        "source": "preorder_page" if source_precommandes else "priority_search",
        "notify_when_referenced": True,
    }


def scan():
    produits = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="fr-FR")

        try:
            print("🔎 Carte One Piece : page des précommandes")
            noter_requete()
            page.goto(PREORDER_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1800)
            html_precommandes = page.content()
            liens_precommandes = extraire_liens_produits(html_precommandes)

            if (
                not liens_precommandes
                and not page_precommandes_vide(html_precommandes)
            ):
                raise RuntimeError(
                    "La page de précommandes ne contient ni produit "
                    "ni message d'absence de précommande"
                )

            fermeture = extraire_fermeture(html_precommandes)
            if fermeture:
                print("🏖️ Fermeture annoncée :", fermeture)

            candidats = {lien: True for lien in liens_precommandes}

            print(
                f"🔥 Carte One Piece : recherche directe {CIBLE_PRIORITAIRE}"
            )
            noter_requete()
            page.goto(
                PRIORITY_SEARCH_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )
            page.wait_for_timeout(1400)
            html_prioritaire = page.content()
            liens_prioritaires = extraire_liens_produits(html_prioritaire)

            if (
                not liens_prioritaires
                and not recherche_sans_resultat(html_prioritaire)
            ):
                raise RuntimeError(
                    f"La recherche {CIBLE_PRIORITAIRE} ne contient ni résultat "
                    "ni message d'absence de résultat"
                )

            for lien in liens_prioritaires:
                candidats.setdefault(lien, False)

            for lien, source_precommandes in candidats.items():
                produit = charger_produit(page, lien, source_precommandes)
                if produit is None:
                    continue

                if (
                    not source_precommandes
                    and not est_cible_prioritaire(produit["name"])
                ):
                    continue

                produits[produit["link"]] = produit
                print(
                    "🔍 Produit :",
                    produit["name"],
                    "|",
                    produit["status"],
                    "|",
                    produit["availability"] or "Date non annoncée",
                    "|",
                    produit["price"],
                )
        finally:
            browser.close()

    print("📦 Carte One Piece :", len(produits), "produit(s) surveillé(s)")
    return produits
