"""Dependency-free regression checks for read-only overlap diagnostics."""

import ast
import json
import unittest
from pathlib import Path


NOTEBOOK = (
    Path(__file__).resolve().parents[1]
    / "3. Fabric"
    / "notebooks"
    / "ValueLens_Data_Check.ipynb"
)


class DataCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cls.sources = ["".join(cell["source"]) for cell in notebook["cells"]]
        source = next(text for text in cls.sources if "def _overlap_diagnostic(" in text)
        definitions = [
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "_overlap_diagnostic"
        ]
        if len(definitions) != 1:
            raise AssertionError("Expected exactly one overlap diagnostic helper")
        namespace = {}
        exec(compile(ast.Module(body=definitions, type_ignores=[]), str(NOTEBOOK), "exec"), namespace)
        cls.diagnose = staticmethod(namespace["_overlap_diagnostic"])

    def assert_not_comparable(self, counts, expected):
        status, message = self.diagnose(*counts)
        self.assertEqual(status, "not_comparable")
        self.assertIn(expected, message)
        self.assertIn('"Active Licensed Users" will be zero', message)
        self.assertIn("cannot be assessed", message)
        self.assertNotIn("NO OVERLAP", message)
        self.assertNotIn("identity formats", message)
        self.assertNotIn("different tenants", message)

    def test_empty_audit_is_not_an_identity_mismatch(self):
        self.assert_not_comparable((5, 0, 0, 0), "NO AUDIT ROWS")

    def test_null_or_blank_audit_identifiers_are_not_an_identity_mismatch(self):
        self.assert_not_comparable((5, 0, 0, 8), "NO USABLE AUDIT USER IDENTIFIERS")

    def test_no_qualifying_licensed_users_is_not_an_identity_mismatch(self):
        self.assert_not_comparable((0, 5, 0, 8), "NO LICENSED USERS WITH USABLE UPNs")

    def test_both_sources_empty_reports_both_gaps(self):
        self.assert_not_comparable((0, 0, 0, 0), "NO AUDIT ROWS")
        self.assertIn("NO LICENSED USERS WITH USABLE UPNs", self.diagnose(0, 0, 0, 0)[1])

    def test_both_sources_without_usable_users_reports_both_gaps(self):
        self.assert_not_comparable((0, 0, 0, 8), "NO USABLE AUDIT USER IDENTIFIERS")
        self.assertIn("NO LICENSED USERS WITH USABLE UPNs", self.diagnose(0, 0, 0, 8)[1])

    def test_nonempty_disjoint_users_still_warn(self):
        status, message = self.diagnose(5, 5, 0, 8)
        self.assertEqual(status, "no_overlap")
        self.assertIn("NO OVERLAP", message)
        self.assertIn("possible causes, not a diagnosis", message)
        self.assertIn("audit users are licensed", message)

    def test_low_overlap_still_warns(self):
        status, message = self.diagnose(5, 5, 1, 8)
        self.assertEqual(status, "low_overlap")
        self.assertIn("low overlap", message)

    def test_overlap_threshold_and_matching_users_do_not_warn(self):
        for counts in ((4, 4, 2, 8), (5, 5, 5, 8), (10, 2, 2, 8)):
            with self.subTest(counts=counts):
                self.assertEqual(self.diagnose(*counts), ("overlap", ""))

    def test_notebook_uses_diagnostic_and_displays_only_comparable_samples(self):
        source = next(text for text in self.sources if "# === 4. OVERLAP CHECK" in text)
        tree = ast.parse(source)
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "_overlap_diagnostic"
        ]
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            [ast.unparse(arg) for arg in calls[0].args],
            ["nl", "na", "both", "adf.count()"],
        )
        self.assertIn("if status in ('no_overlap', 'low_overlap'):", source)
        self.assertIn("if message:\n            print(message)", source)

    def test_empty_audit_does_not_suggest_a_null_date_range(self):
        source = next(text for text in self.sources if "# === 2. AUDIT LOG COVERAGE" in text)
        self.assertIn("if n == 0:", source)
        self.assertIn("NO AUDIT ROWS - date coverage cannot be assessed.", source)
        self.assertIn("elif dcol:", source)
        self.assertIn("distinct usable users in audit data", source)
        self.assertIn("isNotNull() & (F.trim(F.col(f'`{ucol}`')) != '')", source)


if __name__ == "__main__":
    unittest.main()
