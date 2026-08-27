import html
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from observabilite import noter_requete
from scanners.politique import produit_autorise


BASE_URL = "https://www.philibertnet.com"

CATEGORY_URL_TEMPLATE = (
    "https://www.philibertnet.com/fr/"
    "17214-one-piece-le-jeu-de-cartes?p={}"
)

MAX_PAGES = 10

EXCLUDED_PRODUCT_MARKERS = (
    "CARTE À L'UNITÉ",
    "CARTE A L'UNITE",
    "CARTES À L'UNITÉ",
    "CARTES A L'UNITE",
    "CARTE INDIVIDUELLE",
    "CARTE SEULE",
    "CARTE GRADÉE",
    "CARTE GRADEE",
    "LOT DE CARTES"
)

ACCESSORY_MARKERS = (
    "TAPIS DE JEU",
    "PLAYMAT",
    "PROTÈGE-CARTES",
    "PROTEGE-CARTES",
    "PROTECTIONS DE CARTES",
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
        str(texte or "").replace(
            "\u00a0",
            " "
        )
    ).strip()


def extraire_datalayer(carte):

    donnees = carte.get(
        "data-datalayer-event",
        ""
    )

    if not donnees:

        return {}

    try:

        return json.loads(
            html.unescape(
                donnees
            )
        )

    except json.JSONDecodeError:

        return {}


def extraire_prix(carte, datalayer=None):

    element_prix = carte.select_one(
        ".product-card__price"
    )

    if element_prix is not None:

        prix = nettoyer_texte(
            element_prix.get_text(
                " ",
                strip=True
            )
        )

        if prix:

            return prix

    datalayer = datalayer or {}

    prix_numerique = datalayer.get(
        "price"
    )

    if isinstance(
        prix_numerique,
        (
            int,
            float
        )
    ):

        return (
            f"{prix_numerique:.2f} €"
            .replace(
                ".",
                ","
            )
        )

    return "Non disponible"


def detecter_langue(texte):

    texte = nettoyer_texte(
        texte
    ).upper()

    if (
        "ANGLAIS" in texte
        or "ANGLAISE" in texte
        or "ENGLISH" in texte
    ):

        return "EN"

    if (
        "FRANÇAIS" in texte
        or "FRANCAIS" in texte
        or "FRANÇAISE" in texte
        or "FRANCAISE" in texte
        or "FRENCH" in texte
    ):

        return "VF"

    return "OTHER"


def langue_valide(texte):

    texte = nettoyer_texte(
        texte
    ).upper()

    if any(
        marqueur in texte
        for marqueur in EXCLUDED_LANGUAGE_MARKERS
    ):

        return False

    code_langue = re.search(
        r"(?:^|[^A-Z])(?:JP|JPN|KR|KOR|CN|CHN)(?:[^A-Z]|$)",
        texte
    )

    return code_langue is None


def produit_surveille(
    nom,
    description="",
    langue=""
):

    if not produit_autorise(
        nom,
        " ".join((description, langue))
    ):

        return False

    texte = nettoyer_texte(
        " ".join(
            [
                nom,
                description,
                langue
            ]
        )
    ).upper()

    if "ONE PIECE" not in texte:

        return False

    if any(
        marqueur in texte
        for marqueur in EXCLUDED_PRODUCT_MARKERS
    ):

        return False

    est_accessoire = any(
        marqueur in texte
        for marqueur in ACCESSORY_MARKERS
    )

    contient_carte_promo = any(
        marqueur in texte
        for marqueur in PROMO_CARD_MARKERS
    )

    if (
        est_accessoire
        and not contient_carte_promo
    ):

        return False

    return langue_valide(
        texte
    )


def detecter_statut(
    texte_labels,
    texte_stock
):

    labels = nettoyer_texte(
        texte_labels
    ).upper()

    stock = nettoyer_texte(
        texte_stock
    ).upper()

    # Philibert affiche aussi un bloc technique "Rupture" sur les
    # références à venir. Le badge visible doit donc toujours primer.
    if (
        "À VENIR" in labels
        or "A VENIR" in labels
    ):

        return "COMING_SOON"

    if (
        "PRÉCOMMANDE" in labels
        or "PRECOMMANDE" in labels
        or "PRÉCOMMANDE" in stock
        or "PRECOMMANDE" in stock
    ):

        return "PREORDER"

    if "EN STOCK" in stock:

        return "AVAILABLE"

    if (
        "RUPTURE" in stock
        or "ÉPUISÉ" in stock
        or "EPUISE" in stock
    ):

        return "SOLD OUT"

    return "UNKNOWN"


