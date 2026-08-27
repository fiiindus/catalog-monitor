import re

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin

from observabilite import noter_requete
from scanners.politique import produit_autorise


BASE_URL = "https://p-bandai.com"

URL_TEMPLATE = (
    "https://p-bandai.com/us/series/onepiece-series"
    "?_f_shops=05-0004"
    "&_f_series=03-002"
    "&offset={offset}"
    "&limit={limit}"
    "&sortType=NewArrival"
    "&_f_productStatuses=Waiting,On"
)

PAGE_SIZE = 20
MAX_PAGES = 10

PRODUCT_SELECTOR = ".o-search-product .c-product__link"
PRODUCT_WAIT_TIMEOUT_MS = 30000
FIRST_PAGE_SETTLE_MS = 1000
NEXT_PAGE_SETTLE_MS = 2500
NEXT_PAGE_CHANGE_TIMEOUT_MS = 15000
NEXT_PAGE_POLL_MS = 500
EMPTY_PAGE_CONFIRM_MS = 2000
DETAIL_PAGE_SETTLE_MS = 1500

ACCESSORY_MARKERS = (
    "PLAYMAT",
    "PLAY MAT",
    "PROTÈGE-CARTES",
    "PROTEGE-CARTES",
    "CARD SLEEVES",
    "SLEEVES",
    "DECK BOX",
)

PROMO_CARD_MARKERS = (
    "CARTE PROMO",
    "CARTE PROMOTIONNELLE",
    "CARTE EXCLUSIVE",
    "PROMO CARD",
    "PROMOTIONAL CARD",
    "EXCLUSIVE CARD",
    "INCLUDES CARD",
    "WITH CARD",
)

STATUTS_FERMES = (
    "PRE-ORDER CLOSED",
    "PREORDER CLOSED",
    "PRE-ORDERS CLOSED",
    "PREORDERS CLOSED",
    "ORDERS CLOSED",
    "ORDER CLOSED",
    "SALES ENDED",
    "SALE ENDED",
    "SOLD OUT",
    "OUT OF STOCK",
)

STATUTS_PRECOMMANDE = (
    "PRE-ORDERS OPEN",
    "PREORDERS OPEN",
    "PRE-ORDER OPEN",
    "PREORDER OPEN",
    "PRE-ORDER",
    "PREORDER",
    "ORDERS OPEN",
    "ORDER OPEN",
    "ORDER PERIOD",
    "ACCEPTING ORDERS",
    "ACCEPTING PRE-ORDERS",
)

STATUTS_DISPONIBLES = (
    "IN STOCK",
    "ADD TO CART",
    "BUY NOW",
    "PURCHASE",
    "AVAILABLE NOW",
    "NOW AVAILABLE",
)


def nettoyer_texte(texte):
    texte = str(texte or "")

    for caractere in (
        "\u200b",
        "\u200c",
        "\u200d",
        "\ufeff",
    ):
        texte = texte.replace(caractere, "")

    return re.sub(r"\s+", " ", texte).strip()


def produit_surveille(nom):
    # Premium Bandai est une exception volontaire à la politique générale :
    # les produits officiels scellés asiatiques sont admis. Les cartes à
    # l'unité et accessoires ordinaires restent filtrés.
    if not produit_autorise(
        nom,
        autoriser_langues_asiatiques=True,
    ):
        return False

    texte = nettoyer_texte(nom).upper()

    est_accessoire = any(
        marqueur in texte
        for marqueur in ACCESSORY_MARKERS
    )

    contient_carte_promo = any(
        marqueur in texte
        for marqueur in PROMO_CARD_MARKERS
    )

    return not est_accessoire or contient_carte_promo


def est_commandable(status):
    return status in {
        "AVAILABLE",
        "PREORDER",
    }


def normaliser_prix(texte):
    texte = nettoyer_texte(texte)

    correspondance = re.search(
        r"(?:US)?\$\s*(\d+(?:[.,]\d{2})?)",
        texte,
        re.IGNORECASE,
    )

    if not correspondance:
        return "Non trouvé"

    montant = correspondance.group(1).replace(",", ".")
    return "US$" + montant


def detecter_statut(texte):
    texte = nettoyer_texte(texte).upper()

    # Les mentions fermes doivent être testées avant les expressions
    # génériques contenant PRE-ORDER / ORDER.
    if any(marqueur in texte for marqueur in STATUTS_FERMES):
        return "SOLD OUT"

    if any(marqueur in texte for marqueur in STATUTS_PRECOMMANDE):
        return "PREORDER"

    if any(marqueur in texte for marqueur in STATUTS_DISPONIBLES):
        return "AVAILABLE"

    return "UNKNOWN"


def extraire_statut_element(link):
    # Le texte complet reste la source principale. On ajoute les classes et
    # attributs data/aria car Premium Bandai peut porter l'état dans le DOM
    # sans l'afficher textuellement dans le titre du produit.
    morceaux = [link.get_text(" ", strip=True)]

    for element in [link, *link.find_all(True)]:
        classes = element.get("class", [])
        if classes:
            morceaux.append(" ".join(str(classe) for classe in classes))

        for attribut, valeur in element.attrs.items():
            nom_attribut = str(attribut).lower()
            if (
                nom_attribut.startswith("data-")
                or nom_attribut in {"aria-label", "title"}
            ):
                if isinstance(valeur, (list, tuple)):
                    valeur = " ".join(str(item) for item in valeur)
                morceaux.append(str(valeur))

    return detecter_statut(" ".join(morceaux))


