import importlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from boutiques import BOUTIQUES
from comparateur import comparer
from confirmation import confirmer_transitions
from deduplication import (
    charger_etat as charger_alertes_envoyees,
    filtrer_alertes,
    mettre_a_jour_etat as mettre_a_jour_alertes_envoyees,
    sauvegarder_etat as sauvegarder_alertes_envoyees,
)
from etat_technique import (
    charger_chutes,
    charger_pannes,
    enregistrer_chute_candidate,
    mettre_a_jour_pannes,
    sauvegarder_chutes,
    sauvegarder_pannes,
)
from integrite import (
    CatalogueSuspect,
    DROP_CONFIRMATIONS_REQUIRED,
    charger_stock_precedent,
    valider_scan,
)
from notifier import send_discord, send_technical_alert
from mise_a_jour_stock import sauvegarder
from observabilite import (
    commencer_mesure,
    journaliser_echec,
    journaliser_reussite,
)
from scanners.politesse import temporiser_demarrage
from suivi_op17 import analyser_disparitions, sauvegarder_etat


MAX_BOUTIQUES_EN_ERREUR = 1

stock_precedent = charger_stock_precedent()
etat_pannes_precedent = charger_pannes()
etat_chutes = charger_chutes()
etat_alertes_envoyees = charger_alertes_envoyees()


def scanner_boutique(boutique):
    nom = boutique["nom"]
    temporiser_demarrage(nom)
    print(f"🔎 Scan : {nom}")

    module = importlib.import_module(f"scanners.{boutique['scanner']}")
    commencer_mesure()
    try:
        produits = module.scan()
        produits = valider_scan(boutique, produits, stock_precedent)
    except Exception as erreur:
        journaliser_echec(nom, erreur)
        raise

    print(f"📦 {nom} : {len(produits)} produit(s)")
    journaliser_reussite(
        nom,
        produits,
        stock_precedent.get(nom, {}),
    )
    return nom, produits


print("🔎 Lancement surveillance stock")

resultats = {}
erreurs = []

with ThreadPoolExecutor(max_workers=min(4, len(BOUTIQUES))) as executor:
    futures = {
        executor.submit(scanner_boutique, boutique): boutique
        for boutique in BOUTIQUES
    }

    for future in as_completed(futures):
        boutique = futures[future]
        try:
            nom, produits = future.result()
            resultats[nom] = produits
        except Exception as erreur:
            nom = boutique["nom"]
            print(f"❌ Échec du scan {nom} : {erreur}")
            erreurs.append((boutique, erreur))

erreurs_finales = []

for boutique, premiere_erreur in erreurs:
    nom = boutique["nom"]
    derniere_erreur = premiere_erreur
    nombre_tentatives = int(boutique.get("retry_attempts", 2))

    if nombre_tentatives <= 0:
        print(
            f"ℹ️ {nom} : aucune relance automatique "
            "pendant l'indisponibilité connue"
        )
        erreurs_finales.append((boutique, derniere_erreur))
        continue

    for tentative in range(1, nombre_tentatives + 1):
        attente = tentative * 10
        print(
            f"🔁 Nouvelle tentative {tentative}/{nombre_tentatives} pour {nom} "
            f"dans {attente}s"
        )
        time.sleep(attente)

        try:
            _, produits = scanner_boutique(boutique)
            resultats[nom] = produits
            print(f"✅ Scan récupéré : {nom}")
            break
        except Exception as erreur:
            derniere_erreur = erreur
            print(f"⚠️ Nouvelle tentative échouée pour {nom} : {erreur}")
    else:
        erreurs_finales.append((boutique, derniere_erreur))

# Une chute massive cohérente sur deux passages distincts est considérée
# comme une vraie évolution du catalogue. Les retries du même passage ne
# modifient pas l'état persistant, car cette étape n'est exécutée qu'ici.
erreurs_apres_confirmation = []
for boutique, erreur in erreurs_finales:
    nom = boutique["nom"]

    if isinstance(erreur, CatalogueSuspect):
        confirmations = enregistrer_chute_candidate(
            etat_chutes,
            nom,
            erreur.courant,
            erreur.precedent,
            signature=erreur.signature,
            raison=erreur.__class__.__name__,
        )

        if confirmations >= DROP_CONFIRMATIONS_REQUIRED:
            resultats[nom] = erreur.produits
            etat_chutes.pop(nom, None)
            print(
                f"✅ {nom} : chute de catalogue confirmée sur "
                f"{confirmations} passages, nouvelle base acceptée "
                f"({erreur.courant} produits)"
            )
            continue

        print(
            f"🛡️ {nom} : chute suspecte mémorisée "
            f"({confirmations}/{DROP_CONFIRMATIONS_REQUIRED}), "
            "ancien stock conservé"
        )
    else:
        # Une panne réseau ou un autre défaut ne doit pas servir de première
        # confirmation à une future réduction de catalogue.
        etat_chutes.pop(nom, None)

    erreurs_apres_confirmation.append((boutique, erreur))

