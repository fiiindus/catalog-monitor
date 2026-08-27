import os
import time
from urllib.parse import urlparse

import requests


MAX_DISCORD_ATTEMPTS = 4
RETRYABLE_DISCORD_STATUSES = {429, 500, 502, 503, 504}


def libelle_priorite(alert):
    if alert.get("priority_target") == "OP17":
        return "🔥 OP17 — PRIORITÉ ABSOLUE"

    return str(alert.get("priority", 0))


def ligne_disponibilite(alert):
    disponibilite = alert.get("availability")

    if not disponibilite:
        return ""

    return "\n\n📅 **Disponibilité annoncée :** " + str(disponibilite)


def url_http_valide(valeur):
    if not valeur:
        return ""

    url = str(valeur).strip()
    parties = urlparse(url)

    if parties.scheme not in {"http", "https"} or not parties.netloc:
        return ""

    return url


def tronquer(valeur, limite):
    texte = str(valeur or "")

    if len(texte) <= limite:
        return texte

    return texte[: limite - 1] + "…"


def delai_nouvelle_tentative(response, tentative):
    if response is not None and response.status_code == 429:
        try:
            valeur = float(response.json().get("retry_after", 0))
        except (AttributeError, TypeError, ValueError):
            valeur = 0

        if valeur <= 0:
            try:
                valeur = float(response.headers.get("Retry-After", 0))
            except (AttributeError, TypeError, ValueError):
                valeur = 0

        if valeur > 0:
            return min(valeur, 30)

    return min(2 ** tentative, 10)


def envoyer_payload_discord(webhook, payload):
    derniere_erreur = None

    for tentative in range(MAX_DISCORD_ATTEMPTS):
        response = None

        try:
            response = requests.post(webhook, json=payload, timeout=20)
        except requests.RequestException as erreur:
            derniere_erreur = erreur
        else:
            if response.status_code == 204:
                print("✅ Discord envoyé :", response.status_code)
                return

            derniere_erreur = RuntimeError(
                f"Discord a refusé l'alerte avec le statut "
                f"{response.status_code}"
            )

            if response.status_code not in RETRYABLE_DISCORD_STATUSES:
                raise derniere_erreur

        if tentative == MAX_DISCORD_ATTEMPTS - 1:
            break

        attente = delai_nouvelle_tentative(response, tentative)
        print(
            f"⚠️ Discord indisponible, nouvelle tentative "
            f"dans {attente:g}s"
        )
        time.sleep(attente)

    raise RuntimeError(
        "Impossible de remettre les alertes à Discord après plusieurs essais"
    ) from derniere_erreur


def obtenir_webhook_discord():
    webhook = os.environ.get("DISCORD_WEBHOOK", "").strip()

    if not webhook:
        raise RuntimeError(
            "DISCORD_WEBHOOK manquant : l'historique ne doit pas être sauvegardé"
        )

    return webhook


def obtenir_webhook_technique_discord():
    webhook = os.environ.get("DISCORD_ERROR_WEBHOOK", "").strip()

    if not webhook:
        raise RuntimeError(
            "DISCORD_ERROR_WEBHOOK manquant : alerte technique impossible"
        )

    return webhook


def construire_embed(alert):
    description = f"""
🚨 **{alert.get('type_alerte', 'ALERTE STOCK')}**

🏪 **Boutique :** {alert.get('boutique', alert.get('site', 'Inconnu'))}

🏷️ **Catégorie :** {alert.get('category', 'AUTRE')}

🌍 **Langue :** {alert.get('language', 'AUTRE')}

⭐ **Priorité :** {libelle_priorite(alert)}

💰 **Prix :** {alert.get('price', 'Non disponible')}

📌 **Statut :** {alert.get('status', 'Inconnu')}{ligne_disponibilite(alert)}
"""

    embed = {
        "title": tronquer(alert.get("name", "Produit inconnu"), 256),
        "description": tronquer(description, 4096),
    }

    lien = url_http_valide(alert.get("link"))
    image = url_http_valide(alert.get("image"))

    if lien:
        embed["url"] = lien

    if image:
        embed["thumbnail"] = {"url": image}

    return embed


def send_discord(alerts):
    if not alerts:
        return

    webhook = obtenir_webhook_discord()
    embeds = [construire_embed(alert) for alert in alerts]

    for index in range(0, len(embeds), 10):
        envoyer_payload_discord(
            webhook,
            {"embeds": embeds[index:index + 10]},
        )


def send_technical_alert(message):
    webhook = obtenir_webhook_technique_discord()
    envoyer_payload_discord(
        webhook,
        {"content": tronquer(message, 2000)},
    )
