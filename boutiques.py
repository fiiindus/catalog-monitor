from datetime import datetime, timezone


_CLES_EXCEPTION_TEMPORAIRE = (
    "retry_attempts",
    "counts_toward_global_failure",
    "suppress_technical_alert",
    "health_allowed_failure_messages",
    "known_outage_reason",
    "known_outage_until",
)

_CLES_SIGNALANT_PANNE_CONNUE = (
    "counts_toward_global_failure",
    "suppress_technical_alert",
    "health_allowed_failure_messages",
    "known_outage_reason",
)


_BOUTIQUES_CONFIG = [

    {
        "nom": "Figurines Goodies",
        "url": "https://www.figurines-goodies.com/650-carte-a-jouer-one-piece",
        "scanner": "figurines_goodies"
    },

    {
        "nom": "UltraJeux",
        "url": "https://www.ultrajeux.com/cat-0-1031--one-piece-card-game.html",
        "scanner": "ultrajeux"
    },

    {
        "nom": "Premium Bandai US",
        "url": "https://p-bandai.com/us/series/onepiece-series",
        "scanner": "premium_bandai",
        "minimum_count_ratio": 0.85,
        "minimum_overlap_ratio": 0.85
    },

    {
        "nom": "Parkage",
        "url": "https://www.parkage.com/fr/one-piece-card-game",
        "scanner": "parkage"
    },

    {
        "nom": "Philibert",
        "url": "https://www.philibertnet.com/fr/17214-one-piece-le-jeu-de-cartes",
        "scanner": "philibert"
    },

    {
        "nom": "Carte One Piece",
        "url": "https://carteonepiece.fr/pages/articles-en-precommandes",
        "scanner": "carte_one_piece",
        "allow_empty": True,
        "minimum_count_ratio": 0
    },

    {
        "nom": "Oupi",
        "url": "https://oupi.eu/fr/382-one-piece",
        "scanner": "oupi"
    },

    {
        "nom": "Playin",
        "url": "https://www.play-in.com/fr/gamme/24/one-piece/catalogue",
        "scanner": "playin",
        "retry_attempts": 0,
        "counts_toward_global_failure": False,
        "suppress_technical_alert": True,
        "known_outage_reason": "Fermeture temporaire annoncée par Playin",
        "known_outage_until": "2026-08-17T00:00:00+02:00",
        "health_allowed_failure_messages": (
            "Playin ne fournit pas son catalogue rendu au tracker",
            "Playin a renvoyé un catalogue vide ou non chargé",
        ),
    }

]


def panne_connue_active(boutique, maintenant=None):
    expiration = boutique.get("known_outage_until")
    if not expiration:
        return False

    limite = datetime.fromisoformat(expiration)
    if limite.tzinfo is None:
        raise ValueError(
            f"known_outage_until doit contenir un fuseau horaire : {expiration}"
        )

    maintenant = maintenant or datetime.now(timezone.utc)
    if maintenant.tzinfo is None:
        raise ValueError("maintenant doit contenir un fuseau horaire")
    return maintenant < limite


def configuration_effective(boutique, maintenant=None):
    configuration = dict(boutique)
    expiration = configuration.get("known_outage_until")
    declare_panne_connue = any(
        cle in configuration
        for cle in _CLES_SIGNALANT_PANNE_CONNUE
    )

    if declare_panne_connue and not expiration:
        raise ValueError(
            f"L'exception temporaire de {configuration.get('nom', 'boutique')} "
            "doit avoir une date known_outage_until"
        )

    if not expiration:
        return configuration

    if panne_connue_active(configuration, maintenant):
        return configuration

    for cle in _CLES_EXCEPTION_TEMPORAIRE:
        configuration.pop(cle, None)
    return configuration


def configurations_boutiques(maintenant=None):
    return [
        configuration_effective(boutique, maintenant)
        for boutique in _BOUTIQUES_CONFIG
    ]


BOUTIQUES = configurations_boutiques()
