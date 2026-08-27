import re
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from cible import CIBLE_PRIORITAIRE, est_cible_prioritaire
from observabilite import noter_requete
from scanners.politique import produit_autorise


BASE_URL = "https://oupi.eu"
CATALOGUE_URL = "https://oupi.eu/fr/382-one-piece"
PREORDER_URL = "https://oupi.eu/fr/413-precommande-one-piece"
PRIORITY_SEARCH_URL = (
    "https://oupi.eu/fr/recherche?controller=search"
    f"&s={CIBLE_PRIORITAIRE}"
)
READER_PREFIX = "https://r.jina.ai/"
READER_TARGET = "#products"
MAX_PAGES = 10

EXCLUDED_PRODUCT_MARKERS = (
    "CARTE À L'UNITÉ",
    "CARTE A L'UNITE",
    "CARTES À L'UNITÉ",
    "CARTES A L'UNITE",
    "LOT DE CARTES",
    "PROXY",
)

ACCESSORY_MARKERS = (
    "TAPIS DE JEU",
    "PLAYMAT",
    "PROTÈGE-CARTES",
    "PROTEGE-CARTES",
    "SLEEVES",
    "CARD SLEEVES",
    "DECK BOX",
    "CLASSEUR",
    "BINDER",
    "ALBUM",
    "PORTFOLIO",
    "PROTECTION EN ACRYLIQUE",
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
    "WITH CARD",
)

SEALED_PRODUCT_MARKERS = (
    "DISPLAY",
    "BOOSTER",
    "STARTER",
    "DECK",
    "DOUBLE PACK",
    "COFFRET",
    "COLLECTION",
    "GOODS SET",
    "PREMIUM CARD",
    "DEVIL FRUIT",
    "BOÎTE",
    "BOITE",
    "CARTON",
    "CASE SCELL",
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
    "KOREAN",
)

MONTH_PATTERN = (
    r"JANVIER|F[ÉE]VRIER|MARS|AVRIL|MAI|JUIN|JUILLET|"
    r"AO[ÛU]T|SEPTEMBRE|OCTOBRE|NOVEMBRE|D[ÉE]CEMBRE"
)


def nettoyer_texte(texte):
    return re.sub(
        r"\s+",
        " ",
        str(texte or "").replace("\u00a0", " "),
    ).strip()


def normaliser_lien(lien):
    parties = urlsplit(urljoin(BASE_URL, str(lien or "")))
    if not parties.path or ".html" not in parties.path:
        return ""
    return urlunsplit(
        (
            parties.scheme,
            parties.netloc,
            parties.path.rstrip("/"),
            "",
            "",
        )
    )


def est_op17(texte):
    """Alias historique : détecte la cible prioritaire configurée."""
    return est_cible_prioritaire(texte)


def detecter_langue(texte):
    texte = nettoyer_texte(texte).upper()

    if re.search(r"\b(?:ANGLAIS|ANGLAISE|ENGLISH)\b", texte):
        return "EN"

    if re.search(r"\b(?:FRANÇAIS|FRANCAIS|FRANÇAISE|VF)\b", texte):
        return "VF"

    return "OTHER"


def produit_surveille(nom, description=""):
    if not produit_autorise(nom, description):
        return False

    texte = " " + nettoyer_texte(nom + " " + description).upper() + " "

    signature_tcg = (
        "ONE PIECE" in texte
        or re.search(r"\b(?:OP|EB|PRB|ST|DP|DF)\s*-?\s*\d{2}\b", texte)
        is not None
    )
    if not signature_tcg:
        return False

    if any(marqueur in texte for marqueur in EXCLUDED_PRODUCT_MARKERS):
        return False

    if any(marqueur in texte for marqueur in EXCLUDED_LANGUAGE_MARKERS):
        return False

    if re.search(r"\b(?:OP|EB|PRB|ST|P)\d{2}-\d{3}\b", texte):
        return False

    est_accessoire = any(marqueur in texte for marqueur in ACCESSORY_MARKERS)
    contient_promo = any(marqueur in texte for marqueur in PROMO_CARD_MARKERS)
    if est_accessoire and not contient_promo:
        return False

    return (
        any(marqueur in texte for marqueur in SEALED_PRODUCT_MARKERS)
        or contient_promo
    )


