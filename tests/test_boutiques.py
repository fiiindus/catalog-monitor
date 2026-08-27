import unittest
from datetime import datetime, timezone

from boutiques import configuration_effective, panne_connue_active


PLAYIN_TEMPORAIRE = {
    "nom": "Playin",
    "scanner": "playin",
    "retry_attempts": 0,
    "counts_toward_global_failure": False,
    "suppress_technical_alert": True,
    "health_allowed_failure_messages": ("panne connue",),
    "known_outage_reason": "Fermeture annoncée",
    "known_outage_until": "2026-08-17T00:00:00+02:00",
}


class BoutiquesTests(unittest.TestCase):
    def test_known_outage_is_active_before_its_expiration(self):
        maintenant = datetime(2026, 8, 16, 21, 59, tzinfo=timezone.utc)

        self.assertTrue(panne_connue_active(PLAYIN_TEMPORAIRE, maintenant))
        self.assertFalse(
            configuration_effective(PLAYIN_TEMPORAIRE, maintenant)[
                "counts_toward_global_failure"
            ]
        )

    def test_known_outage_expires_at_the_declared_instant(self):
        maintenant = datetime(2026, 8, 16, 22, 0, tzinfo=timezone.utc)
        configuration = configuration_effective(PLAYIN_TEMPORAIRE, maintenant)

        self.assertFalse(panne_connue_active(PLAYIN_TEMPORAIRE, maintenant))
        self.assertNotIn("known_outage_until", configuration)
        self.assertNotIn("health_allowed_failure_messages", configuration)
        self.assertNotIn("suppress_technical_alert", configuration)
        self.assertNotIn("counts_toward_global_failure", configuration)
        self.assertNotIn("retry_attempts", configuration)

    def test_known_outage_requires_a_timezone(self):
        configuration = {
            **PLAYIN_TEMPORAIRE,
            "known_outage_until": "2026-08-17T00:00:00",
        }

        with self.assertRaisesRegex(ValueError, "fuseau horaire"):
            panne_connue_active(configuration)

    def test_known_outage_cannot_be_permanent_by_omission(self):
        configuration = dict(PLAYIN_TEMPORAIRE)
        configuration.pop("known_outage_until")

        with self.assertRaisesRegex(ValueError, "known_outage_until"):
            configuration_effective(configuration)

    def test_ordinary_retry_configuration_is_not_treated_as_an_outage(self):
        configuration = {
            "nom": "Boutique",
            "scanner": "boutique",
            "retry_attempts": 1,
        }

        self.assertEqual(configuration, configuration_effective(configuration))


if __name__ == "__main__":
    unittest.main()
