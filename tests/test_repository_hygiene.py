import re
import unittest
from pathlib import Path


class RepositoryHygieneTests(unittest.TestCase):
    def test_no_test_scripts_remain_at_repository_root(self):
        repository = Path(__file__).resolve().parents[1]
        fichiers = sorted(path.name for path in repository.glob("test_*.py"))
        self.assertEqual([], fichiers)

    def test_github_actions_are_pinned_to_full_shas(self):
        repository = Path(__file__).resolve().parents[1]
        workflows = repository / ".github" / "workflows"
        non_epingles = []
        motif = re.compile(r"^\s*uses:\s*[^@\s]+@([0-9a-fA-F]{40})(?:\s+#.*)?$")

        for path in sorted(workflows.glob("*.yml")):
            for numero, ligne in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if "uses:" not in ligne:
                    continue
                if motif.match(ligne) is None:
                    non_epingles.append(f"{path.name}:{numero}: {ligne.strip()}")

        self.assertEqual([], non_epingles)

    def test_config_contains_only_active_top_level_settings(self):
        import json

        repository = Path(__file__).resolve().parents[1]
        config = json.loads((repository / "config.json").read_text(encoding="utf-8"))
        self.assertEqual({"priority_set", "priority"}, set(config))

    def test_every_persistent_state_file_is_saved_by_the_tracker_workflow(self):
        repository = Path(__file__).resolve().parents[1]
        workflow = (
            repository / ".github" / "workflows" / "check.yml"
        ).read_text(encoding="utf-8")

        for nom in (
            "ancien_stock.json",
            "op17_missing.json",
            "boutiques_unavailable.json",
            "catalogue_drop_state.json",
            "alertes_envoyees.json",
        ):
            self.assertIn(nom, workflow)

    def test_unit_tests_cover_main_code_changes_and_html_fixtures(self):
        repository = Path(__file__).resolve().parents[1]
        workflow = (
            repository / ".github" / "workflows" / "test-oupi-playin.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("push:", workflow)
        self.assertIn("- main", workflow)
        self.assertIn('"tests/fixtures/**"', workflow)
        self.assertIn('"config.json"', workflow)

    def test_local_test_artifacts_are_ignored(self):
        repository = Path(__file__).resolve().parents[1]
        gitignore = (repository / ".gitignore").read_text(encoding="utf-8")

        self.assertIn(".test-tmp/", gitignore)
        self.assertIn(".python-packages/", gitignore)


if __name__ == "__main__":
    unittest.main()