def detecter_statut_detail(html):
    soup = BeautifulSoup(html, "lxml")
    boutons = " ".join(
        bouton.get_text(" ", strip=True)
        for bouton in soup.select("button")
    )
    return detecter_statut(boutons)


def confirmer_disponibilite(produit):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="en-US")
        try:
            noter_requete()
            page.goto(
                produit["link"],
                wait_until="domcontentloaded",
                timeout=60000,
            )
            page.wait_for_timeout(DETAIL_PAGE_SETTLE_MS)
            return detecter_statut_detail(page.content())
        finally:
            browser.close()


def extraire_liens_bruts(html):
    soup = BeautifulSoup(html, "lxml")
    return {
        urljoin(BASE_URL, link.get("href", ""))
        for link in soup.select(PRODUCT_SELECTOR)
        if link.get("href", "")
    }


def extraire_page(html, products):
    soup = BeautifulSoup(html, "lxml")
    links = soup.select(PRODUCT_SELECTOR)
    liens_bruts = set()

    for link in links:
        href = urljoin(BASE_URL, link.get("href", ""))
        if href:
            liens_bruts.add(href)

        name_node = link.select_one(".c-product__title")
        name = nettoyer_texte(
            name_node.get_text(" ", strip=True) if name_node else ""
        )

        if (
            not href
            or "ONE PIECE CARD GAME" not in name.upper()
            or not produit_surveille(name)
        ):
            continue

        status = extraire_statut_element(link)
        price_node = link.select_one(".c-product__price-currency")
        price = normaliser_prix(
            price_node.get_text(" ", strip=True) if price_node else ""
        )

        img = link.find("img")
        image = ""
        if img:
            image = urljoin(
                BASE_URL,
                img.get("src") or img.get("data-src") or "",
            )

        products[href] = {
            "site": "Premium Bandai US",
            "name": name,
            "price": price,
            "status": status,
            "orderable": est_commandable(status),
            "link": href,
            "image": image,
        }

        if status == "UNKNOWN":
            texte_debug = nettoyer_texte(
                link.get_text(" ", strip=True)
            )[:300]
            print(
                "⚠️ Premium Bandai statut UNKNOWN :",
                name,
                "|",
                texte_debug,
            )

    return liens_bruts


def attendre_page_suivante(page, liens_precedents):
    """Attend que le catalogue change réellement ou confirme une page vide."""
    page.wait_for_timeout(NEXT_PAGE_SETTLE_MS)
    ecoule = NEXT_PAGE_SETTLE_MS
    vide_depuis = None
    html = page.content()

    while True:
        liens_courants = extraire_liens_bruts(html)

        if liens_courants and liens_courants != liens_precedents:
            return html

        if not liens_courants:
            if vide_depuis is None:
                vide_depuis = 0
            elif vide_depuis >= EMPTY_PAGE_CONFIRM_MS:
                return html
        else:
            vide_depuis = None

        if ecoule >= NEXT_PAGE_CHANGE_TIMEOUT_MS:
            return html

        page.wait_for_timeout(NEXT_PAGE_POLL_MS)
        ecoule += NEXT_PAGE_POLL_MS
        if vide_depuis is not None:
            vide_depuis += NEXT_PAGE_POLL_MS
        html = page.content()


def charger_page_catalogue(
    page,
    url,
    exiger_produits=False,
    liens_precedents=None,
):
    """Charge une page et attend le rendu utile du catalogue."""
    noter_requete()
    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    if exiger_produits:
        page.wait_for_selector(
            PRODUCT_SELECTOR,
            state="attached",
            timeout=PRODUCT_WAIT_TIMEOUT_MS,
        )
        page.wait_for_timeout(FIRST_PAGE_SETTLE_MS)
        return page.content()

    if liens_precedents is not None:
        return attendre_page_suivante(page, liens_precedents)

    page.wait_for_timeout(NEXT_PAGE_SETTLE_MS)
    return page.content()


def _scan_premiere_page():
    products = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="en-US")

        try:
            html = charger_page_catalogue(
                page,
                URL_TEMPLATE.format(offset=0, limit=PAGE_SIZE),
                exiger_produits=True,
            )
        finally:
            browser.close()

    extraire_page(html, products)

    if not products:
        raise RuntimeError(
            "Aucun produit One Piece Card Game détecté sur Premium Bandai"
        )

    return products


def scan():
    products = {}
    liens_bruts_vus = set()
    liens_page_precedente = None

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="en-US")

        try:
            for numero_page in range(MAX_PAGES):
                offset = numero_page * PAGE_SIZE
                url_page = URL_TEMPLATE.format(
                    offset=offset,
                    limit=PAGE_SIZE,
                )
                print("🔎 Premium Bandai offset :", offset)

                html = charger_page_catalogue(
                    page,
                    url_page,
                    exiger_produits=(numero_page == 0),
                    liens_precedents=liens_page_precedente,
                )
                liens_bruts_page = extraire_page(
                    html,
                    products,
                )
                nouveaux_liens = liens_bruts_page - liens_bruts_vus

                if not liens_bruts_page or not nouveaux_liens:
                    break

                liens_bruts_vus.update(liens_bruts_page)
                liens_page_precedente = liens_bruts_page

                if len(liens_bruts_page) < PAGE_SIZE:
                    break
        finally:
            browser.close()

    if not products:
        raise RuntimeError(
            "Aucun produit One Piece Card Game détecté sur Premium Bandai"
        )

    return products
