import importlib
import json
from html.parser import HTMLParser

from integrite import normaliser_identite_lien


STATUTS_COMMANDABLES = {"AVAILABLE", "PREORDER"}
STATUTS_CONFIRMES = STATUTS_COMMANDABLES | {"SOLD OUT", "STORE_ONLY"}
MAX_CONFIRMATIONS_PAR_BOUTIQUE = 3

SCHEMA_STATUS = {
    "instock": "AVAILABLE",
    "limitedavailability": "AVAILABLE",
    "onlineonly": "AVAILABLE",
    "preorder": "PREORDER",
    "presale": "PREORDER",
    "outofstock": "SOLD OUT",
    "soldout": "SOLD OUT",
    "discontinued": "SOLD OUT",
}


class ExtracteurDonneesStructurees(HTMLParser):
    def __init__(self):
        super().__init__()
        self._capture_json_ld = False
        self._morceaux = []
        self.json_ld = []
        self.meta_availability = []

    def handle_starttag(self, tag, attrs):
        attributs = {str(cle).lower(): valeur for cle, valeur in attrs}
        if tag.lower() == "script" and (
            str(attributs.get("type", "")).lower()
            == "application/ld+json"
        ):
            self._capture_json_ld = True
            self._morceaux = []

        if tag.lower() == "meta":
            nom = str(
                attributs.get("itemprop")
                or attributs.get("property")
                or ""
            ).lower()
            if "availability" in nom:
                self.meta_availability.append(
                    str(attributs.get("content", ""))
                )

    def handle_data(self, data):
        if self._capture_json_ld:
            self._morceaux.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self._capture_json_ld:
            self.json_ld.append("".join(self._morceaux))
            self._capture_json_ld = False
            self._morceaux = []


def normaliser_statut_schema(valeur):
    texte = str(valeur or "").strip().lower().rstrip("/")
    cle = texte.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    return SCHEMA_STATUS.get(cle)


def _chercher_availability(valeur):
    if isinstance(valeur, dict):
        statut = normaliser_statut_schema(valeur.get("availability"))
        if statut:
            return statut
        for enfant in valeur.values():
            statut = _chercher_availability(enfant)
            if statut:
                return statut
    elif isinstance(valeur, list):
        for enfant in valeur:
            statut = _chercher_availability(enfant)
            if statut:
                return statut
    return None


def extraire_statut_structure(html):
    extracteur = ExtracteurDonneesStructurees()
    extracteur.feed(str(html or ""))

    for valeur in extracteur.meta_availability:
        statut = normaliser_statut_schema(valeur)
        if statut:
            return statut

    for bloc in extracteur.json_ld:
        try:
            donnees = json.loads(bloc)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        statut = _chercher_availability(donnees)
        if statut:
            return statut

    return None


def confirmer_url(produit, get=None):
    if get is None:
        import requests

        get = requests.get

    reponse = get(
        produit["link"],
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; onepiece-stock-tracker/1.0)"
            ),
        },
        timeout=30,
    )
    reponse.raise_for_status()
    return extraire_statut_structure(reponse.text)


def _ancien_produit(ancien_boutique, lien):
    produit = ancien_boutique.get(lien)
    if produit is not None:
        return produit

    index = {
        normaliser_identite_lien(ancien_lien): ancien_produit
        for ancien_lien, ancien_produit in ancien_boutique.items()
    }
    return index.get(normaliser_identite_lien(lien))


def confirmer_transitions(
    boutiques,
    stock_precedent,
    nouveau_stock,
    importer=importlib.import_module,
    confirmation_generique=confirmer_url,
):
    configurations = {boutique["nom"]: boutique for boutique in boutiques}

    for nom, produits in nouveau_stock.items():
        ancien_boutique = stock_precedent.get(nom)
        if not isinstance(ancien_boutique, dict):
            continue

        candidats = []
        for lien, produit in produits.items():
            if produit.get("status") not in STATUTS_COMMANDABLES:
                continue
            ancien = _ancien_produit(ancien_boutique, lien)
            if ancien and ancien.get("status") == produit.get("status"):
                continue
            candidats.append((lien, produit))

        candidats.sort(
            key=lambda element: element[1].get("priority", 0),
            reverse=True,
        )
        configuration = configurations.get(nom, {})
        limite = int(
            configuration.get(
                "maximum_conditional_confirmations",
                MAX_CONFIRMATIONS_PAR_BOUTIQUE,
            )
        )
        module = importer(f"scanners.{configuration['scanner']}")
        confirmer = getattr(
            module,
            "confirmer_disponibilite",
            confirmation_generique,
        )

        for _, produit in candidats[:max(0, limite)]:
            try:
                statut_confirme = confirmer(produit)
            except Exception as erreur:
                print(
                    f"⚠️ {nom} : confirmation conditionnelle impossible pour "
                    f"{produit.get('name', 'Produit inconnu')} ({erreur})"
                )
                continue

            if statut_confirme not in STATUTS_CONFIRMES:
                print(
                    f"ℹ️ {nom} : confirmation conditionnelle non concluante "
                    f"pour {produit.get('name', 'Produit inconnu')}"
                )
                continue

            produit["status"] = statut_confirme
            if "orderable" in produit or nom == "Premium Bandai US":
                produit["orderable"] = statut_confirme in STATUTS_COMMANDABLES

            if statut_confirme in STATUTS_COMMANDABLES:
                print(
                    f"✅ {nom} : disponibilité confirmée sur la fiche : "
                    f"{produit.get('name', 'Produit inconnu')}"
                )
            else:
                print(
                    f"🛡️ {nom} : faux changement rejeté par la fiche : "
                    f"{produit.get('name', 'Produit inconnu')}"
                )

    return nouveau_stock

