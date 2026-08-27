import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from cible import CIBLE_PRIORITAIRE
from observabilite import noter_requete
from scanners.politique import est_op17, produit_autorise


BASE_URL = "https://www.parkage.com"
SEARCH_URL_TEMPLATE = (
    "https://www.parkage.com/fr/recherche"
    "?category_id=9883"
    "&product_type_id=9885"
    "&product_type_id=9898"
    "&product_type_id=9886"
    "&product_type_id=10585"
    "&page={}"
)
MAX_PAGES = 10
PRIORITY_SEARCH_URL = (
    "https://www.parkage.com/fr/recherche"
    f"?text={CIBLE_PRIORITAIRE}"
)

PRODUCT_PATH_PATTERN = re.compile(r"^/fr/\d+-")

EXCLUDED_TYPE_MARKERS = (
    "CARTE À L'UNITÉ",
    "CARTE A L'UNITE",
    "CARTES À L'UNITÉ",
    "CARTES A L'UNITE",
    "CARTE EXPERTISÉE",
    "CARTE EXPERTISEE",
    "CARTES EXPERTISÉES",
    "CARTES EXPERTISEES",
    "LOT DE CARTES",
    "LOTS DE CARTES"
)

ACCESSORY_MARKERS = (
    "TAPIS DE JEU",
    "PLAYMAT",
    "PROTÈGE-CARTES",
    "PROTEGE-CARTES",
    "CARD SLEEVES",
    "SLEEVES"
)

PROMO_CARD_MARKERS = (
    "CARTE PROMO",
    "CARTE PROMOTIONNELLE",
    "CARTE EXCLUSIVE",
    "PROMO CARD",
    "PROMOTIONAL CARD",
    "EXCLUSIVE CARD",
    "INCLUT UNE CARTE",
    "AVEC CARTE",
    "INCLUDES CARD",
    "WITH CARD"
)

EXCLUDED_LANGUAGE_MARKERS = (
    "JAPONAIS",
    "JAPONAISE",
    "JAPANESE",
    "CHINOIS",
    "CHINOISE",
    "CHINESE",
    "CORÉEN",
    "COREEN",
    "KOREAN"
)


def nettoyer_texte(texte):
    return re.sub(
        r"\s+",
        " ",
        str(texte or "").replace("\u00a0", " ")
    ).strip()


def extraire_prix(texte):
    texte = nettoyer_texte(texte)
    correspondance = re.search(
        r"\d+(?:[ .]\d{3})*(?:[,.]\d{2})?\s*€",
        texte
    )
    return nettoyer_texte(correspondance.group(0)) if correspondance else "Non trouvé"


def extraire_types_produit(carte):
    types = []
    for lien in carte.find_all("a"):
        texte = nettoyer_texte(lien.get_text(" ", strip=True))
        if not texte.upper().startswith("TYPE DE PRODUIT:"):
            continue
        type_produit = nettoyer_texte(texte.split(":", 1)[1])
        if type_produit and type_produit not in types:
            types.append(type_produit)
    return types


def langue_valide(texte):
    texte = nettoyer_texte(texte).upper()
    if any(marqueur in texte for marqueur in EXCLUDED_LANGUAGE_MARKERS):
        return False
    return re.search(
        r"(?:^|[^A-Z])(?:JP|JPN|KR|KOR|CN|CHN)(?:[^A-Z]|$)",
        texte
    ) is None


def detecter_langue(texte):
    texte = nettoyer_texte(texte).upper()
    if "ANGLAIS" in texte or "ANGLAISE" in texte or "ENGLISH" in texte:
        return "EN"
    if (
        "FRANÇAIS" in texte
        or "FRANCAIS" in texte
        or "FRANÇAISE" in texte
        or "FRANCAISE" in texte
        or "FRENCH" in texte
        or " VF " in f" {texte} "
    ):
        return "VF"
    return "VF"


