import unittest
from datetime import datetime, timezone
from pathlib import Path

from boutiques import configurations_boutiques


class ScannerHealthWorkflowTests(unittest.TestCase):
    def setUp(self):
        repository = Path(__file__).resolve().parents[1]
        self.workflow = (
            repository / ".github" / "workflows" / "scanner-health.yml"
        ).read_text(encoding="utf-8")

    def test_health_check_reuses_production_integrity_validation(self):
        self.assertIn("from boutiques import BOUTIQUES", self.workflow)
        self.assertIn(
            "from integrite import charger_stock_precedent, valider_scan",
            self.workflow,
        )
        self.assertIn("valider_scan(", self.workflow)
        self.assertIn("stock_precedent", self.workflow)

    def test_known_outage_tolerance_requires_matching_error_message(self):
        self.assertIn("health_allowed_failure_messages", self.workflow)
        self.assertIn("any(", self.workflow)
        self.assertIn("fragment in message", self.workflow)
        self.assertIn("panne d'accès connue tolérée", self.workflow)

        configurations = configurations_boutiques(
            datetime(2026, 8, 16, 21, 59, tzinfo=timezone.utc)
        )
        playin = next(
            boutique
            for boutique in configurations
            if boutique["scanner"] == "playin"
        )
        messages = tuple(playin.get("health_allowed_failure_messages", ()))
        self.assertTrue(messages)
        self.assertIn(
            "Playin ne fournit pas son catalogue rendu au tracker",
            messages,
        )
        self.assertNotIn("statut inconnu", messages)
        self.assertNotIn("lien incohérent", messages)


if __name__ == "__main__":
    unittest.main()
