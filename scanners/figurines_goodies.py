from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin

from cible import CIBLE_PRIORITAIRE
from observabilite import noter_requete
from scanners.politique import est_op17, produit_autorise


URL = "https://www.figurines-goodies.com/650-carte-a-jouer-one-piece"
BASE_URL = "https://www.figurines-goodies.com"
MAX_PAGES = 10
PRIORITY_SEARCH_URL = (
    "https://www.figurines-goodies.com/"
    f"recherche?controller=search&s={CIBLE_PRIORITAIRE}"
)


def is_valid_language(name):
    name = name.upper()
    excluded = [
        "JAPON",
        "JAPONAISE",
        "JAPONAIS",
        " JP ",
        "CHINOIS",
        "CHINOISE",
        "COREEN",
        "CORÉEN",
        " KR "
    ]
    return not any(word in name for word in excluded)


def is_tcg_product(name):
    if not produit_autorise(name):
        return False

    name = name.upper()
    keywords = [
        "BOOSTER",
        "DISPLAY",
        "STARTER",
        "DECK",
        "DOUBLE PACK",
        "PREMIUM",
        "CARD",
        "ANNIVERSARY",
        "PRB",
        "OP-",
        "ST-"
    ]
    return any(key in name for key in keywords)


def get_priority(name):
    name = name.upper()
    if "DISPLAY" in name:
        return 1
    if "PRB" in name or "PREMIUM BOOSTER" in name:
        return 2
    if "PREMIUM CARD" in name or "ANNIVERSARY" in name:
        return 3
    if "DOUBLE PACK" in name:
        return 4
    if "STARTER" in name or "DECK" in name:
        return 5
    if "CASE" in name:
        return 6
    return 99


def extract_price(text):
    prices = re.findall(r'\d+[,.]?\d*\s*€', text)
    return prices[0] if prices else "Non trouvé"


def clean_name(name):
    stop_words = [
        "Redécouvrez",
        "Découvrez",
        "Ajoutez",
        "Renforcez",
        "Propulsez",
        "Invoquez",
        "Prenez",
        "Libérez",
        "Liberez",
        "Congelez",
        "Anticipez",
        "Imposez",
        "Maximisez",
        "Dominez",
        "Incarnez",
        "Préparez",
        "Hissez",
        "Le choix",
        "L'occasion",
        "Un format",
        "Une sélection",
        "Attention",
        "Licence",
        "Série",
        "Contenu",
        "Langue",
        "État"
    ]

    for word in stop_words:
        if word in name:
            return name.split(word)[0].strip()
    return name


def _scan_sans_pagination():
    products = {}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        noter_requete()
        page.goto(URL, wait_until="networkidle", timeout=60000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "lxml")
    for link in soup.find_all("a", href=True):
        href = link["href"]
        name = link.get_text(" ", strip=True)
        if not name or "ONE PIECE" not in name.upper():
            continue
        if not is_tcg_product(name) or not is_valid_language(name):
            continue

        name = clean_name(name)
        href = urljoin(BASE_URL, href)
        parent = link.parent
        text = parent.get_text(" ", strip=True)
        text_upper = text.upper()

        if "RUPTURE DE STOCK" in text_upper:
            status = "SOLD OUT"
        elif "PRÉCOMMANDE" in text_upper or "PRECOMMANDE" in text_upper:
            status = "PREORDER"
        elif "DISPONIBLE" in text_upper or "JE CRAQUE" in text_upper:
            status = "AVAILABLE"
        else:
            status = "UNKNOWN"

        img = link.find("img")
        image = urljoin(BASE_URL, img.get("src", "")) if img else ""
        products[href] = {
            "site": "Figurines Goodies",
            "name": name,
            "price": extract_price(text),
            "status": status,
            "priority": get_priority(name),
            "link": href,
            "image": image
        }

    return products


def extraire_page(html, products, seulement_op17=False):
    soup = BeautifulSoup(html, "lxml")
    liens_bruts = set()

    for link in soup.find_all("a", href=True):
        name = link.get_text(" ", strip=True)
        if not name or "ONE PIECE" not in name.upper():
            continue

        if seulement_op17 and not est_op17(name):
            continue

        href = urljoin(BASE_URL, link.get("href", ""))
        if not href:
            continue

        liens_bruts.add(href)

        if not is_tcg_product(name) or not is_valid_language(name):
            continue

        name = clean_name(name)
        parent = link.parent
        text = parent.get_text(" ", strip=True)
        text_upper = text.upper()

        if "RUPTURE DE STOCK" in text_upper:
            status = "SOLD OUT"
        elif "PRÉCOMMANDE" in text_upper or "PRECOMMANDE" in text_upper:
            status = "PREORDER"
        elif "DISPONIBLE" in text_upper or "JE CRAQUE" in text_upper:
            status = "AVAILABLE"
        else:
            status = "UNKNOWN"

        img = link.find("img")
        image = ""
        if img:
            image = urljoin(
                BASE_URL,
                img.get("data-src") or img.get("src") or ""
            )

        products[href] = {
            "site": "Figurines Goodies",
            "name": name,
            "price": extract_price(text),
            "status": status,
            "priority": get_priority(name),
            "link": href,
            "image": image
        }

    return liens_bruts


def scan():
    products = {}
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
                    URL if numero_page == 1 else f"{URL}?page={numero_page}",
                    False
                )
                for numero_page in range(1, MAX_PAGES + 1)
            ]

            for etiquette_page, url_page, sonde_prioritaire in pages_a_scanner:
                print("🔎 Figurines Goodies page :", etiquette_page)
                noter_requete()
                page.goto(
                    url_page,
                    wait_until="domcontentloaded",
                    timeout=60000
                )
                page.wait_for_timeout(2500)

                liens_bruts_page = extraire_page(
                    page.content(),
                    products,
                    seulement_op17=sonde_prioritaire
                )
                nouveaux_liens = liens_bruts_page - liens_bruts_vus

                if not liens_bruts_page or not nouveaux_liens:
                    if sonde_prioritaire:
                        continue
                    break

                liens_bruts_vus.update(liens_bruts_page)
        finally:
            browser.close()

    if not products:
        raise RuntimeError(
            "Aucun produit One Piece Card Game surveillable "
            "détecté sur Figurines Goodies"
        )

    return products
