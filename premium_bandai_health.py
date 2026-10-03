"""Independent freshness check, callable by the external scheduler."""
import argparse
from datetime import datetime, timezone

from deduplication import charger_etat, sauvegarder_etat
from notifier import send_technical_alert

STATE_FILE = "premium_bandai_health.json"
MAX_AGE_SECONDS = 15 * 60


def maintenant():
    return datetime.now(timezone.utc)


def age_dernier_scan(etat, now):
    valeur = etat.get("last_complete_at")
    if not valeur:
        return None
    try:
        date = datetime.fromisoformat(valeur)
        if date.tzinfo is None:
            return None
        return (now - date).total_seconds()
    except (ValueError, TypeError):
        return None


def verifier(etat, now, notifier=send_technical_alert):
    etat = dict(etat)
    age = age_dernier_scan(etat, now)
    retard = age is None or age >= MAX_AGE_SECONDS or age < 0
    if retard and not etat.get("stale_notified"):
        notifier("🚨 **PREMIUM BANDAI : SURVEILLANCE EN RETARD**\n"
                 "Aucun scan complet confirmé depuis quinze minutes. "
                 "Vérifier les déclenchements et la couverture des sources.")
        etat["stale_notified"] = True
    elif not retard and etat.get("stale_notified"):
        notifier("✅ **PREMIUM BANDAI : SURVEILLANCE RÉTABLIE**\n"
                 "Un scan complet récent est confirmé.")
        etat["stale_notified"] = False
    return etat, retard


def enregistrer_scan(etat, erreurs, now, notifier=send_technical_alert):
    etat = dict(etat)
    etat["last_attempt_at"] = now.isoformat()
    etat["errors"] = erreurs
    if erreurs and not etat.get("degraded_notified"):
        notifier("⚠️ **PREMIUM BANDAI : SCAN INCOMPLET**\n"
                 "Les références récupérées restent surveillées, mais la "
                 "découverte complète n'est pas confirmée.\n" + "\n".join(erreurs[:5]))
        etat["degraded_notified"] = True
    elif not erreurs:
        etat["last_complete_at"] = now.isoformat()
        if etat.get("degraded_notified"):
            notifier("✅ **PREMIUM BANDAI : SOURCES RÉTABLIES**\n"
                     "La découverte et les fiches suivies ont été vérifiées.")
        etat["degraded_notified"] = False
    return etat


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    ancien = charger_etat(STATE_FILE)
    nouveau, retard = verifier(ancien, maintenant(),
                               notifier=print if args.dry_run else send_technical_alert)
    print("Premium Bandai : " + ("scan complet en retard" if retard else "scan complet récent"))
    if not args.dry_run:
        sauvegarder_etat(nouveau, STATE_FILE)


if __name__ == "__main__":
    main()
