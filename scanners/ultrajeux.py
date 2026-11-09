from urllib.parse import parse_qs, urljoin, urlsplit
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

import re

from confirmation import normaliser_statut_schema
from observabilite import noter_requete
from scanners.politique import produit_autorise


BASE_URL = "https://www.ultrajeux.com/"


URL_TEMPLATE = (
    "https://www.ultrajeux.com/"
    "cat.php?cat=0&jeu=1031&page={}"
)


TIN_PACK_TS03 = {
    33535: "monkey-d-luffy-v1",
    33536: "monkey-d-luffy-v2",
    33537: "shanks-v1",
    33538: "shanks-v2",
    33539: "boa-hancock-v2",
    33540: "boa-hancock-v1",
}


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
        "DEVIL FRUITS COLLECTION",
        "TIN PACK",
        "MINI-TIN",
        "MINI TIN",
    ]

    if any(
        keyword in name
        for keyword in tcg_keywords
    ):

        return True

    product_code = re.search(
        r"\b(?:OP|EB|ST|PRB|DF|DP|TS)\s*-?\s*\d{2}\b",
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


def detect_status(text, orderable=False, today=None):

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

    release = re.search(r"SORTIE\s+LE\s+(\d{2}/\d{2}/\d{4})", text)
    if release:
        if not orderable:
            return "COMING_SOON"
        try:
            release_date = datetime.strptime(release.group(1), "%d/%m/%Y").date()
        except ValueError:
            return "UNKNOWN"
        today = today or datetime.now(ZoneInfo("Europe/Paris")).date()
        return "PREORDER" if release_date > today else "AVAILABLE"

    if orderable:
        return "AVAILABLE"

    return "UNKNOWN"


def can_order(parent):
    """Only a live add-to-cart control is evidence of an online order."""
    for control in parent.select('input[type="submit"], button'):
        label = control.get("value", "") + " " + control.get_text(" ", strip=True)
        form = control.find_parent("form")
        if (
            "AJOUTER" in label.upper()
            and not control.has_attr("disabled")
            and control.get("aria-disabled") != "true"
            and form is not None
            and form.select_one('input[name="op"][value="danspanier"]')
        ):
            return True
    return False


def extract_image(link, parent):
    # The language flag precedes the product photo in UltraJeux cards.
    candidates = (
        parent.select("img.produit_scan, .image img")
        + link.find_all("img")
        + parent.find_all("img")
    )
    for image_element in candidates:
        image_url = image_element.get("data-src") or image_element.get("src") or ""
        if not image_url:
            continue
        if any(marker in image_url.lower() for marker in ("/pays/", "icon_")):
            continue
        return urljoin(BASE_URL, image_url)
    return ""


def extract_tin_detail(html, url):
    soup = BeautifulSoup(html, "lxml")
    name_element = soup.select_one('h1[itemprop="name"]')
    offer = soup.select_one('form[itemprop="offers"]')
    if name_element is None or offer is None:
        raise ValueError("Fiche produit UltraJeux incomplète")

    name = name_element.get_text(" ", strip=True)
    availability = offer.select_one('[itemprop="availability"][content]')
    status = normaliser_statut_schema(availability["content"]) if availability else None
    if not status or not re.search(r"\bTS[- ]?03\b", name, re.I):
        raise ValueError("Identité ou disponibilité TS-03 non vérifiable")
    if status in {"AVAILABLE", "PREORDER"} and not can_order(offer):
        status = "STORE_ONLY" if status == "AVAILABLE" else "COMING_SOON"

    image = soup.select_one('meta[itemprop="image"][content]')
    return {
        "site": "UltraJeux",
        "name": name,
        "price": extract_price(offer.get_text(" ", strip=True)),
        "status": status,
        "priority": get_priority(name),
        "link": url,
        "image": urljoin(BASE_URL, image["content"]) if image else "",
    }


def add_missing_tins(products):
    listed_ids = {
        match.group(1)
        for url in products
        if (match := re.search(r"/produit-(\d+)", urlsplit(url).path))
    }
    for product_id, variant in TIN_PACK_TS03.items():
        if str(product_id) in listed_ids:
            continue
        url = urljoin(
            BASE_URL,
            f"produit-{product_id}-ts03-tin-pack-{variant}-4582770066807.html",
        )
        try:
            noter_requete()
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            products[url] = extract_tin_detail(response.content, url)
            print(f"🔍 UltraJeux TS-03 hors catalogue : {product_id} | {products[url]['status']}")
        except (requests.RequestException, ValueError) as error:
            print(f"⚠️ UltraJeux TS-03 : fiche {product_id} indisponible ({error})")


def has_next_page(soup, page_number):
    for link in soup.select('a[href*="page="]'):
        url = urlsplit(urljoin(BASE_URL, link["href"]))
        if url.netloc != urlsplit(BASE_URL).netloc or url.path != "/cat.php":
            continue
        params = parse_qs(url.query)
        if (
            params.get("cat") == ["0"]
            and params.get("jeu") == ["1031"]
            and params.get("page") == [str(page_number + 1)]
        ):
            return True
    return False


def scan():

    products = {}

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        for page_number in range(1, 51):

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
                    product_text,
                    orderable=can_order(parent),
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

            if not has_next_page(soup, page_number):
                break
        else:
            raise RuntimeError("La pagination UltraJeux dépasse la limite de sécurité")

        browser.close()

    if products:
        add_missing_tins(products)
    return products
