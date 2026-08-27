import json
import math
import re
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from cible import CIBLE_PRIORITAIRE, est_cible_prioritaire
from observabilite import noter_requete
from scanners.politique import produit_autorise


BASE_URL = "https://www.play-in.com"
CATALOGUE_URL = "https://www.play-in.com/fr/gamme/24/one-piece/catalogue"
READER_PREFIX = "https://r.jina.ai/"
MAX_PAGES = 10
CATALOGUE_PAGE_SIZE = 48

EXCLUDED_PRODUCT_MARKERS = (
    "CARTE À L'UNITÉ", "CARTE A L'UNITE", "CARTES À L'UNITÉ",
    "CARTES A L'UNITE", "LOT DE CARTES", "PROXY",
)
ACCESSORY_MARKERS = (
    "TAPIS DE JEU", "PLAYMAT", "PROTÈGE-CARTES", "PROTEGE-CARTES",
    "SLEEVES", "CARD SLEEVES", "DECK BOX", "SIDEWINDER", "ZIPFOLIO",
    "CLASSEUR", "BINDER", "ALBUM", "PORTFOLIO", "PROTECTION EN ACRYLIQUE",
)
PROMO_CARD_MARKERS = (
    "CARTE PROMO", "CARTE PROMOTIONNELLE", "CARTE EXCLUSIVE", "PROMO CARD",
    "PROMOTIONAL CARD", "EXCLUSIVE CARD", "INCLUT UNE CARTE", "AVEC CARTE",
    "INCLUDES CARD", "WITH CARD",
)
SEALED_PRODUCT_MARKERS = (
    "DISPLAY", "BOOSTER", "STARTER", "DECK", "DOUBLE PACK", "COFFRET",
    "COLLECTION", "GOODS SET", "PREMIUM CARD", "DEVIL FRUIT",
    "FRUIT DU DÉMON", "FRUITS DU DÉMON", "BOÎTE", "BOITE", "CARTON",
    "CASE SCELL",
)
EXCLUDED_LANGUAGE_MARKERS = (
    "JAPONAIS", "JAPONAISE", "JAPANESE", "CHINOIS", "CHINOISE", "CHINESE",
    "CORÉEN", "COREEN", "KOREAN",
)


def nettoyer_texte(texte):
    return re.sub(
        r"\s+",
        " ",
        str(texte or "").replace("\u00a0", " "),
    ).strip()


def normaliser_lien(lien):
    parties = urlsplit(urljoin(BASE_URL, str(lien or "")))
    if "/fr/produit/" not in parties.path:
        return ""
    return urlunsplit((
        parties.scheme,
        parties.netloc,
        parties.path.rstrip("/"),
        "",
        "",
    ))


def est_op17(texte):
    """Alias historique : détecte la cible prioritaire configurée."""
    return est_cible_prioritaire(texte)


def detecter_langue(texte):
    texte = " " + nettoyer_texte(texte).upper() + " "
    if re.search(r"(?:ONE PIECE|\))\s+EN\b", texte) or " ANGLAIS " in texte:
        return "EN"
    if re.search(r"(?:ONE PIECE|\))\s+FR\b", texte) or any(
        marqueur in texte
        for marqueur in (" FRANÇAIS ", " FRANCAIS ", " VF ")
    ):
        return "VF"
    return "OTHER"


def langue_exclue(texte):
    texte = " " + nettoyer_texte(texte).upper() + " "
    return (
        any(marqueur in texte for marqueur in EXCLUDED_LANGUAGE_MARKERS)
        or re.search(r"(?:ONE PIECE|\))\s+(?:JP|JA|KO|KR|CN)\b", texte)
        is not None
    )


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
    if langue_exclue(texte):
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
    correspondance = re.search(
        r"SORTIE\s+PR[ÉE]VUE\s+LE\s+(\d{1,2}/\d{1,2}/20\d{2})",
        nettoyer_texte(texte),
        flags=re.IGNORECASE,
    )
    return correspondance.group(1) if correspondance else ""


def extraire_prix(texte):
    correspondance = re.search(
        r"(\d[\d\s.,]*\s*€)",
        nettoyer_texte(texte),
    )
    return nettoyer_texte(correspondance.group(1)) if correspondance else "Non disponible"


