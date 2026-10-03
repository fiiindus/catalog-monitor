import re
import time

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin, urlsplit, urlunsplit

from observabilite import noter_requete


BASE_URL = "https://p-bandai.com"

URL_TEMPLATES = (
    # Search across all shops and series, including closed and upcoming items.
    "https://p-bandai.com/us/search?keyword=ONE%20PIECE%20CARD%20GAME"
    "&offset={offset}&limit={limit}&sortType=NewArrival"
    "&_f_productStatuses=Waiting,On,End",
    "https://p-bandai.com/us/search?keyword=ONE%20PIECE%20CARD%20GAME"
    "&offset={offset}&limit={limit}&sortType=Relevance"
    "&_f_productStatuses=Waiting,On,End",
    # The series listing catches items omitted by the site's text index.
    "https://p-bandai.com/us/series/onepiece-series"
    "?offset={offset}&limit={limit}&sortType=NewArrival"
    "&_f_productStatuses=Waiting,On,End",
)

PAGE_SIZE = 40
MAX_PAGES = 50
WATCHED_ITEMS = ("https://p-bandai.com/us/item/N2873815002",)

PRODUCT_SELECTOR = ".o-search-product .c-product__link"
PRODUCT_WAIT_TIMEOUT_MS = 30000
FIRST_PAGE_SETTLE_MS = 1000
NEXT_PAGE_SETTLE_MS = 2500
NEXT_PAGE_CHANGE_TIMEOUT_MS = 15000
NEXT_PAGE_POLL_MS = 500
EMPTY_PAGE_CONFIRM_MS = 2000
DETAIL_PAGE_SETTLE_MS = 1500


class ScanIncomplet(RuntimeError):
    pass


class PageIndisponible(ScanIncomplet):
    pass


def verifier_page_disponible(page):
    # The site serves its own error page with HTTP 200 on some runner requests.
    # Waiting for product elements cannot make that response a valid catalogue.
    if str(page.title()).upper().startswith("PAGE NOT AVAILABLE"):
        raise PageIndisponible("Premium Bandai renvoie Page indisponible")


def attendre_produit_ou_erreur(page, selector):
    # The error can appear after DOMContentLoaded; race it against useful content.
    page.wait_for_function(
        "selector => document.title.toUpperCase().startsWith('PAGE NOT AVAILABLE') || document.querySelector(selector)",
        arg=selector, timeout=PRODUCT_WAIT_TIMEOUT_MS)
    verifier_page_disponible(page)


def diagnostic_page(page):
    """Public page diagnostics for failed unattended loads (no cookies/headers)."""
    try:
        soup = BeautifulSoup(page.content(), "lxml")
        titre = nettoyer_texte(soup.title.get_text() if soup.title else "")[:160]
        h1 = [nettoyer_texte(node.get_text())[:160] for node in soup.find_all("h1")]
        print("Diagnostic page :", {"titre": titre, "h1": h1[:3],
                                     "liens_catalogue": len(soup.select(PRODUCT_SELECTOR))})
    except Exception:
        print("Diagnostic page indisponible")


def lien_produit(href):
    parties = urlsplit(urljoin(BASE_URL, href))
    if (parties.scheme != "https" or parties.netloc != "p-bandai.com"
            or not re.fullmatch(r"/us/item/[A-Za-z0-9]+/?", parties.path)):
        return ""
    return urlunsplit(("https", "p-bandai.com", parties.path.rstrip("/"), "", ""))

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
    return "ONE PIECE CARD GAME" in nettoyer_texte(nom).upper()


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

    if "COMING SOON" in texte or "COMING_SOON" in texte:
        return "COMING_SOON"

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
        if not bouton.has_attr("disabled")
        and bouton.get("aria-disabled") != "true"
    )
    return detecter_statut(boutons)


def extraire_detail(html, lien, precedent=None):
    soup = BeautifulSoup(html, "lxml")
    titre = soup.select_one("h1")
    nom = nettoyer_texte(titre.get_text(" ", strip=True) if titre else "")
    if not produit_surveille(nom):
        raise ScanIncomplet("Fiche absente ou titre produit non reconnu")
    statut = detecter_statut_detail(html)
    if statut == "UNKNOWN":
        raise ScanIncomplet("État d'achat non reconnu sur la fiche")
    produit = dict(precedent or {})
    produit.update(site="Premium Bandai US", name=nom, link=lien,
                   status=statut, orderable=est_commandable(statut),
                   notify_when_referenced=True)
    return produit


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
        href = lien_produit(link.get("href", ""))
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
            "notify_when_referenced": True,
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
    verifier_page_disponible(page)

    if exiger_produits:
        attendre_produit_ou_erreur(page, PRODUCT_SELECTOR)
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