def extraire_disponibilite(texte):
    texte = nettoyer_texte(texte)
    motifs = (
        r"(?:SORTIE\s+PR[ÉE]VUE|DISPONIBILIT[ÉE])\s*(?:LE|:)?\s*"
        r"(\d{1,2}/\d{1,2}/20\d{2})",
        r"(?:SORTIE\s+PR[ÉE]VUE|DISPONIBILIT[ÉE])\s*(?:LE|:)?\s*"
        rf"((?:FIN\s+|D[ÉE]BUT\s+|COURANT\s+)?(?:\d{{1,2}}\s+)?"
        rf"(?:{MONTH_PATTERN})(?:\s+20\d{{2}})?)",
    )
    for motif in motifs:
        correspondance = re.search(motif, texte, flags=re.IGNORECASE)
        if correspondance:
            return nettoyer_texte(correspondance.group(1))
    return ""


def detecter_statut(carte, texte):
    bouton = carte.select_one('button[data-button-action="add-to-cart"]')
    texte_majuscule = nettoyer_texte(texte).upper()

    if (
        "OUT OF STOCK" in texte_majuscule
        or "RUPTURE DE STOCK" in texte_majuscule
        or "ÉPUISÉ" in texte_majuscule
        or "EPUISE" in texte_majuscule
    ):
        return "SOLD OUT"

    if bouton:
        classes = " ".join(bouton.get("class", [])).upper()
        titre = str(bouton.get("data-original-title", "")).upper()
        if bouton.has_attr("disabled") or "OUT-OF-STOCK" in classes or "OUT OF STOCK" in titre:
            return "SOLD OUT"

    if "PRÉCOMMANDE" in texte_majuscule or "PRECOMMANDE" in texte_majuscule:
        return "PREORDER" if bouton else "COMING_SOON"

    if bouton:
        return "AVAILABLE"

    return "UNKNOWN"


def extraire_produits(html_page, source="catalogue"):
    soup = BeautifulSoup(html_page, "lxml")
    produits = {}

    for carte in soup.select("article.product-miniature"):
        nom_element = (
            carte.select_one('h6[itemprop="name"]')
            or carte.select_one(".product-title h6")
        )
        lien_element = (
            carte.select_one('a.thumbnail[itemprop="url"]')
            or carte.select_one(".product-title a[href]")
        )
        if not nom_element or not lien_element:
            continue

        nom = nettoyer_texte(nom_element.get_text(" ", strip=True))
        lien = normaliser_lien(lien_element.get("href", ""))
        texte = nettoyer_texte(carte.get_text(" ", strip=True))
        if not lien or not produit_surveille(nom, texte):
            continue

        prix_element = carte.select_one(".product-price-and-shipping .price")
        image_element = carte.select_one("img[itemprop='image']") or carte.select_one("img")
        disponibilite = extraire_disponibilite(texte)

        produit = {
            "site": "Oupi",
            "name": nom,
            "price": nettoyer_texte(prix_element.get_text(" ", strip=True)) if prix_element else "Non disponible",
            "status": detecter_statut(carte, texte),
            "availability": disponibilite,
            "link": lien,
            "image": urljoin(BASE_URL, image_element.get("src", "")) if image_element else "",
            "language": detecter_langue(nom),
            "source": source,
            "notify_when_referenced": est_cible_prioritaire(nom),
        }
        produits[lien] = produit

    return produits


def extraire_nombre_pages(html_page):
    soup = BeautifulSoup(html_page, "lxml")
    numeros = [1]
    for lien in soup.select('a[href*="page="]'):
        correspondance = re.search(r"[?&]page=(\d+)", lien.get("href", ""))
        if correspondance:
            numeros.append(int(correspondance.group(1)))
    return min(max(numeros), MAX_PAGES)


