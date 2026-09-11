"""Offline regression checks for archived add-ons and their shared notebooks."""
import ast
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FABRIC = ROOT / "3. Fabric"
EXTENDED = FABRIC / "archive" / "extended"
STUDIO = EXTENDED / "Fabric + Copilot Studio"
MIRRORS = (
    Path("3. Fabric") / "archive" / "extended" / "_shared" / "notebooks",
    Path("3. Fabric") / "archive" / "extended" / "Fabric + Copilot Studio" / "notebooks" / "_core",
)
SHARED_NAMES = {
    "Copilot_Agent365_Lander.ipynb",
    "Copilot_Agent365_Registry_Ingester.ipynb",
    "Copilot_Audit_Log_Direct_Ingester.ipynb",
    "Copilot_Cost_Consumption_Ingester.ipynb",
    "Copilot_Licensed_Users_Direct_Ingester.ipynb",
    "Copilot_Org_Data_Direct_Ingester.ipynb",
    "Copilot_ProductFeedback_Ingester.ipynb",
    "ValueLens_Data_Check.ipynb",
}
PROCESSOR = "Copilot_Audit_Log_Processor.ipynb"
COST_FILES = (
    "Copilot_CostConsumption_Email_to_OneLake.json",
    "Copilot_CostConsumption_SharePoint_to_OneLake.json",
    "COST-CONSUMPTION.md",
    "COST-CONSUMPTION-SETUP.md",
)


class ArchiveLayoutTests(unittest.TestCase):
    def test_active_extended_tree_is_absent(self):
        self.assertFalse((FABRIC / "extended").exists())

    def test_archived_add_on_assets_are_complete(self):
        expected = {
            STUDIO / "ValueLens - Fabric (+ Studio Agent Deepdive).pbit",
            STUDIO / "flows" / "Copilot_Consumption_Email_to_OneLake.json",
            STUDIO / "flows" / "Copilot_Consumption_SharePoint_to_OneLake.json",
            STUDIO / "notebooks" / "Copilot_Agent_Transcript_Parser.ipynb",
            STUDIO / "notebooks" / "Copilot_Credit_Consumption_Ingester.ipynb",
            STUDIO / "notebooks" / "samples" / "smoketest_files_mode.py",
            STUDIO / "notebooks" / "samples" / "copilot_transcripts" / "conversationtranscripts.csv",
        }
        expected.update(ROOT / folder / name for folder in MIRRORS for name in SHARED_NAMES)
        actual = {p for p in EXTENDED.rglob("*") if p.is_file() and p.suffix.lower() != ".md"}
        self.assertEqual(actual, expected)

    def test_cost_flow_assets_are_archived_not_deleted(self):
        for name in COST_FILES:
            with self.subTest(name=name):
                self.assertTrue((FABRIC / "archive" / "flows" / name).is_file())
                self.assertFalse((FABRIC / "flows" / name).exists())

    def test_product_feedback_flow_remains_active(self):
        self.assertTrue((FABRIC / "flows" / "Copilot_ProductFeedback_Email_to_OneLake.json").is_file())

    def test_archived_smoke_paths_resolve_without_runtime_dependencies(self):
        script = STUDIO / "notebooks" / "samples" / "smoketest_files_mode.py"
        tree = ast.parse(script.read_text(encoding="utf-8-sig"))
        assignments = [
            node for node in tree.body
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in {"NB_PATH", "SAMPLE"}
                for target in node.targets
            )
        ]
        self.assertEqual(len(assignments), 2)
        namespace = {"Path": Path, "__file__": str(script)}
        exec(compile(ast.Module(body=assignments, type_ignores=[]), str(script), "exec"), namespace)
        self.assertEqual(namespace["NB_PATH"], STUDIO / "notebooks" / "Copilot_Agent_Transcript_Parser.ipynb")
        self.assertEqual(namespace["SAMPLE"], script.parent / "copilot_transcripts" / "conversationtranscripts.csv")
        self.assertTrue(namespace["NB_PATH"].is_file())
        self.assertTrue(namespace["SAMPLE"].is_file())

    def test_workflow_checks_both_archived_mirrors_on_push_and_pull_request(self):
        workflow = (ROOT / ".github" / "workflows" / "sync-shared.yml").read_text(encoding="utf-8")
        push, pull_request = workflow.split("  push:\n", 1)[1].split("  pull_request:\n", 1)
        pull_request = pull_request.split("\njobs:", 1)[0]
        for block in (push, pull_request):
            for pattern in (
                "3. Fabric/pipelines/**",
                "3. Fabric/notebooks/**",
                "3. Fabric/archive/extended/**/notebooks/_core/**",
                "3. Fabric/archive/extended/_shared/notebooks/**",
                "3. Fabric/archive/flows/**",
                "3. Fabric/*.pbit",
                "tests/**",
                "scripts/sync-shared.ps1",
                ".github/workflows/sync-shared.yml",
            ):
                self.assertIn(f"      - '{pattern}'", block)
            self.assertNotIn("'3. Fabric/extended/", block)
        self.assertIn("sync-shared.ps1 -Check", workflow)
        self.assertIn("python -B -m unittest discover -s tests -v", workflow)


class ArchiveSyncTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(shutil.which("pwsh"), "PowerShell 7 is required for sync regression checks")
        self.directory = tempfile.TemporaryDirectory(prefix="archive-sync-", dir=ROOT / "tests")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "scripts").mkdir()
        shutil.copyfile(ROOT / "scripts" / "sync-shared.ps1", self.root / "scripts" / "sync-shared.ps1")
        self.source = self.root / "3. Fabric" / "notebooks"
        self.source.mkdir(parents=True)
        for name in SHARED_NAMES | {PROCESSOR}:
            (self.source / name).write_bytes((FABRIC / "notebooks" / name).read_bytes())

    def run_sync(self, check=False):
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(self.root / "scripts" / "sync-shared.ps1")]
            + (["-Check"] if check else []),
            cwd=self.root, capture_output=True, text=True, timeout=60,
        )
        self.assertFalse((self.root / "3. Fabric" / "extended").exists())
        return result

    def assert_synced(self):
        for folder in MIRRORS:
            destination = self.root / folder
            self.assertEqual({p.name for p in destination.iterdir()}, SHARED_NAMES)
            for name in SHARED_NAMES:
                self.assertEqual((destination / name).read_bytes(), (self.source / name).read_bytes())
            self.assertFalse((destination / PROCESSOR).exists())

    def test_missing_archive_check_is_read_only_and_write_creates_only_archive(self):
        result = self.run_sync(check=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("MISSING DIR:"), 2)
        self.assertFalse((self.root / "3. Fabric" / "archive").exists())
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_synced()
        result = self.run_sync(check=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("8 notebook(s) x 2 destinations", result.stdout)

    def test_drift_in_either_archive_is_detected_without_writes_and_repaired(self):
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        name = "ValueLens_Data_Check.ipynb"
        for folder in MIRRORS:
            with self.subTest(folder=folder):
                target = self.root / folder / name
                target.write_bytes(b"drift")
                result = self.run_sync(check=True)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("DRIFT:", result.stdout)
                self.assertEqual(target.read_bytes(), b"drift")
                result = self.run_sync()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assert_synced()
                target.unlink()
                result = self.run_sync(check=True)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertFalse(target.exists())
                result = self.run_sync()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assert_synced()


if __name__ == "__main__":
    unittest.main()
