from urllib.parse import quote

import requests

from observabilite import noter_requete
from scanners.parkage import BASE_URL


BOUTIQUE = "Parkage — Cartes à l’unité"
API_URL = "https://back.parkage.com/api/parkage/search/get"
IMAGE_URL = "https://embedded.parkage.com/files/img/"
PAGE_SIZE = 50
MAX_PAGES = 20

ONE_PIECE = 9883
CARTE_A_L_UNITE = 10419
LEADER = 10415
SECRET_RARE = 1346
SUPER_RARE = 1347
ALTERNATIVE_ART = 12863
RARITIES = {
    LEADER: "Leader alternatif",
    SECRET_RARE: "Secret Rare",
    SUPER_RARE: "Super Rare",
}
LANGUAGES = {"fr": "VF", "en": "EN", "jp": "JP"}


def extraire_carte(produit):
    taxonomies = {
        champ["name"]: champ["values"]
        for champ in produit["taxonomies"]
    }
    if not any(v["id"] == CARTE_A_L_UNITE for v in taxonomies.get("product_type_id", [])):
        return None

    raretes = taxonomies.get("rarity_id", [])
    if len(raretes) != 1 or (rarete := raretes[0]["id"]) not in RARITIES:
        return None

    traitements = taxonomies.get("treatment_id", [])
    alternatif = any(
        v["id"] == ALTERNATIVE_ART
        or any(mot in v["name_fr"].casefold() for mot in ("alternativ", "parallèle"))
        for v in traitements
    )
    manga = any("manga" in v["name_fr"].casefold() for v in traitements)
    if (rarete == LEADER and not alternatif) or (
        rarete != LEADER and (alternatif or manga)
    ):
        return None

    if produit["canSelling"] is not True:
        return None
    if produit["isPreorderWithStock"] is True:
        statut = "PREORDER"
    elif produit["isPreorder"] is False and produit["isStock"] is True:
        statut = "AVAILABLE"
    else:
        return None

    nom = produit["name"].strip()
    prix = produit["price_discount"] if produit.get("isDiscount") else produit["price"]
    if not nom or not isinstance(prix, (int, float)) or prix < 0:
        raise ValueError("Carte Parkage sans nom ou prix valide")

    lien = f"{BASE_URL}/fr/{produit['id']}"
    editions = [
        v["abreviation"] or v["name_fr"] for v in taxonomies.get("set_id", [])
    ]
    details = " · ".join(filter(None, [
        RARITIES[rarete], *editions, produit.get("state_fr"),
    ]))
    image = produit.get("image_url_1") or ""
    return {
        "site": BOUTIQUE,
        "name": nom,
        "price": f"{prix:.2f}".replace(".", ",") + " €",
        "status": statut,
        "link": lien,
        "image": IMAGE_URL + quote(image.lstrip("/")) if image else "",
        "language": LANGUAGES.get(produit.get("lang"), "OTHER"),
        "card_details": details,
    }


def lire_recherche(session, filtres):
    params = {
        "category_id": ONE_PIECE,
        "product_type_id": CARTE_A_L_UNITE,
        "locale": "fr",
        "complete": "true",
        "count": "true",
        "limit": PAGE_SIZE,
        "order": "relevance",
        "direction": "DESC",
        **filtres,
    }
    total = None
    references = set()
    for page in range(MAX_PAGES):
        noter_requete()
        reponse = session.get(
            API_URL,
            params={**params, "offset": page * PAGE_SIZE},
            timeout=20,
        )
        reponse.raise_for_status()
        resultat = reponse.json()
        if resultat["type"] != "success":
            raise RuntimeError("Recherche Parkage non aboutie")

        donnees = resultat["data"]
        nombre = donnees["count"]
        produits = donnees["list"]
        if type(nombre) is not int or not 0 <= nombre <= PAGE_SIZE * MAX_PAGES:
            raise RuntimeError("Nombre de cartes Parkage hors limites")
        if total is None:
            total = nombre
        if (
            nombre != total
            or not isinstance(produits, list)
            or len(produits) != min(PAGE_SIZE, total - len(references))
        ):
            raise RuntimeError("La pagination des cartes Parkage a changé pendant le scan")

        for produit in produits:
            identifiant = produit["id"]
            if type(identifiant) is not int or identifiant <= 0 or identifiant in references:
                raise RuntimeError("Identifiant de carte Parkage invalide ou dupliqué")
            references.add(identifiant)
            yield produit

        if len(references) == total:
            return


def scan():
    produits = {}
    recherches = (
        {"rarity_id": LEADER, "treatment_id": ALTERNATIVE_ART},
        {"rarity_id": [SECRET_RARE, SUPER_RARE]},
    )
    with requests.Session() as session:
        for filtres in recherches:
            for fiche in lire_recherche(session, filtres):
                carte = extraire_carte(fiche)
                if carte:
                    produits[carte["link"]] = carte
    return produits
