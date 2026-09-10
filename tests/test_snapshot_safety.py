"""Offline regression tests for notebook snapshot-safety helpers."""
import ast
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "3. Fabric" / "notebooks"


def notebook(name):
    return json.loads((NOTEBOOKS / name).read_text(encoding="utf-8"))


def code_from_cell(name, index):
    return "".join(notebook(name)["cells"][index]["source"])


def extract(name, index, *, functions=(), assigns=(), import_names=None):
    tree = ast.parse(code_from_cell(name, index))
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if import_names is None:
                selected.append(node)
                continue
            names = {
                alias.asname or alias.name.split(".")[0]
                for alias in node.names
            }
            if names & set(import_names):
                selected.append(node)
        elif isinstance(node, ast.Assign):
            targets = {
                target.id
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            if targets & set(assigns):
                selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in set(functions):
            selected.append(node)
    namespace = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), f"{name}:cell{index}", "exec"), namespace)
    return namespace


class SnapshotSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = None
        cls.spark_error = None
        if importlib.util.find_spec("pyspark"):
            from pyspark.sql import SparkSession

            try:
                cls.spark = (
                    SparkSession.builder.master("local[1]")
                    .appName("snapshot-safety-tests")
                    .getOrCreate()
                )
            except Exception as exc:  # pragma: no cover - environment-specific
                cls.spark_error = exc

    @classmethod
    def tearDownClass(cls):
        if cls.spark is not None:
            cls.spark.stop()

    def test_licensed_report_rejects_malformed_rows_and_conflicting_duplicates(self):
        ns = extract(
            "Copilot_Licensed_Users_Direct_Ingester.ipynb",
            6,
            functions=(
                "_normalise_header",
                "_pick_report_column",
                "_normalise_identity",
                "_parse_active_user_report",
                "_validate_report_rows",
            ),
            import_names=("csv", "StringIO"),
        )
        with self.assertRaisesRegex(ValueError, "row 2 has 1 columns; expected 2"):
            ns["_parse_active_user_report"](
                "User Principal Name,Assigned Products\nuser@example.com\n"
            )
        _, rows, upn_col, _ = ns["_parse_active_user_report"](
            "User Principal Name,Assigned Products\n"
            "User@Example.com,Microsoft 365 E7\n"
            " user@example.com ,Microsoft 365 Copilot\n"
        )
        with self.assertRaisesRegex(ValueError, "Duplicate licensed-user row conflict"):
            ns["_validate_report_rows"](rows, upn_col)

    def test_org_helpers_reject_malformed_pages_conflicts_and_cycles(self):
        page = extract(
            "Copilot_Org_Data_Direct_Ingester.ipynb",
            6,
            functions=("_validate_users_page",),
        )
        with self.assertRaisesRegex(ValueError, "missing required 'value'"):
            page["_validate_users_page"]({"@odata.nextLink": "x"}, 1)
        with self.assertRaisesRegex(ValueError, "invalid '@odata.nextLink'"):
            page["_validate_users_page"]({"value": [], "@odata.nextLink": 123}, 1)

        rows_ns = extract(
            "Copilot_Org_Data_Direct_Ingester.ipynb",
            8,
            functions=("_normalise_identity", "_canonical_org_row", "_dedupe_org_rows"),
        )
        rows = [
            rows_ns["_canonical_org_row"](
                {"userPrincipalName": "A@example.com", "displayName": "Alice", "department": "HR"}
            ),
            rows_ns["_canonical_org_row"](
                {"userPrincipalName": " a@example.com ", "displayName": "Alicia", "department": "HR"}
            ),
        ]
        with self.assertRaisesRegex(ValueError, "Conflicting org rows"):
            rows_ns["_dedupe_org_rows"](rows)

        hier = extract(
            "Copilot_Org_Data_Direct_Ingester.ipynb",
            10,
            functions=("build_hierarchy",),
            assigns=("MAX_ORG_LEVELS", "HIER_FIXED", "HIER_LEVELS", "HIER_COLUMNS"),
        )
        with self.assertRaisesRegex(ValueError, "Cycle detected"):
            hier["build_hierarchy"](
                [
                    {"PersonId": "a@example.com", "displayName": "A", "managerUPN": "b@example.com"},
                    {"PersonId": "b@example.com", "displayName": "B", "managerUPN": "a@example.com"},
                ]
            )

    def test_registry_helpers_reject_malformed_pages_details_and_duplicate_keys(self):
        page = extract(
            "Copilot_Agent365_Registry_Ingester.ipynb",
            4,
            functions=("_validate_catalog_page",),
            import_names=(),
        )
        with self.assertRaisesRegex(ValueError, "missing required 'value'"):
            page["_validate_catalog_page"]({"@odata.nextLink": "x"}, 1)

        shape = extract(
            "Copilot_Agent365_Registry_Ingester.ipynb",
            6,
            functions=("_normalise_registry_key", "_elements", "_dedupe_registry_rows"),
            import_names=("_json",),
        )
        with self.assertRaisesRegex(ValueError, "Invalid elementDetails JSON"):
            shape["_elements"](
                {"elementDetails": [{"elementType": "command", "elements": [{"definition": "{"}]}]}
            )
        with self.assertRaisesRegex(ValueError, "Conflicting Agent 365 rows"):
            shape["_dedupe_registry_rows"](
                [
                    {"Title ID": "T_1", "Agent name": "Agent A"},
                    {"Title ID": " t_1 ", "Agent name": "Agent B"},
                ]
            )

    def test_feedback_snapshot_helpers_preserve_existing_and_reject_unsafe_append(self):
        ns = extract(
            "Copilot_ProductFeedback_Ingester.ipynb",
            8,
            functions=("_assert_feedback_write_mode", "_decide_missing_feedback_action"),
            import_names=(),
        )
        ns.update({
            "REPORT_GLOB": "*feedback*",
            "SOURCE_DIR": "Files/product_feedback",
            "TARGET_TABLE": "dbo.user_feedback",
        })
        with self.assertRaisesRegex(ValueError, "WRITE_MODE='append' is not supported"):
            ns["_assert_feedback_write_mode"]("append")
        decision = ns["_decide_missing_feedback_action"](
            matches=[],
            table_exists=True,
            strict=False,
            allow_empty_first_snapshot=False,
        )
        self.assertEqual(decision["action"], "preserve")
        self.assertIn("Preserving existing", decision["message"])
        with self.assertRaisesRegex(ValueError, "ALLOW_EMPTY_FIRST_SNAPSHOT"):
            ns["_decide_missing_feedback_action"](
                matches=[],
                table_exists=False,
                strict=False,
                allow_empty_first_snapshot=False,
            )

    def test_feedback_has_no_superseded_writer_before_guarded_publication(self):
        # A second writer used to erase the table before the tested guard ran.
        cells = notebook("Copilot_ProductFeedback_Ingester.ipynb")["cells"]
        publishing_cells = []
        for index, cell in enumerate(cells):
            if cell["cell_type"] != "code":
                continue
            tree = ast.parse("".join(cell["source"]))
            if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr == "saveAsTable" for node in ast.walk(tree)):
                publishing_cells.append(index)
        self.assertEqual(publishing_cells, [8])

    def test_agent365_lander_alias_plan_is_comprehensive_and_rejects_ambiguity(self):
        ns = extract(
            "Copilot_Agent365_Lander.ipynb",
            2,
            functions=("_norm", "_build_alias_plan", "_build_header_groups", "_resolve_alias_targets"),
            import_names=("re",),
        )
        canonical, plan = ns["_build_alias_plan"]()
        self.assertEqual(set(canonical), set(plan))
        resolved = ns["_resolve_alias_targets"](
            ["name", "title_id", "publisher", "deployed_to", "total_runtime"],
            plan,
            canonical,
        )
        self.assertEqual(resolved["Agent name"], "name")
        self.assertEqual(resolved["Title ID"], "title_id")
        self.assertEqual(resolved["Publisher"], "publisher")
        self.assertEqual(resolved["Deployment"], "deployed_to")
        self.assertEqual(resolved["Run Time"], "total_runtime")
        with self.assertRaisesRegex(ValueError, "Ambiguous source headers"):
            ns["_resolve_alias_targets"](["Title ID", "title_id"], plan, canonical)

    def test_agent365_lander_duplicate_equivalence_is_behavioral(self):
        if self.spark is None:
            self.skipTest(f"local Spark unavailable: {self.spark_error}")
        ns = extract(
            "Copilot_Agent365_Lander.ipynb",
            2,
            functions=("_columns_equivalent",),
            import_names=("F",),
        )
        df_same = self.spark.createDataFrame(
            [("T_1", "T_1"), ("T_2", "T_2")],
            ["Title ID", "title_id"],
        )
        df_diff = self.spark.createDataFrame(
            [("T_1", "P_1")],
            ["Title ID", "title_id"],
        )
        self.assertTrue(ns["_columns_equivalent"](df_same, ["Title ID", "title_id"]))
        self.assertFalse(ns["_columns_equivalent"](df_diff, ["Title ID", "title_id"]))

    def test_data_check_helpers_keep_full_totals_and_only_overlap_real_licensed_identities(self):
        ns = extract(
            "ValueLens_Data_Check.ipynb",
            3,
            functions=("_accepted_flag", "_summarize_flag_values", "_licensed_upns"),
            assigns=("ACCEPTED",),
            import_names=("Counter",),
        )
        values = [("TRUE" if i < 3 else f"other-{i}") for i in range(30)]
        summary = ns["_summarize_flag_values"](values)
        self.assertEqual(summary["counted"], 3)
        self.assertEqual(summary["total"], 30)
        self.assertEqual(len(summary["display_rows"]), 25)
        self.assertIsNone(ns["_licensed_upns"]([], "User Principal Name", None))
        self.assertEqual(
            ns["_licensed_upns"](
                [
                    {"User Principal Name": "a@example.com", "Has license": "TRUE"},
                    {"User Principal Name": " ", "Has license": "TRUE"},
                    {"User Principal Name": "b@example.com", "Has license": "FALSE"},
                    {"User Principal Name": "A@example.com", "Has license": "TRUE"},
                ],
                "User Principal Name",
                "Has license",
            ),
            {"a@example.com"},
        )


if __name__ == "__main__":
    unittest.main()