def detecter_statut(texte):
    texte = nettoyer_texte(texte).upper()
    if "À VENIR" in texte or "A VENIR" in texte or "BIENTÔT DISPONIBLE" in texte:
        return "COMING_SOON"
    if "PRÉCOMMANDE" in texte or "PRECOMMANDE" in texte or "PREORDER" in texte:
        return "PREORDER"
    if "RETRAIT MAGASIN UNIQUEMENT" in texte:
        return "STORE_ONLY"
    if "RUPTURE DE STOCK" in texte or "ÉPUISÉ" in texte or "EPUISE" in texte:
        return "SOLD OUT"
    if re.search(r"\d[\d\s.,]*\s*€", texte):
        return "AVAILABLE"
    return "UNKNOWN"


def extraire_chunks_flight(html_page):
    chunks = []
    soup = BeautifulSoup(html_page, "lxml")
    for script in soup.find_all("script"):
        contenu = script.string or script.get_text() or ""
        prefixe = "self.__next_f.push("
        debut = contenu.find(prefixe)
        fin = contenu.rfind(")")
        if debut < 0 or fin <= debut:
            continue
        try:
            charge = json.loads(contenu[debut + len(prefixe):fin])
        except (json.JSONDecodeError, TypeError):
            continue
        if (
            isinstance(charge, list)
            and len(charge) > 1
            and isinstance(charge[1], str)
        ):
            chunks.append(charge[1])
    return chunks


def extraire_objet_json(texte, debut):
    profondeur = 0
    dans_chaine = False
    echappe = False
    for position in range(debut, len(texte)):
        caractere = texte[position]
        if dans_chaine:
            if echappe:
                echappe = False
            elif caractere == "\\":
                echappe = True
            elif caractere == '"':
                dans_chaine = False
            continue
        if caractere == '"':
            dans_chaine = True
        elif caractere == "{":
            profondeur += 1
        elif caractere == "}":
            profondeur -= 1
            if profondeur == 0:
                return texte[debut:position + 1]
    return ""


def extraire_donnees_produit_flight(html_page, identifiant_recherche):
    for chunk in extraire_chunks_flight(html_page):
        for correspondance in re.finditer(r'"(?:product|sealedProduct)":\{', chunk):
            objet_brut = extraire_objet_json(chunk, correspondance.end() - 1)
            if not objet_brut:
                continue
            try:
                donnees = json.loads(objet_brut)
            except json.JSONDecodeError:
                continue
            if donnees.get("_id") == identifiant_recherche:
                return donnees
    return {}


