import runpy
import sys
import types
import unittest
from unittest.mock import patch


class SurveillanceRetryTests(unittest.TestCase):
    def construire_modules(
        self,
        boutiques_config,
        scanners,
        stock_precedent,
        compared,
        saved,
        op17_states,
        technical_alerts,
    ):
        boutiques = types.ModuleType("boutiques")
        boutiques.BOUTIQUES = boutiques_config

        comparateur = types.ModuleType("comparateur")
        comparateur.comparer = lambda stock: compared.append(stock) or []

        confirmation = types.ModuleType("confirmation")
        confirmation.confirmer_transitions = (
            lambda configurations, ancien, nouveau: nouveau
        )

        deduplication = types.ModuleType("deduplication")
        deduplication.charger_etat = lambda: {}
        deduplication.filtrer_alertes = lambda alertes, etat: alertes
        deduplication.mettre_a_jour_etat = (
            lambda etat, alertes, stock: etat
        )
        deduplication.sauvegarder_etat = lambda etat: None

        integrite = types.ModuleType("integrite")

        class CatalogueSuspect(RuntimeError):
            pass

        integrite.CatalogueSuspect = CatalogueSuspect
        integrite.DROP_CONFIRMATIONS_REQUIRED = 2
        integrite.charger_stock_precedent = lambda: stock_precedent
        integrite.valider_scan = lambda boutique, produits, ancien: produits

        notifier = types.ModuleType("notifier")
        notifier.send_discord = lambda alertes: None
        notifier.send_technical_alert = (
            lambda message: technical_alerts.append(message)
        )

        mise_a_jour_stock = types.ModuleType("mise_a_jour_stock")
        mise_a_jour_stock.sauvegarder = lambda stock: saved.append(stock)

        observabilite = types.ModuleType("observabilite")
        observabilite.commencer_mesure = lambda: None
        observabilite.journaliser_echec = lambda nom, erreur: None
        observabilite.journaliser_reussite = (
            lambda nom, produits, precedent: None
        )

        suivi_op17 = types.ModuleType("suivi_op17")
        suivi_op17.analyser_disparitions = (
            lambda ancien, nouveau: ([], {"validated": True})
        )
        suivi_op17.sauvegarder_etat = (
            lambda etat: op17_states.append(etat)
        )

        etat_technique = types.ModuleType("etat_technique")
        etat_technique.charger_chutes = lambda: {}
        etat_technique.charger_pannes = lambda: {}
        etat_technique.enregistrer_chute_candidate = (
            lambda etat, nom, nombre, precedent, **kwargs: 1
        )

        def mettre_a_jour_pannes(boutiques_config, erreurs, precedent):
            nouvel_etat = {}
            nouvelles = []
            for boutique, erreur in erreurs:
                nom = boutique["nom"]
                nouvel_etat[nom] = {"error": str(erreur)}
                if not boutique.get("suppress_technical_alert", False):
                    nouvelles.append((nom, erreur))
            return nouvel_etat, nouvelles, []

        etat_technique.mettre_a_jour_pannes = mettre_a_jour_pannes
        etat_technique.sauvegarder_chutes = lambda etat: None
        etat_technique.sauvegarder_pannes = lambda etat: None

        modules = {
            "boutiques": boutiques,
            "comparateur": comparateur,
            "confirmation": confirmation,
            "deduplication": deduplication,
            "etat_technique": etat_technique,
            "integrite": integrite,
            "notifier": notifier,
            "mise_a_jour_stock": mise_a_jour_stock,
            "observabilite": observabilite,
            "suivi_op17": suivi_op17,
        }
        modules.update(scanners)
        return modules

    def test_failed_store_is_retried_with_its_configuration(self):
        attempts = []
        link = "https://example.com/recovered"
        products = {
            link: {
                "name": "Recovered product",
                "link": link,
                "status": "AVAILABLE",
            }
        }
        compared = []
        saved = []
        op17_states = []
        technical_alerts = []

        scanner = types.ModuleType("scanners.retry_probe")

        def scan():
            attempts.append(True)
            if len(attempts) == 1:
                raise RuntimeError("temporary failure")
            return products

        scanner.scan = scan

        fake_modules = self.construire_modules(
            [{"nom": "Boutique test", "scanner": "retry_probe"}],
            {"scanners.retry_probe": scanner},
            {},
            compared,
            saved,
            op17_states,
            technical_alerts,
        )

        with patch.dict(sys.modules, fake_modules), patch(
            "time.sleep", return_value=None
        ):
            runpy.run_module("surveillance", run_name="__main__")

        expected_stock = {"Boutique test": products}
        self.assertEqual(len(attempts), 2)
        self.assertEqual(compared, [expected_stock])
        self.assertEqual(saved, [expected_stock])
        self.assertEqual(op17_states, [{"validated": True}])
        self.assertEqual(technical_alerts, [])

    def test_one_failed_store_keeps_previous_stock_and_scan_continues(self):
        failed_attempts = []
        good_link = "https://example.com/good"
        old_link = "https://example.com/old"
        good_products = {
            good_link: {
                "name": "Good product",
                "link": good_link,
                "status": "AVAILABLE",
            }
        }
        old_products = {
            old_link: {
                "name": "Old product",
                "link": old_link,
                "status": "SOLD OUT",
            }
        }
        stock_precedent = {
            "Boutique HS": old_products,
            "Boutique OK": good_products,
        }
        compared = []
        saved = []
        op17_states = []
        technical_alerts = []

        failed_scanner = types.ModuleType("scanners.failed_probe")

        def failed_scan():
            failed_attempts.append(True)
            raise RuntimeError("403 Forbidden")

        failed_scanner.scan = failed_scan

        good_scanner = types.ModuleType("scanners.good_probe")
        good_scanner.scan = lambda: good_products

        fake_modules = self.construire_modules(
            [
                {"nom": "Boutique HS", "scanner": "failed_probe"},
                {"nom": "Boutique OK", "scanner": "good_probe"},
            ],
            {
                "scanners.failed_probe": failed_scanner,
                "scanners.good_probe": good_scanner,
            },
            stock_precedent,
            compared,
            saved,
            op17_states,
            technical_alerts,
        )

        with patch.dict(sys.modules, fake_modules), patch(
            "time.sleep", return_value=None
        ):
            runpy.run_module("surveillance", run_name="__main__")

        expected_stock = {
            "Boutique HS": old_products,
            "Boutique OK": good_products,
        }
        self.assertEqual(len(failed_attempts), 3)
        self.assertEqual(compared, [expected_stock])
        self.assertEqual(saved, [expected_stock])
        self.assertEqual(op17_states, [{"validated": True}])
        self.assertEqual(len(technical_alerts), 1)
        self.assertIn("Boutique HS", technical_alerts[0])
        self.assertIn("403 Forbidden", technical_alerts[0])

    def test_known_outage_does_not_consume_global_failure_budget(self):
        known_attempts = []
        temporary_attempts = []
        old_known = {
            "https://example.com/known": {
                "name": "Known old product",
                "link": "https://example.com/known",
                "status": "SOLD OUT",
            }
        }
        old_temporary = {
            "https://example.com/temporary": {
                "name": "Temporary old product",
                "link": "https://example.com/temporary",
                "status": "SOLD OUT",
            }
        }
        stock_precedent = {
            "Known outage": old_known,
            "Temporary outage": old_temporary,
        }
        compared = []
        saved = []
        op17_states = []
        technical_alerts = []

        known_scanner = types.ModuleType("scanners.known_probe")

        def known_scan():
            known_attempts.append(True)
            raise RuntimeError("403 Forbidden")

        known_scanner.scan = known_scan

        temporary_scanner = types.ModuleType("scanners.temporary_probe")

        def temporary_scan():
            temporary_attempts.append(True)
            raise RuntimeError("503 Service Unavailable")

        temporary_scanner.scan = temporary_scan

        fake_modules = self.construire_modules(
            [
                {
                    "nom": "Known outage",
                    "scanner": "known_probe",
                    "retry_attempts": 0,
                    "counts_toward_global_failure": False,
                    "suppress_technical_alert": True,
                },
                {
                    "nom": "Temporary outage",
                    "scanner": "temporary_probe",
                },
            ],
            {
                "scanners.known_probe": known_scanner,
                "scanners.temporary_probe": temporary_scanner,
            },
            stock_precedent,
            compared,
            saved,
            op17_states,
            technical_alerts,
        )

        with patch.dict(sys.modules, fake_modules), patch(
            "time.sleep", return_value=None
        ):
            runpy.run_module("surveillance", run_name="__main__")

        expected_stock = {
            "Known outage": old_known,
            "Temporary outage": old_temporary,
        }
        self.assertEqual(len(known_attempts), 1)
        self.assertEqual(len(temporary_attempts), 3)
        self.assertEqual(compared, [expected_stock])
        self.assertEqual(saved, [expected_stock])
        self.assertEqual(op17_states, [{"validated": True}])
        self.assertEqual(len(technical_alerts), 1)
        self.assertNotIn("Known outage", technical_alerts[0])
        self.assertIn("Temporary outage", technical_alerts[0])

    def test_two_failed_stores_still_abort_global_scan(self):
        compared = []
        saved = []
        op17_states = []
        technical_alerts = []

        scanner_a = types.ModuleType("scanners.failed_a")
        scanner_a.scan = lambda: (_ for _ in ()).throw(RuntimeError("failure A"))
        scanner_b = types.ModuleType("scanners.failed_b")
        scanner_b.scan = lambda: (_ for _ in ()).throw(RuntimeError("failure B"))

        fake_modules = self.construire_modules(
            [
                {"nom": "Boutique A", "scanner": "failed_a"},
                {"nom": "Boutique B", "scanner": "failed_b"},
            ],
            {
                "scanners.failed_a": scanner_a,
                "scanners.failed_b": scanner_b,
            },
            {"Boutique A": {}, "Boutique B": {}},
            compared,
            saved,
            op17_states,
            technical_alerts,
        )

        with patch.dict(sys.modules, fake_modules), patch(
            "time.sleep", return_value=None
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "plusieurs boutiques en erreur",
            ):
                runpy.run_module("surveillance", run_name="__main__")

        self.assertEqual(compared, [])
        self.assertEqual(saved, [])
        self.assertEqual(op17_states, [])
        self.assertEqual(technical_alerts, [])


if __name__ == "__main__":
    unittest.main()
