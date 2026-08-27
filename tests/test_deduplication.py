import unittest
from pathlib import Path

from deduplication import (
    charger_etat,
    filtrer_alertes,
    mettre_a_jour_etat,
    sauvegarder_etat,
)


LIEN = "https://example.com/product"


def alerte(status="AVAILABLE"):
    return {
        "site": "Boutique",
        "name": "Produit",
        "link": LIEN,
        "status": status,
        "type_alerte": "RETOUR EN STOCK",
    }


def stock(status):
    return {
        "Boutique": {
            LIEN: {
                "name": "Produit",
                "link": LIEN,
                "status": status,
            }
        }
    }


class DeduplicationTests(unittest.TestCase):
    def test_same_alert_is_sent_only_once_while_status_is_unchanged(self):
        premiere = alerte()
        etat = mettre_a_jour_etat({}, [premiere], stock("AVAILABLE"))

        self.assertEqual([], filtrer_alertes([alerte()], etat))

    def test_non_orderable_transition_rearms_future_restock(self):
        etat = mettre_a_jour_etat({}, [alerte()], stock("AVAILABLE"))
        etat = mettre_a_jour_etat(etat, [], stock("SOLD OUT"))

        self.assertEqual([alerte()], filtrer_alertes([alerte()], etat))

    def test_temporary_disappearance_does_not_rearm_same_availability(self):
        etat = mettre_a_jour_etat({}, [alerte()], stock("AVAILABLE"))
        etat = mettre_a_jour_etat(etat, [], {"Boutique": {}})

        self.assertEqual([], filtrer_alertes([alerte()], etat))

    def test_missing_link_uses_store_and_name_as_identity(self):
        premiere = {**alerte(), "link": ""}
        deuxieme = {
            **premiere,
            "site": "Autre boutique",
        }

        self.assertEqual(2, len(filtrer_alertes([premiere, deuxieme], {})))

    def test_duplicate_inside_same_batch_is_removed(self):
        self.assertEqual(1, len(filtrer_alertes([alerte(), alerte()], {})))

    def test_state_is_written_atomically(self):
        chemin = Path(".test-tmp") / "deduplication-state-test.json"
        temporaire = Path(str(chemin) + ".tmp")
        try:
            chemin.parent.mkdir(parents=True, exist_ok=True)
            sauvegarder_etat({"key": {"status": "AVAILABLE"}}, chemin)
            self.assertEqual(
                {"key": {"status": "AVAILABLE"}},
                charger_etat(chemin),
            )
        finally:
            chemin.unlink(missing_ok=True)
            temporaire.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
