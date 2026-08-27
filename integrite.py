import json
import hashlib
import math
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


STATUTS_VALIDES = {
    "AVAILABLE",
    "PREORDER",
    "COMING_SOON",
    "SOLD OUT",
    "STORE_ONLY",
    "UNKNOWN",
}

DEFAULT_MINIMUM_COUNT_RATIO = 0.65
DEFAULT_MINIMUM_OVERLAP_RATIO = 0.60
DEFAULT_MAXIMUM_UNKNOWN_RATIO = 0.0
DROP_CONFIRMATIONS_REQUIRED = 2

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def normaliser_identite_lien(lien):
    lien = str(lien or "").strip()
    if not lien:
        return ""

    parties = urlsplit(lien)
    requete = [
        (cle, valeur)
        for cle, valeur in parse_qsl(parties.query, keep_blank_values=True)
        if cle.lower() not in TRACKING_QUERY_KEYS
        and not cle.lower().startswith(TRACKING_QUERY_PREFIXES)
    ]
    chemin = parties.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parties.scheme.lower(),
            parties.netloc.lower(),
            chemin,
            urlencode(sorted(requete)),
            "",
        )
    )


def empreinte_catalogue(produits):
    identites = sorted(
        normaliser_identite_lien(lien)
        for lien in produits
    )
    contenu = "\n".join(identites).encode("utf-8")
    return hashlib.sha256(contenu).hexdigest()


def ratio_recoupement(precedent, courant):
    if not precedent:
        return 1.0

    anciens = {
        normaliser_identite_lien(lien)
        for lien in precedent
    }
    nouveaux = {
        normaliser_identite_lien(lien)
        for lien in courant
    }
    return len(anciens & nouveaux) / len(anciens)


class CatalogueSuspect(RuntimeError):
    def __init__(self, nom, produits, precedent, courant, raison):
        self.nom = nom
        self.produits = produits
        self.precedent = precedent
        self.courant = courant
        self.raison = raison
        self.signature = empreinte_catalogue(produits)
        super().__init__(raison)


class ChuteCatalogueSuspecte(CatalogueSuspect):
    def __init__(self, nom, produits, precedent, courant, minimum):
        self.minimum = minimum
        super().__init__(
            nom,
            produits,
            precedent,
            courant,
            f"{nom} a chuté de {precedent} à {courant} produit(s), "
            f"sous le seuil de sécurité {minimum}",
        )


class RecoupementCatalogueSuspect(CatalogueSuspect):
    def __init__(self, nom, produits, precedent, courant, ratio, minimum):
        self.ratio = ratio
        self.minimum = minimum
        super().__init__(
            nom,
            produits,
            precedent,
            courant,
            f"{nom} ne recoupe que {ratio:.0%} de son ancien catalogue, "
            f"sous le seuil de sécurité {minimum:.0%}",
        )


def charger_stock_precedent(chemin="ancien_stock.json"):
    try:
        with open(chemin, "r", encoding="utf-8") as fichier:
            stock = json.load(fichier)
    except FileNotFoundError:
        return {}

    if not isinstance(stock, dict):
        raise RuntimeError("ancien_stock.json ne contient pas un objet valide")

    return stock


def valider_scan(boutique, produits, stock_precedent):
    nom = boutique["nom"]

    if not isinstance(produits, dict):
        raise RuntimeError(f"{nom} a renvoyé un format de stock invalide")

    autorise_vide = boutique.get("allow_empty", False)

    if not produits and not autorise_vide:
        raise RuntimeError(f"{nom} a renvoyé un catalogue vide")

    precedent_boutique = stock_precedent.get(nom, {})

    if not isinstance(precedent_boutique, dict):
        raise RuntimeError(f"L'historique de {nom} est invalide")

    # Le contenu doit être valide avant toute logique de confirmation de chute.
    # Sinon deux catalogues partiels mais mal formés pourraient être acceptés
    # simplement parce qu'ils contiennent un nombre similaire de produits.
    statuts_inconnus = 0

    for lien, produit in produits.items():
        if not isinstance(lien, str) or not lien.strip():
            raise RuntimeError(f"{nom} contient une clé produit invalide")

        if not isinstance(produit, dict):
            raise RuntimeError(f"{nom} contient un produit invalide : {lien}")

        for champ in ("name", "link", "status"):
            if not str(produit.get(champ, "")).strip():
                raise RuntimeError(
                    f"{nom} contient un produit sans {champ} : {lien}"
                )

        if produit["link"] != lien:
            raise RuntimeError(
                f"{nom} contient un lien incohérent : {lien}"
            )

        if produit["status"] not in STATUTS_VALIDES:
            raise RuntimeError(
                f"{nom} contient un statut inconnu : {produit['status']}"
            )

        if produit["status"] == "UNKNOWN":
            statuts_inconnus += 1

    ratio_inconnu_maximum = float(
        boutique.get(
            "maximum_unknown_ratio",
            DEFAULT_MAXIMUM_UNKNOWN_RATIO,
        )
    )

    if produits and statuts_inconnus / len(produits) > ratio_inconnu_maximum:
        raise RuntimeError(
            f"{nom} contient trop de statuts UNKNOWN "
            f"({statuts_inconnus}/{len(produits)})"
        )

    ratio_minimum = float(
        boutique.get("minimum_count_ratio", DEFAULT_MINIMUM_COUNT_RATIO)
    )
    nombre_precedent = len(precedent_boutique)
    nombre_courant = len(produits)

    if ratio_minimum > 0 and nombre_precedent >= 10:
        minimum_accepte = math.ceil(nombre_precedent * ratio_minimum)

        if nombre_courant < minimum_accepte:
            raise ChuteCatalogueSuspecte(
                nom,
                produits,
                nombre_precedent,
                nombre_courant,
                minimum_accepte,
            )

    ratio_recoupement_minimum = float(
        boutique.get(
            "minimum_overlap_ratio",
            DEFAULT_MINIMUM_OVERLAP_RATIO,
        )
    )

    if ratio_recoupement_minimum > 0 and nombre_precedent >= 10:
        ratio = ratio_recoupement(precedent_boutique, produits)
        if ratio < ratio_recoupement_minimum:
            raise RecoupementCatalogueSuspect(
                nom,
                produits,
                nombre_precedent,
                nombre_courant,
                ratio,
                ratio_recoupement_minimum,
            )

    return produits
