import importlib
from boutiques import BOUTIQUES


resultats = {}


for boutique in BOUTIQUES:

    print("🔎 Scan :", boutique["nom"])


    module = importlib.import_module(
        f"scanners.{boutique['scanner']}"
    )


    produits = module.scan()


    resultats[boutique["nom"]] = produits


    print(
        f"📦 {boutique['nom']} : {len(produits)} produit(s) trouvé(s)"
    )


print("✅ Scan terminé")