erreurs_finales = erreurs_apres_confirmation

# Un scan normal annule toute ancienne candidature de chute partielle.
for nom in resultats:
    etat_chutes.pop(nom, None)

# Une chute de catalogue mise en quarantaine n'est pas une panne technique :
# l'ancien stock est conservé et chaque boutique peut confirmer sa nouvelle
# base indépendamment. Elle ne consomme donc pas le budget global de pannes.
erreurs_techniques = [
    (boutique, erreur)
    for boutique, erreur in erreurs_finales
    if not isinstance(erreur, CatalogueSuspect)
]

erreurs_bloquantes = [
    (boutique, erreur)
    for boutique, erreur in erreurs_techniques
    if boutique.get("counts_toward_global_failure", True)
]

if len(erreurs_bloquantes) > MAX_BOUTIQUES_EN_ERREUR:
    boutiques_en_erreur = ", ".join(
        boutique["nom"]
        for boutique, _ in erreurs_bloquantes
    )
    raise RuntimeError(
        f"Contrôle interrompu : plusieurs boutiques en erreur : "
        f"{boutiques_en_erreur}"
    )

for boutique, erreur in erreurs_finales:
    nom = boutique["nom"]
    ancien_boutique = stock_precedent.get(nom)

    if not isinstance(ancien_boutique, dict):
        raise RuntimeError(
            f"Impossible de conserver l'historique de {nom} après échec du scan"
        )

    resultats[nom] = ancien_boutique
    if isinstance(erreur, CatalogueSuspect):
        print(
            f"🛡️ {nom} : conservation de "
            f"{len(ancien_boutique)} ancien(s) produit(s) en attendant confirmation"
        )
    else:
        print(
            f"⚠️ {nom} indisponible : conservation de "
            f"{len(ancien_boutique)} ancien(s) produit(s)"
        )

nouvel_etat_pannes, nouvelles_pannes, retablissements = mettre_a_jour_pannes(
    BOUTIQUES,
    erreurs_techniques,
    etat_pannes_precedent,
)

nouveau_stock = {
    boutique["nom"]: resultats[boutique["nom"]]
    for boutique in BOUTIQUES
}

confirmer_transitions(
    BOUTIQUES,
    stock_precedent,
    nouveau_stock,
)

total = sum(len(produits) for produits in nouveau_stock.values())
print(f"📦 Total : {total} produit(s) analysé(s)")

alertes = comparer(nouveau_stock)
alertes_disparitions, nouvel_etat_op17 = analyser_disparitions(
    stock_precedent,
    nouveau_stock
)
alertes.extend(alertes_disparitions)
alertes.sort(
    key=lambda produit: produit.get("priority", 0),
    reverse=True
)
alertes = filtrer_alertes(alertes, etat_alertes_envoyees)

if alertes:
    print("🚨 ALERTES STOCK")

    for produit in alertes:
        print(
            produit.get("type_alerte", "🚨 ALERTE"),
            ":",
            produit["name"],
        )

    send_discord(alertes)
else:
    print("✅ Aucun changement")

nouvel_etat_alertes_envoyees = mettre_a_jour_alertes_envoyees(
    etat_alertes_envoyees,
    alertes,
    nouveau_stock,
)

if nouvelles_pannes:
    details = "\n".join(
        f"- {nom}: {erreur}"
        for nom, erreur in nouvelles_pannes
    )
    send_technical_alert(
        "⚠️ **BOUTIQUE TEMPORAIREMENT INDISPONIBLE**\n"
        "Le contrôle global continue et l'ancien stock de cette boutique "
        "a été conservé pour éviter de fausses alertes.\n"
        f"{details}"
    )

if retablissements:
    details = "\n".join(f"- {nom}" for nom in retablissements)
    send_technical_alert(
        "✅ **BOUTIQUE DE NOUVEAU DISPONIBLE**\n"
        "Le scanner fonctionne de nouveau normalement.\n"
        f"{details}"
    )

sauvegarder(nouveau_stock)
sauvegarder_etat(nouvel_etat_op17)
sauvegarder_pannes(nouvel_etat_pannes)
sauvegarder_chutes(etat_chutes)
sauvegarder_alertes_envoyees(nouvel_etat_alertes_envoyees)
print("💾 Stock et états techniques sauvegardés")