def produit_surveille(nom, texte_carte, types_produit=None):
    types_produit = types_produit or []
    if not produit_autorise(nom, texte_carte, types_produit):
        return False

    texte = nettoyer_texte(
        " ".join([nom, texte_carte, *types_produit])
    ).upper()
    if "ONE PIECE" not in texte:
        return False
    if any(marqueur in texte for marqueur in EXCLUDED_TYPE_MARKERS):
        return False

    est_accessoire = any(marqueur in texte for marqueur in ACCESSORY_MARKERS)
    contient_carte_promo = any(
        marqueur in texte for marqueur in PROMO_CARD_MARKERS
    )
    if est_accessoire and not contient_carte_promo:
        return False
    return langue_valide(texte)


def detecter_statut(texte):
    texte = nettoyer_texte(texte).upper()
    if "RUPTURE DE STOCK" in texte:
        return "SOLD OUT"
    if "PRÉCOMMANDE" in texte or "PRECOMMANDE" in texte:
        return "PREORDER"
    if "SITE INTERNET" in texte:
        return "AVAILABLE"
    if "STOCK BOUTIQUES" in texte:
        return "STORE_ONLY"
    return "UNKNOWN"


def trouver_carte_produit(lien):
    parent = lien
    for _ in range(8):
        parent = parent.parent
        if parent is None:
            return None
        texte = nettoyer_texte(parent.get_text(" ", strip=True))
        if (
            "STOCK BOUTIQUES" in texte.upper()
            and extraire_prix(texte) != "Non trouvé"
        ):
            return parent
    return None


def extraire_image(carte):
    image = carte.find("img")
    if image is None:
        return ""
    source = image.get("src") or image.get("data-src") or ""
    return urljoin(BASE_URL, source)


def scan():
    produits = {}
    liens_bruts_vus = set()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="fr-FR")

        try:
            pages_a_scanner = [
                (CIBLE_PRIORITAIRE, PRIORITY_SEARCH_URL, True)
            ] + [
                (
                    str(numero_page),
                    SEARCH_URL_TEMPLATE.format(numero_page),
                    False
                )
                for numero_page in range(1, MAX_PAGES + 1)
            ]

            for etiquette_page, url_page, sonde_prioritaire in pages_a_scanner:
                print("🔎 Parkage page :", etiquette_page)
                noter_requete()
                page.goto(
                    url_page,
                    wait_until="domcontentloaded",
                    timeout=60000
                )
                page.wait_for_timeout(3500)

                soup = BeautifulSoup(page.content(), "lxml")
                liens_page = soup.find_all("a", href=PRODUCT_PATH_PATTERN)
                liens_bruts_page = {
                    urljoin(BASE_URL, lien.get("href", ""))
                    for lien in liens_page
                }
                nouveaux_liens_bruts = liens_bruts_page - liens_bruts_vus

                if not liens_bruts_page:
                    if sonde_prioritaire:
                        continue
                    break

                nouveaux_sur_la_page = 0
                for lien in liens_page:
                    nom = nettoyer_texte(lien.get_text(" ", strip=True))
                    if not nom:
                        continue
                    if sonde_prioritaire and not est_op17(nom):
                        continue

                    carte = trouver_carte_produit(lien)
                    if carte is None:
                        continue

                    texte_carte = nettoyer_texte(carte.get_text(" ", strip=True))
                    types_produit = extraire_types_produit(carte)
                    if not produit_surveille(nom, texte_carte, types_produit):
                        continue

                    url_produit = urljoin(BASE_URL, lien.get("href", ""))
                    if url_produit in produits:
                        continue

                    statut = detecter_statut(texte_carte)
                    prix = extraire_prix(texte_carte)
                    produits[url_produit] = {
                        "site": "Parkage",
                        "name": nom,
                        "price": prix,
                        "status": statut,
                        "link": url_produit,
                        "image": extraire_image(carte),
                        "language": detecter_langue(texte_carte),
                        "product_types": types_produit
                    }
                    nouveaux_sur_la_page += 1
                    print("🔍 Produit :", nom, "|", statut, "|", prix)

                print(
                    f"📦 Page {etiquette_page} : "
                    f"{nouveaux_sur_la_page} produit(s)"
                )

                liens_bruts_vus.update(liens_bruts_page)
                if not nouveaux_liens_bruts:
                    if sonde_prioritaire:
                        continue
                    break
        finally:
            browser.close()

    if not produits:
        raise RuntimeError(
            "Aucun produit One Piece Card Game surveillable détecté sur Parkage"
        )

    return produits
