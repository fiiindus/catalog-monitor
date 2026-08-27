import unittest

from cible import CIBLE_PRIORITAIRE
from suivi_op17 import analyser_disparitions


LIEN = "https://example.com/priority-display"
PRODUIT = {
    "site": "Boutique test",
    "name": f"One Piece {CIBLE_PRIORITAIRE} Display 24 boosters VF",
    "price": "144,95 €",
    "status": "COMING_SOON",
    "link": LIEN,
    "image": "",
}


class SuiviPrioritaireTests(unittest.TestCase):
    def test_disappearance_alerts_only_after_two_scans(self):
        ancien = {"Boutique test": {LIEN: PRODUIT}}
        nouveau = {"Boutique test": {}}

        alertes_1, etat_1 = analyser_disparitions(
            ancien,
            nouveau,
            etat={},
        )
        self.assertEqual(alertes_1, [])
        self.assertEqual(next(iter(etat_1.values()))["compteur"], 1)

        alertes_2, etat_2 = analyser_disparitions(
            {"Boutique test": {}},
            nouveau,
            etat=etat_1,
        )
        self.assertEqual(len(alertes_2), 1)
        self.assertEqual(
            alertes_2[0]["type_alerte"],
            f"PRODUIT {CIBLE_PRIORITAIRE} RETIRÉ DU CATALOGUE",
        )
        self.assertEqual(
            alertes_2[0]["priority_target"],
            CIBLE_PRIORITAIRE,
        )
        self.assertEqual(next(iter(etat_2.values()))["compteur"], 2)

        alertes_3, etat_3 = analyser_disparitions(
            {"Boutique test": {}},
            nouveau,
            etat=etat_2,
        )
        self.assertEqual(alertes_3, [])
        self.assertEqual(next(iter(etat_3.values()))["compteur"], 2)
        self.assertEqual(etat_3, etat_2)

    def test_already_alerted_large_counter_is_normalized_once(self):
        cle = "Boutique test|https://example.com/priority-display"
        etat = {
            cle: {
                "boutique": "Boutique test",
                "produit": PRODUIT,
                "compteur": 79,
                "alerte_envoyee": True,
            }
        }

        alertes, nouvel_etat = analyser_disparitions(
            {"Boutique test": {}},
            {"Boutique test": {}},
            etat=etat,
        )

        self.assertEqual(alertes, [])
        self.assertEqual(nouvel_etat[cle]["compteur"], 2)
        self.assertTrue(nouvel_etat[cle]["alerte_envoyee"])

    def test_reappearance_resets_missing_state(self):
        _, etat = analyser_disparitions(
            {"Boutique test": {LIEN: PRODUIT}},
            {"Boutique test": {}},
            etat={},
        )

        alertes, nouvel_etat = analyser_disparitions(
            {"Boutique test": {}},
            {"Boutique test": {LIEN: PRODUIT}},
            etat=etat,
        )
        self.assertEqual(alertes, [])
        self.assertEqual(nouvel_etat, {})

    def test_non_priority_products_are_ignored(self):
        produit = {**PRODUIT, "name": "One Piece OP01 Display"}
        if CIBLE_PRIORITAIRE == "OP01":
            produit["name"] = "One Piece OP02 Display"

        alertes, etat = analyser_disparitions(
            {"Boutique test": {LIEN: produit}},
            {"Boutique test": {}},
            etat={},
        )
        self.assertEqual(alertes, [])
        self.assertEqual(etat, {})

    def test_state_from_previous_priority_target_is_discarded(self):
        ancien_nom = "One Piece OP01 Display"
        if CIBLE_PRIORITAIRE == "OP01":
            ancien_nom = "One Piece OP02 Display"
        ancien_produit = {**PRODUIT, "name": ancien_nom}
        cle = "Boutique test|https://example.com/ancienne-cible"
        etat = {
            cle: {
                "boutique": "Boutique test",
                "produit": ancien_produit,
                "compteur": 2,
                "alerte_envoyee": True,
            }
        }

        alertes, nouvel_etat = analyser_disparitions(
            {"Boutique test": {}},
            {"Boutique test": {}},
            etat=etat,
        )

        self.assertEqual(alertes, [])
        self.assertEqual(nouvel_etat, {})


if __name__ == "__main__":
    unittest.main()
