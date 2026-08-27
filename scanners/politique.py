import re
import unicodedata

from cible import est_cible_prioritaire


PRODUITS_UNITAIRES = (
    "CARTE A L UNITE",
    "CARTES A L UNITE",
    "CARTE INDIVIDUELLE",
    "CARTE SEULE",
    "SINGLE CARD",
    "LOT DE CARTES",
    "LOTS DE CARTES",
    "CARTE GRADEE",
    "CARTES GRADEES",
    "CARTE EXPERTISEE",
    "CARTES EXPERTISEES",
    "PROXY",
)

ACCESSOIRES = (
    "TAPIS DE JEU",
    "PLAYMAT",
    "PLAY MAT",
    "PROTEGE CARTES",
    "PROTECTION DE CARTES",
    "PROTECTIONS DE CARTES",
    "CARD SLEEVES",
    "SLEEVES",
    "DECK BOX",
    "SIDEWINDER",
    "ZIPFOLIO",
    "CLASSEUR",
    "BINDER",
    "ALBUM",
    "PORTFOLIO",
    "PROTECTION EN ACRYLIQUE",
    "ACRYLIC CASE",
)

CARTES_PROMO = (
    "CARTE PROMO",
    "CARTE PROMOTIONNELLE",
    "CARTE EXCLUSIVE",
    "PROMO CARD",
    "PROMOTIONAL CARD",
    "EXCLUSIVE CARD",
    "INCLUT UNE CARTE PROMO",
    "INCLUT UNE CARTE EXCLUSIVE",
    "AVEC CARTE PROMO",
    "AVEC CARTE EXCLUSIVE",
    "INCLUDES PROMO CARD",
    "INCLUDES EXCLUSIVE CARD",
    "WITH PROMO CARD",
    "WITH EXCLUSIVE CARD",
)

LANGUES_EXCLUES = (
    "JAPONAIS",
    "JAPONAISE",
    "JAPANESE",
    "CHINOIS",
    "CHINOISE",
    "CHINESE",
    "COREEN",
    "COREENNE",
    "KOREAN",
)


def normaliser(texte):
    texte = unicodedata.normalize("NFKD", str(texte or ""))
    texte = "".join(
        caractere
        for caractere in texte
        if not unicodedata.combining(caractere)
    )
    texte = re.sub(r"[^A-Z0-9]+", " ", texte.upper())
    return re.sub(r"\s+", " ", texte).strip()


def est_op17(texte):
    """Alias historique : détecte désormais la cible prioritaire configurée."""
    return est_cible_prioritaire(texte)


def contient_carte_promo(texte):
    texte = normaliser(texte)
    return any(marqueur in texte for marqueur in CARTES_PROMO)


def produit_autorise(
    nom,
    description="",
    types=(),
    autoriser_langues_asiatiques=False,
):
    texte = normaliser(
        " ".join(
            [str(nom or ""), str(description or "")]
            + [str(type_produit or "") for type_produit in types]
        )
    )

    if not autoriser_langues_asiatiques:
        if any(marqueur in texte for marqueur in LANGUES_EXCLUES):
            return False

        if re.search(
            r"(?:^| )(?:(?:JP|JPN|JA)|(?:KR|KOR|KO)|(?:CN|CHN))(?: |$)",
            texte,
        ):
            return False

    if any(marqueur in texte for marqueur in PRODUITS_UNITAIRES):
        return False

    if re.search(r"\b(?:OP|EB|PRB|ST|P)\s*\d{2}\s*[- ]\s*\d{3}\b", texte):
        return False

    est_accessoire = any(marqueur in texte for marqueur in ACCESSOIRES)
    if est_accessoire and not contient_carte_promo(texte):
        return False

    return True