def extraire_disponibilite(texte_labels):

    texte = nettoyer_texte(
        texte_labels
    )

    correspondance = re.search(
        r"DISPO\s*:\s*([^|]+)$",
        texte,
        flags=re.IGNORECASE
    )

    if correspondance:

        return nettoyer_texte(
            correspondance.group(1)
        )

    correspondance = re.search(
        r"(?:À|A)\s+VENIR\s*:\s*(.+)$",
        texte,
        flags=re.IGNORECASE
    )

    if correspondance:

        return nettoyer_texte(
            correspondance.group(1)
        )

    return ""


def extraire_image(carte):

    image = carte.select_one(
        ".product-card__thumb"
    )

    if image is None:

        return ""

    source = (
        image.get("src")
        or image.get("data-src")
        or ""
    )

    return urljoin(
        BASE_URL,
        source
    )


def scan():

    produits = {}
    produits_bruts_vus = set()

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            locale="fr-FR"
        )

        try:

            for numero_page in range(
                1,
                MAX_PAGES + 1
            ):

                url_page = CATEGORY_URL_TEMPLATE.format(
                    numero_page
                )

                print(
                    "🔎 Philibert page :",
                    numero_page
                )

                noter_requete()
                page.goto(
                    url_page,
                    wait_until="domcontentloaded",
                    timeout=60000
                )

                page.wait_for_timeout(
                    2500
                )

                soup = BeautifulSoup(
                    page.content(),
                    "lxml"
                )

                cartes_page = soup.select(
                    ".product-card[data-pid]"
                )

                identifiants_page = {
                    carte.get("data-pid", "")
                    for carte in cartes_page
                    if carte.get("data-pid", "")
                }

                nouveaux_produits_bruts = (
                    identifiants_page - produits_bruts_vus
                )

                if not identifiants_page:

                    break

                nouveaux_sur_la_page = 0

                for carte in cartes_page:

                    lien = carte.select_one(
                        "a.product-card__title[href]"
                    )

                    if lien is None:

                        continue

                    nom = nettoyer_texte(
                        lien.get_text(
                            " ",
                            strip=True
                        )
                    )

                    description_element = carte.select_one(
                        ".product-card__description-text"
                    )

                    description = nettoyer_texte(
                        description_element.get_text(
                            " ",
                            strip=True
                        )
                        if description_element is not None
                        else ""
                    )

                    langue_element = carte.select_one(
                        ".product-card__feature"
                    )

                    langue_texte = nettoyer_texte(
                        langue_element.get_text(
                            " ",
                            strip=True
                        )
                        if langue_element is not None
                        else ""
                    )

                    if not produit_surveille(
                        nom,
                        description,
                        langue_texte
                    ):

                        continue

                    url_produit = urljoin(
                        BASE_URL,
                        lien.get(
                            "href",
                            ""
                        )
                    )

                    if url_produit in produits:

                        continue

                    texte_labels = nettoyer_texte(
                        " | ".join(
                            element.get_text(
                                " ",
                                strip=True
                            )
                            for element in carte.select(
                                ".badge-label"
                            )
                        )
                    )

                    stock_element = carte.select_one(
                        ".stock-block"
                    )

                    texte_stock = nettoyer_texte(
                        stock_element.get_text(
                            " ",
                            strip=True
                        )
                        if stock_element is not None
                        else ""
                    )

                    datalayer = extraire_datalayer(
                        carte
                    )

                    statut = detecter_statut(
                        texte_labels,
                        texte_stock
                    )

                    disponibilite = extraire_disponibilite(
                        texte_labels
                    )

                    produits[url_produit] = {
                        "site": "Philibert",
                        "name": nom,
                        "price": extraire_prix(
                            carte,
                            datalayer
                        ),
                        "status": statut,
                        "availability": disponibilite,
                        "link": url_produit,
                        "image": extraire_image(
                            carte
                        ),
                        "language": detecter_langue(
                            langue_texte
                        ),
                        "description": description
                    }

                    nouveaux_sur_la_page += 1

                    print(
                        "🔍 Produit :",
                        nom,
                        "|",
                        statut,
                        "|",
                        disponibilite or "Date non annoncée",
                        "|",
                        produits[url_produit]["price"]
                    )

                print(
                    f"📦 Page {numero_page} : "
                    f"{nouveaux_sur_la_page} produit(s)"
                )

                produits_bruts_vus.update(identifiants_page)

                if not nouveaux_produits_bruts:

                    break

        finally:

            browser.close()

    if not produits:

        raise RuntimeError(
            "Aucun produit One Piece Card Game surveillable "
            "détecté sur Philibert"
        )

    return produits
