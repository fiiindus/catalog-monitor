import os
import random
import time


DEFAULT_MINIMUM_START_JITTER_SECONDS = 0.75
DEFAULT_MAXIMUM_START_JITTER_SECONDS = 8.0

_RANDOM = random.SystemRandom()


def temporiser_demarrage(
    nom_boutique,
    minimum=DEFAULT_MINIMUM_START_JITTER_SECONDS,
    maximum=DEFAULT_MAXIMUM_START_JITTER_SECONDS,
):
    """Décale légèrement un scan sans ajouter la moindre requête réseau."""
    if os.environ.get("TRACKER_DISABLE_START_JITTER") == "1":
        return 0.0

    minimum = max(0.0, float(minimum))
    maximum = max(minimum, float(maximum))
    attente = _RANDOM.uniform(minimum, maximum)

    print(
        f"🕊️ {nom_boutique} : démarrage courtois dans {attente:.1f}s"
    )
    time.sleep(attente)
    return attente

