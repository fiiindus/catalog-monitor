import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import premium_bandai_health as health


class WorkflowOwnershipTests(unittest.TestCase):
    def test_scanners_keep_one_writer_and_watchdog_has_an_independent_queue(self):
        workflows = Path(__file__).resolve().parents[1] / ".github" / "workflows"
        groups = {}
        for name in ("check", "premium-bandai", "premium-bandai-health"):
            workflow = (workflows / (name + ".yml")).read_text(encoding="utf-8")
            block = re.search(r"^concurrency:\n((?:[ \t]+[^\n]*\n)+)",
                              workflow, re.MULTILINE).group(1)
            groups[name] = re.search(r"group: (.+)", block).group(1)
            self.assertIn("cancel-in-progress: false", block)
            self.assertIn("queue: max", block)
        self.assertEqual(groups["check"], groups["premium-bandai"])
        self.assertNotEqual(groups["check"], groups["premium-bandai-health"])
        workflow = (workflows / "premium-bandai-health.yml").read_text(encoding="utf-8")
        self.assertIn("git add " + health.INCIDENT_FILE, workflow)
        self.assertNotIn("git add " + health.STATE_FILE, workflow)


class IndependentFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.scan_file = Path(self.directory.name) / "scan.json"
        self.incident_file = Path(self.directory.name) / "incident.json"
        self.now = datetime(2026, 11, 23, 22, tzinfo=timezone.utc)
        for name, value in (("STATE_FILE", os.fspath(self.scan_file)),
                            ("INCIDENT_FILE", os.fspath(self.incident_file))):
            p = patch.object(health, name, value)
            p.start()
            self.addCleanup(p.stop)

    def write_scan(self, age=0, **fields):
        state = {"last_complete_at": (self.now - timedelta(seconds=age)).isoformat(),
                 "degraded_notified": False, **fields}
        self.scan_file.write_text(json.dumps(state), encoding="utf-8")

    def check(self, notify, dry_run=False):
        with patch.object(health, "maintenant", return_value=self.now), \
                patch.object(health, "send_technical_alert", notify):
            return health.controler_fraicheur(dry_run)

    def test_checker_does_not_overwrite_a_scan_completed_while_it_notifies(self):
        self.write_scan(age=1800)
        notify = Mock(side_effect=lambda message: self.write_scan(errors=[]))
        self.assertTrue(self.check(notify))
        self.assertEqual(self.now.isoformat(), json.loads(
            self.scan_file.read_text())["last_complete_at"])
        self.assertEqual({"stale_notified": True}, json.loads(
            self.incident_file.read_text()))

    def test_incident_deduplication_and_recovery_use_independent_file(self):
        self.write_scan(age=1800)
        notify = Mock()
        self.assertTrue(self.check(notify))
        self.assertTrue(self.check(notify))
        self.assertEqual(1, notify.call_count)
        self.write_scan()
        self.assertFalse(self.check(notify))
        self.assertFalse(self.check(notify))
        self.assertEqual(2, notify.call_count)
        self.assertEqual({"stale_notified": False}, json.loads(
            self.incident_file.read_text()))

    def test_existing_acknowledged_incident_is_migrated_without_duplicate(self):
        self.write_scan(age=1800, stale_notified=True)
        notify = Mock()
        original = self.scan_file.read_bytes()
        self.assertTrue(self.check(notify))
        notify.assert_not_called()
        self.assertEqual(original, self.scan_file.read_bytes())

    def test_dry_run_writes_neither_file_and_sends_no_notification(self):
        self.write_scan(age=1800)
        original = self.scan_file.read_bytes()
        notify = Mock()
        self.assertTrue(self.check(notify, dry_run=True))
        notify.assert_not_called()
        self.assertEqual(original, self.scan_file.read_bytes())
        self.assertFalse(self.incident_file.exists())


if __name__ == "__main__":
    unittest.main()