def extraire_date_sortie(valeur):
    if not valeur:
        return None
    try:
        return datetime.fromisoformat(str(valeur).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def detecter_statut_donnees(produit):
    date_sortie = extraire_date_sortie(produit.get("releasedAt"))
    if produit.get("sellable"):
        if produit.get("inStore") and produit.get("inWarehouse") is False:
            return "STORE_ONLY"
        return "AVAILABLE"
    if date_sortie and date_sortie >= date.today():
        return "COMING_SOON"
    if produit.get("inRestocking"):
        return "COMING_SOON"
    return "SOLD OUT"


def formater_prix_donnees(produit):
    valeur = produit.get("sellPrice")
    if valeur is None:
        valeur = produit.get("priceWithoutDiscount")
    try:
        return f"{float(valeur):.2f}".replace(".", ",") + " €"
    except (TypeError, ValueError):
        return "Non disponible"


def extraire_produits_flight(html_page):
    chunks = extraire_chunks_flight(html_page)
    liens_par_id = {}
    for chunk in chunks:
        for lien, identifiant in re.findall(
            r'"href":"([^" ]*/fr/produit/(\d+)/[^" ]+)"',
            chunk,
        ):
            liens_par_id[int(identifiant)] = normaliser_lien(lien)

    donnees_par_id = {}
    for chunk in chunks:
        for correspondance in re.finditer(r'"(?:product|sealedProduct)":\{', chunk):
            objet_brut = extraire_objet_json(chunk, correspondance.end() - 1)
            if not objet_brut:
                continue
            try:
                donnees = json.loads(objet_brut)
            except json.JSONDecodeError:
                continue
            identifiant = donnees.get("_id")
            if donnees.get("__typename") == "SealedProduct" and isinstance(identifiant, int):
                donnees_par_id[identifiant] = donnees

    produits = {}
    for identifiant, donnees in donnees_par_id.items():
        lien = liens_par_id.get(identifiant, "")
        nom = nettoyer_texte(donnees.get("transName") or donnees.get("name"))
        categorie = nettoyer_texte((donnees.get("category") or {}).get("transName"))
        if not lien or not produit_surveille(nom, categorie):
            continue

        statut = detecter_statut_donnees(donnees)
        date_sortie = extraire_date_sortie(donnees.get("releasedAt"))
        disponibilite = ""
        if date_sortie and (statut == "COMING_SOON" or est_cible_prioritaire(nom)):
            disponibilite = date_sortie.strftime("%d/%m/%Y")

        produits[lien] = {
            "site": "Playin",
            "name": nom,
            "price": formater_prix_donnees(donnees),
            "status": statut,
            "availability": disponibilite,
            "link": lien,
            "image": donnees.get("imageUrl") or "",
            "language": detecter_langue(nom),
            "source": "catalogue",
            "delivery": "STORE_ONLY" if statut == "STORE_ONLY" else "SHIPPING_OR_ANNOUNCED",
            "notify_when_referenced": est_cible_prioritaire(nom),
        }
    return produits


def extraire_produits_json_ld(html_page):
    produits = {}
    for chunk in extraire_chunks_flight(html_page):
        if '"@type":"ItemList"' not in chunk:
            continue
        try:
            document = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if document.get("@type") != "ItemList":
            continue

        for element in document.get("itemListElement", []):
            donnees = element.get("item") or {}
            offres = donnees.get("offers") or {}
            nom = nettoyer_texte(donnees.get("name"))
            lien = normaliser_lien(donnees.get("url") or offres.get("url"))
            if not lien or not produit_surveille(nom):
                continue

            disponibilite_schema = str(offres.get("availability") or "")
            if disponibilite_schema.endswith("/InStock"):
                statut = "AVAILABLE"
            elif est_cible_prioritaire(nom):
                statut = "COMING_SOON"
            else:
                statut = "SOLD OUT"

            prix = offres.get("price")
            if prix in (None, 0, 0.0, "0"):
                prix_formate = "Non disponible"
            else:
                try:
                    prix_formate = f"{float(prix):.2f}".replace(".", ",") + " €"
                except (TypeError, ValueError):
                    prix_formate = "Non disponible"

            produits[lien] = {
                "site": "Playin",
                "name": nom,
                "price": prix_formate,
                "status": statut,
                "availability": "",
                "link": lien,
                "image": donnees.get("image") or "",
                "language": detecter_langue(nom),
                "source": "catalogue",
                "delivery": "SHIPPING_OR_ANNOUNCED",
                "notify_when_referenced": est_cible_prioritaire(nom),
            }
    return produits


def extraire_produits_serveur(html_page):
    produits = extraire_produits_json_ld(html_page)
    produits.update(extraire_produits_flight(html_page))
    return produits


def extraire_disponibilite_detail(html_page, identifiant):
    donnees = extraire_donnees_produit_flight(html_page, identifiant)
    date_sortie = extraire_date_sortie(donnees.get("releasedAt"))
    if date_sortie:
        return date_sortie.strftime("%d/%m/%Y")

    for chunk in extraire_chunks_flight(html_page):
        correspondance = re.search(
            r"(?:SORTIE\s+PR[ÉE]VUE\s+LE|SORTIE\s+LE)\s+"
            r"(\d{1,2}/\d{1,2}/20\d{2})",
            chunk,
            flags=re.IGNORECASE,
        )
        if correspondance:
            return correspondance.group(1)
    return ""


def enrichir_op17(produits):
    """Alias historique : enrichit la cible prioritaire configurée."""
    for produit in produits.values():
        if not est_cible_prioritaire(produit.get("name", "")):
            continue

        correspondance = re.search(
            r"/fr/produit/(\d+)/",
            produit.get("link", ""),
        )
        if not correspondance:
            continue

        try:
            noter_requete()
            reponse = requests.get(
                READER_PREFIX + produit["link"],
                headers={
                    "X-Respond-With": "html",
                    "X-Timeout": "60",
                    "X-No-Cache": "true",
                },
                timeout=120,
            )
            reponse.raise_for_status()
        except requests.RequestException as erreur:
            print(
                f"⚠️ Playin : date {CIBLE_PRIORITAIRE} indisponible pour",
                produit.get("name", "Produit inconnu"),
                "-",
                erreur,
            )
            continue

        disponibilite = extraire_disponibilite_detail(
            reponse.text,
            int(correspondance.group(1)),
        )
        if disponibilite:
            produit["availability"] = disponibilite


def extraire_produits(html_page):
    soup = BeautifulSoup(html_page, "lxml")
    produits = {}
    for carte in soup.select(
        "ul.grid--template_productCatalog > li.tile--type_catalogItem"
    ):
        lien_element = carte.select_one('a[href*="/fr/produit/"]')
        if not lien_element:
            continue

        nom = nettoyer_texte(carte.get("title") or lien_element.get_text(" ", strip=True))
        lien = normaliser_lien(lien_element.get("href", ""))
        texte = nettoyer_texte(carte.get_text(" ", strip=True))
        if not lien or not produit_surveille(nom, texte):
            continue

        image_element = carte.select_one("img")
        statut = detecter_statut(texte)
        produits[lien] = {
            "site": "Playin",
            "name": nom,
            "price": extraire_prix(texte),
            "status": statut,
            "availability": extraire_disponibilite(texte),
            "link": lien,
            "image": urljoin(BASE_URL, image_element.get("src", "")) if image_element else "",
            "language": detecter_langue(nom),
            "source": "catalogue",
            "delivery": "STORE_ONLY" if statut == "STORE_ONLY" else "SHIPPING_OR_ANNOUNCED",
            "notify_when_referenced": est_cible_prioritaire(nom),
        }
    return produits


def extraire_nombre_pages(html_page):
    soup = BeautifulSoup(html_page, "lxml")
    numeros = [1]
    for lien in soup.select('a[href*="page="]'):
        correspondance = re.search(r"[?&]page=(\d+)", lien.get("href", ""))
        if correspondance:
            numeros.append(int(correspondance.group(1)))
    return min(max(numeros), MAX_PAGES)


def extraire_nombre_pages_flight(html_page):
    numeros = [1]
    for chunk in extraire_chunks_flight(html_page):
        numeros.extend(
            int(numero)
            for numero in re.findall(
                r"/fr/gamme/24/one-piece/catalogue\?page=(\d+)",
                chunk,
            )
        )
    return min(max(numeros), MAX_PAGES)


def extraire_nombre_pages_resultats(html_page):
    for chunk in extraire_chunks_flight(html_page):
        correspondance = re.search(
            r"(\d+)\s+r[ée]sultats",
            chunk,
            flags=re.IGNORECASE,
        )
        if correspondance:
            total = int(correspondance.group(1))
            return min(max(1, math.ceil(total / CATALOGUE_PAGE_SIZE)), MAX_PAGES)
    return 1


def charger_page(url):
    erreur_directe = None
    try:
        noter_requete()
        reponse = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; onepiece-stock-tracker/1.0)"},
            timeout=45,
        )
        reponse.raise_for_status()
        html_page = reponse.text
        if "self.__next_f.push" in html_page and extraire_produits_serveur(html_page):
            return html_page
    except requests.RequestException as erreur:
        erreur_directe = erreur

    print(
        "⚠️ Playin : accès direct indisponible, utilisation du lecteur de secours",
        erreur_directe or "page incomplète",
    )

    try:
        noter_requete()
        reponse = requests.get(
            READER_PREFIX + url,
            headers={
                "X-Respond-With": "html",
                "X-Timeout": "60",
                "X-No-Cache": "true",
            },
            timeout=120,
        )
        reponse.raise_for_status()
    except requests.RequestException as erreur:
        raise RuntimeError("Playin ne fournit pas son catalogue rendu au tracker") from erreur

    html_page = reponse.text
    if "self.__next_f.push" not in html_page or not extraire_produits_serveur(html_page):
        raise RuntimeError("Playin a renvoyé un catalogue vide ou non chargé")
    return html_page


def scan():
    produits = {}
    print("🔎 Playin : catalogue page 1")
    html_premiere_page = charger_page(CATALOGUE_URL)
    produits.update(extraire_produits_serveur(html_premiere_page))
    nombre_pages = max(
        2,
        extraire_nombre_pages(html_premiere_page),
        extraire_nombre_pages_flight(html_premiere_page),
        extraire_nombre_pages_resultats(html_premiere_page),
    )

    for numero_page in range(2, nombre_pages + 1):
        url = f"{CATALOGUE_URL}?page={numero_page}"
        print("🔎 Playin : catalogue page", numero_page)
        html_page = charger_page(url)
        produits.update(extraire_produits_serveur(html_page))

    enrichir_op17(produits)

    if not produits:
        raise RuntimeError("Aucun produit Playin surveillé détecté")

    print("📦 Playin :", len(produits), "produit(s) surveillé(s)")
    return produits