def scan_avec_diagnostic(connus=None):
    products = {}
    erreurs = []
    connus = connus or {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="en-US")

        try:
            for source in URL_TEMPLATES:
                liens_bruts_vus = set()
                liens_page_precedente = None
                for numero_page in range(MAX_PAGES):
                    offset = numero_page * PAGE_SIZE
                    url_page = source.format(offset=offset, limit=PAGE_SIZE)
                    print("🔎 Premium Bandai :", url_page)

                    try:
                        for tentative in range(2):
                            try:
                                html = charger_page_catalogue(
                                    page, url_page,
                                    exiger_produits=(numero_page == 0),
                                    liens_precedents=liens_page_precedente)
                                break
                            except PageIndisponible:
                                raise
                            except Exception:
                                if tentative == 1:
                                    raise
                                print("🔁 Nouvelle tentative sur la même page")
                    except Exception as erreur:
                        diagnostic_page(page)
                        # Never jump over a failed first page: newest references
                        # live there. Preserve the other sources and report degradation.
                        erreurs.append(f"{source.split('&offset=')[0]} page {numero_page + 1}: {type(erreur).__name__}")
                        print("⚠️ Premium Bandai source incomplète :", erreurs[-1])
                        break
                    liens_bruts_page = extraire_page(html, products)
                    nouveaux_liens = liens_bruts_page - liens_bruts_vus

                    if not liens_bruts_page:
                        break
                    if not nouveaux_liens:
                        erreurs.append(f"Pagination répétée : {url_page}")
                        break

                    liens_bruts_vus.update(liens_bruts_page)
                    liens_page_precedente = liens_bruts_page

                    if len(liens_bruts_page) < PAGE_SIZE:
                        break
                else:
                    erreurs.append(f"Limite de pagination atteinte : {source}")

            # Always check the anniversary item, and recent known references
            # absent from all listings. Limit detail traffic on each pass.
            manquants = [lien for lien in reversed(list(connus))
                         if lien not in products and lien_produit(lien)]
            if manquants:
                debut = int(time.time() // 300) % len(manquants)
                manquants = manquants[debut:] + manquants[:debut]
            cibles = list(dict.fromkeys([*WATCHED_ITEMS, *manquants[:3]]))
            for lien in cibles:
                try:
                    noter_requete()
                    reponse = page.goto(lien, wait_until="domcontentloaded", timeout=60000)
                    if reponse is not None and reponse.status >= 400:
                        raise ScanIncomplet(f"HTTP {reponse.status}")
                    verifier_page_disponible(page)
                    attendre_produit_ou_erreur(page, "h1.o-items__sidebar-title")
                    page.wait_for_selector("h1.o-items__sidebar-title", state="attached",
                                           timeout=PRODUCT_WAIT_TIMEOUT_MS)
                    page.wait_for_timeout(DETAIL_PAGE_SETTLE_MS)
                    products[lien] = extraire_detail(page.content(), lien,
                                                    products.get(lien) or connus.get(lien))
                except Exception as erreur:
                    diagnostic_page(page)
                    erreurs.append(f"Fiche {lien}: {type(erreur).__name__}")
        finally:
            browser.close()

    if not products:
        raise RuntimeError(
            "Aucun produit One Piece Card Game détecté sur Premium Bandai"
        )

    # Absence and UNKNOWN cannot rearm a stock notification.
    conserves = {lien: dict(produit) for lien, produit in connus.items()}
    for lien, produit in products.items():
        if produit["status"] == "UNKNOWN" and lien in conserves:
            produit = {**produit, "status": conserves[lien]["status"],
                       "orderable": conserves[lien].get("orderable", False)}
        conserves[lien] = produit
    return conserves, erreurs


def scan():
    from integrite import charger_stock_precedent
    produits, erreurs = scan_avec_diagnostic(
        charger_stock_precedent().get("Premium Bandai US", {}))
    if erreurs:
        raise ScanIncomplet("; ".join(erreurs))
    return produits