def charger_page(url, autoriser_vide=False):
    erreur_directe = None

    try:
        noter_requete()
        reponse = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; onepiece-stock-tracker/1.0)",
            },
            timeout=45,
        )
        reponse.raise_for_status()
        html_page = reponse.text

        if (
            BeautifulSoup(html_page, "lxml").select_one(
                "article.product-miniature"
            )
            or (autoriser_vide and html_page.strip())
        ):
            return html_page
    except requests.RequestException as erreur:
        erreur_directe = erreur

    print(
        "⚠️ Oupi : accès direct indisponible, "
        "utilisation du lecteur de secours",
        erreur_directe or "page incomplète"
    )

    try:
        noter_requete()
        reponse = requests.get(
            READER_PREFIX + url,
            headers={
                "X-Respond-With": "html",
                "X-Target-Selector": READER_TARGET,
                "X-Timeout": "60",
                "X-No-Cache": "true",
            },
            timeout=120,
        )
        reponse.raise_for_status()
    except requests.RequestException as erreur:
        raise RuntimeError(
            "Oupi ne fournit pas son catalogue rendu au tracker"
        ) from erreur

    html_page = reponse.text
    if (
        not BeautifulSoup(html_page, "lxml").select_one(
            "article.product-miniature"
        )
        and not autoriser_vide
    ):
        raise RuntimeError(
            "Oupi a renvoyé un catalogue vide ou bloqué"
        )

    return html_page


def ajouter_source_optionnelle(
    produits,
    url,
    source,
    autoriser_vide=False,
    seulement_cible=False,
):
    try:
        html_page = charger_page(url, autoriser_vide=autoriser_vide)
        supplementaires = extraire_produits(html_page, source=source)
    except Exception as erreur:
        print(
            f"⚠️ Oupi : source complémentaire {source} indisponible : {erreur}"
        )
        return 0

    ajoutes = 0
    for lien, produit in supplementaires.items():
        if seulement_cible and not est_cible_prioritaire(produit.get("name", "")):
            continue

        # Le catalogue principal est la base de référence. Les routes dédiées
        # servent uniquement à découvrir plus tôt une fiche absente du catalogue
        # et ne doivent pas faire varier les métadonnées d'un produit déjà connu.
        if lien not in produits:
            produits[lien] = produit
            ajoutes += 1

    print(f"ℹ️ Oupi : {source} a ajouté {ajoutes} référence(s) complémentaire(s)")
    return ajoutes


def scan():
    produits = {}

    # Le catalogue principal est critique et doit être scanné avant les routes
    # complémentaires. Une panne de précommandes/recherche ne doit pas empêcher
    # de surveiller les références déjà présentes dans le catalogue général.
    print("🔎 Oupi : catalogue page 1")
    html_premiere_page = charger_page(CATALOGUE_URL)
    produits.update(extraire_produits(html_premiere_page))
    nombre_pages = extraire_nombre_pages(html_premiere_page)

    for numero_page in range(2, nombre_pages + 1):
        url = f"{CATALOGUE_URL}?page={numero_page}"
        print("🔎 Oupi : catalogue page", numero_page)
        html_page = charger_page(url)
        produits.update(extraire_produits(html_page))

    if not produits:
        raise RuntimeError("Aucun produit Oupi surveillé détecté dans le catalogue principal")

    print(f"Recherche directe {CIBLE_PRIORITAIRE} Oupi")
    ajouter_source_optionnelle(
        produits,
        PRIORITY_SEARCH_URL,
        source="priority_search",
        autoriser_vide=True,
        seulement_cible=True,
    )

    print(
        f"🔥 Oupi : contrôle complémentaire des précommandes et "
        f"de {CIBLE_PRIORITAIRE}"
    )
    ajouter_source_optionnelle(
        produits,
        PREORDER_URL,
        source="preorders",
    )

    print("📦 Oupi :", len(produits), "produit(s) surveillé(s)")
    return produits
