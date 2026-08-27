from urllib.parse import urljoin

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

import re

from observabilite import noter_requete
from scanners.politique import produit_autorise


BASE_URL = "https://www.ultrajeux.com/"


URL_TEMPLATE = (
    "https://www.ultrajeux.com/"
    "cat.php?cat=0&jeu=1031&page={}"
)


def is_valid_language(name):

    name = name.upper()

    excluded_languages = [
        "JAPON",
        "JAPONAISE",
        "JAPONAIS",
        "JAPANESE",
        " JP ",
        "CHINOIS",
        "CHINOISE",
        "CHINESE",
        "CORÉEN",
        "COREEN",
        "KOREAN",
        " KR "
    ]

    return not any(
        word in name
        for word in excluded_languages
    )


def is_tcg_product(name):

    if not produit_autorise(name):

        return False

    name = name.upper()

    excluded_products = [
        "PUZZLE",
        "SAC À DOS",
        "SAC A DOS",
        "SACOCHE",
        "PORTEFEUILLE",
        "CAHIER",
        "TATOUAGE",
        "POSTER",
        "BOÎTE À COOKIES",
        "BOITE À COOKIES",
        "BOITE A COOKIES",
        "COFFRET CADEAU",
        "PORTE-CLÉS",
        "PORTE-CLES",
        "DRAPEAU",
        "MUG",
        "TOURNOIS"
    ]

    if any(
        word in name
        for word in excluded_products
    ):

        return False

    tcg_keywords = [
        "ONE PIECE CARD GAME",
        "STARTER DECK",
        "ULTRA DECK",
        "LEARN TOGETHER DECK SET",
        "LEARN TO PLAY DECK SET",
        "DOUBLE PACK",
        "BOOSTER BOX",
        "DISPLAY",
        "PREMIUM CARD COLLECTION",
        "PREMIUM BOOSTER",
        "DEVIL FRUITS COLLECTION"
    ]

    if any(
        keyword in name
        for keyword in tcg_keywords
    ):

        return True

    product_code = re.search(
        r"\b(?:OP|EB|ST|PRB|DF|DP)-?\d{2}\b",
        name
    )

    return product_code is not None


def get_priority(name):

    name = name.upper()

    if "DISPLAY" in name:
        return 1

    if (
        "PRB" in name
        or "PREMIUM BOOSTER" in name
    ):
        return 2

    if (
        "PREMIUM" in name
        or "COLLECTION" in name
    ):
        return 3

    if "DOUBLE PACK" in name:
        return 4

    if (
        "STARTER" in name
        or "DECK" in name
    ):
        return 5

    return 99


def extract_price(text):

    prices = re.findall(
        r"\d+[,.]?\d*\s*€",
        text
    )

    if prices:
        return prices[0]

    return "Non trouvé"


def detect_status(text):

    text = text.upper()

    if "DISPONIBLE EN MAGASIN" in text:
        return "STORE_ONLY"

    if (
        "INDISPONIBLE" in text
        or "RUPTURE" in text
    ):
        return "SOLD OUT"

    if (
        "PRÉCOMMANDE" in text
        or "PRECOMMANDE" in text
    ):
        return "PREORDER"

    if "DISPONIBLE" in text:
        return "AVAILABLE"

    return "UNKNOWN"


def extract_image(link, parent):

    image_element = link.find("img")

    if image_element is None:
        image_element = parent.find("img")

    if image_element is None:
        return ""

    image_url = (
        image_element.get("data-src")
        or image_element.get("src")
        or ""
    )

    if not image_url:
        return ""

    return urljoin(
        BASE_URL,
        image_url
    )


def scan():

    products = {}

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        for page_number in range(1, 6):

            page_url = URL_TEMPLATE.format(
                page_number
            )

            print(
                "🔎 UltraJeux page :",
                page_number
            )

            noter_requete()
            page.goto(
                page_url,
                wait_until="networkidle",
                timeout=60000
            )

            page.wait_for_timeout(
                3000
            )

            soup = BeautifulSoup(
                page.content(),
                "lxml"
            )

            links = soup.find_all(
                "a",
                href=True
            )

            page_count = 0

            for link in links:

                href = link.get(
                    "href",
                    ""
                )

                if "produit-" not in href:
                    continue

                product_url = urljoin(
                    BASE_URL,
                    href
                )

                name = link.get_text(
                    " ",
                    strip=True
                )

                if not name:
                    continue

                if not is_tcg_product(name):
                    continue

                if not is_valid_language(name):
                    continue

                parent = link

                for _ in range(3):

                    if parent.parent is not None:
                        parent = parent.parent

                product_text = parent.get_text(
                    " ",
                    strip=True
                )

                status = detect_status(
                    product_text
                )

                price = extract_price(
                    product_text
                )

                image = extract_image(
                    link,
                    parent
                )

                print(
                    "🔍 Produit :",
                    name,
                    "|",
                    status,
                    "|",
                    price
                )

                is_new_product = (
                    product_url not in products
                )

                products[product_url] = {
                    "site": "UltraJeux",
                    "name": name,
                    "price": price,
                    "status": status,
                    "priority": get_priority(name),
                    "link": product_url,
                    "image": image
                }

                if is_new_product:
                    page_count += 1

            print(
                f"📦 Page {page_number} : "
                f"{page_count} produit(s)"
            )

        browser.close()

    return products
