import unittest

from etat_technique import enregistrer_chute_candidate, mettre_a_jour_pannes


class TechnicalStateTests(unittest.TestCase):
    def test_outage_alert_is_sent_only_on_transition(self):
        boutique = {"nom": "Boutique", "scanner": "test"}
        erreur = RuntimeError("503")

        etat_1, nouvelles_1, retablissements_1 = mettre_a_jour_pannes(
            [boutique],
            [(boutique, erreur)],
            {},
        )
        self.assertEqual(1, len(nouvelles_1))
        self.assertEqual([], retablissements_1)

        etat_2, nouvelles_2, retablissements_2 = mettre_a_jour_pannes(
            [boutique],
            [(boutique, erreur)],
            etat_1,
        )
        self.assertEqual([], nouvelles_2)
        self.assertEqual([], retablissements_2)
        self.assertIn("Boutique", etat_2)

    def test_recovery_is_reported_once(self):
        boutique = {"nom": "Boutique", "scanner": "test"}
        precedent = {"Boutique": {"error": "503"}}

        etat, nouvelles, retablissements = mettre_a_jour_pannes(
            [boutique],
            [],
            precedent,
        )
        self.assertEqual({}, etat)
        self.assertEqual([], nouvelles)
        self.assertEqual(["Boutique"], retablissements)

        _, _, retablissements_suivants = mettre_a_jour_pannes(
            [boutique],
            [],
            etat,
        )
        self.assertEqual([], retablissements_suivants)

    def test_known_outage_is_recorded_without_initial_alert(self):
        boutique = {
            "nom": "Playin",
            "scanner": "playin",
            "suppress_technical_alert": True,
        }
        etat, nouvelles, _ = mettre_a_jour_pannes(
            [boutique],
            [(boutique, RuntimeError("403"))],
            {},
        )
        self.assertIn("Playin", etat)
        self.assertEqual([], nouvelles)

    def test_suspicious_drop_requires_two_consistent_passages(self):
        etat = {}
        confirmation_1 = enregistrer_chute_candidate(
            etat,
            "Boutique",
            60,
            100,
        )
        confirmation_2 = enregistrer_chute_candidate(
            etat,
            "Boutique",
            62,
            100,
        )

        self.assertEqual(1, confirmation_1)
        self.assertEqual(2, confirmation_2)
        self.assertEqual(2, etat["Boutique"]["confirmations"])

    def test_inconsistent_drop_restarts_confirmation(self):
        etat = {}
        enregistrer_chute_candidate(etat, "Boutique", 60, 100)
        confirmation = enregistrer_chute_candidate(etat, "Boutique", 35, 100)

        self.assertEqual(1, confirmation)
        self.assertEqual(35, etat["Boutique"]["count"])

    def test_different_catalogue_fingerprint_restarts_confirmation(self):
        etat = {}
        enregistrer_chute_candidate(
            etat,
            "Boutique",
            60,
            100,
            signature="catalogue-a",
            raison="RecoupementCatalogueSuspect",
        )
        confirmation = enregistrer_chute_candidate(
            etat,
            "Boutique",
            60,
            100,
            signature="catalogue-b",
            raison="RecoupementCatalogueSuspect",
        )

        self.assertEqual(1, confirmation)
        self.assertEqual("catalogue-b", etat["Boutique"]["signature"])


if __name__ == "__main__":
    unittest.main()
