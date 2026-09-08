"""Execute the distributed notebook classifier offline; never authenticate or write Delta."""
import ast
import contextlib
import functools
import io
import json
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "3. Fabric" / "notebooks"
NOTEBOOK = "Copilot_Licensed_Users_Direct_Ingester.ipynb"
COPIES = (
    CORE / NOTEBOOK,
    ROOT / "3. Fabric" / "extended" / "_shared" / "notebooks" / NOTEBOOK,
    ROOT / "3. Fabric" / "extended" / "Fabric + Copilot Studio" / "notebooks" / "_core" / NOTEBOOK,
)
E7 = (
    "Microsoft 365 E7",
    "MICROSOFT_365_E7",
    "9a18296a-025f-4e37-9ffa-30bf8d1ce775",
)
ALIASES = ("Microsoft 365 Copilot", "Copilot for Microsoft 365", "M365 Copilot")


def cells(path):
    return ["".join(c["source"]) for c in json.loads(path.read_text(encoding="utf-8"))["cells"]]


def classify(products, overrides=None, path=COPIES[0]):
    code = cells(path)
    namespace = {}
    exec(compile(code[2], f"{path}:config", "exec"), namespace)
    namespace.update(overrides or {})
    namespace["rows"] = [{"Assigned Products": value} for value in products]
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(code[8], f"{path}:classifier", "exec"), namespace)
    return namespace, output.getvalue()


class LicenseClassificationTests(unittest.TestCase):
    def assert_flags(self, products, expected, overrides=None, path=COPIES[0]):
        namespace, output = classify(products, overrides, path)
        self.assertEqual([row["HasCopilot"] == "TRUE" for row in namespace["rows"]], expected)
        return namespace, output

    def test_verified_e7_names_and_identifiers_in_every_distributed_copy(self):
        products = list(E7) + [" \t microsoft   365 \u00a0 e7 \n", E7[1].lower(), E7[2].upper()]
        for path in COPIES:
            with self.subTest(path=path):
                self.assert_flags(products, [True] * len(products), path=path)

    def test_existing_copilot_aliases_remain_supported(self):
        products = list(ALIASES) + [s.lower() for s in ALIASES] + ["  MICROSOFT   365 COPILOT  "]
        self.assert_flags(products, [True] * len(products))

    def test_non_entitled_and_unverified_products_rejected(self):
        products = [
            "Microsoft 365 E3", "Microsoft 365 E5", "Office 365 E5", "E7", "SPE_E7",
            "Microsoft 365 E70", "Microsoft 365 E7 trial", "Microsoft 365 E7 Developer",
            "Not Microsoft 365 E7", "Microsoft 365 E7 Add-on", "MICROSOFT_365_E7_TEST",
            "Microsoft 365 E7 (no Teams)", "Microsoft 365 E7 EEA (no Teams)",
            E7[2] + "-other", "a62f8878-de10-42f3-b68f-6149a25ceb97",
            "Copilot Studio", "Microsoft 365 Copilot Studio", "Microsoft Security Copilot",
            "Microsoft 365 Copilot Chat", "Microsoft 365 Copilot Viral Trial",
            "Microsoft 365 Copilot Trial", "Copilot for Microsoft 365 Trial",
        ]
        self.assert_flags(products, [False] * len(products))

    def test_mixed_products_and_per_product_exclusions(self):
        products = [
            f"Microsoft 365 E5{sep}{seat}{sep}Microsoft 365 Copilot Viral Trial"
            for sep in ("+", ",", ";")
            for seat in (*E7, *ALIASES)
        ]
        self.assert_flags(products, [True] * len(products))
        self.assert_flags(
            ["Microsoft 365 E5+Microsoft 365 Copilot Viral Trial",
             "Microsoft 365 Copilot Studio;Microsoft 365 E3",
             "Microsoft 365 Copilot Trial,Microsoft 365 E7",
             "Microsoft 365 E7 Trial+Microsoft 365 Copilot"],
            [False, False, True, True],
        )

    def test_null_empty_and_delimiters(self):
        self.assert_flags([None, "", " \t\n ", "+,;", "Microsoft 365+Copilot"], [False] * 5)
        namespace, _ = classify([])
        self.assertEqual(namespace["copilot_count"], 0)

    def test_custom_patterns_replace_defaults_without_hidden_e7_union(self):
        overrides = {"COPILOT_SKU_PATTERNS": ["COPILOT FOR MICROSOFT 365"]}
        self.assert_flags([*E7, *ALIASES], [False, False, False, False, True, False], overrides)
        self.assert_flags([*E7, *ALIASES], [False] * 6, {"COPILOT_SKU_PATTERNS": []})
        self.assert_flags(["Microsoft 365 E7", "Microsoft 365 E70"], [True, False],
                          {"COPILOT_SKU_PATTERNS": ["= microsoft   365 e7 "]})
        self.assert_flags(["Some Custom Seat", "Microsoft 365 E7"], [True, False],
                          {"COPILOT_SKU_PATTERNS": ["CUSTOM SEAT", "", " "]})

    def test_custom_exclusions_apply_per_product_and_remain_intentional(self):
        self.assert_flags(
            ["Microsoft 365 E7", "Microsoft 365 E7+Microsoft 365 Copilot"],
            [False, True], {"COPILOT_SKU_EXCLUDE": [" e7 ", ""]},
        )
        self.assert_flags(["Microsoft 365 Copilot Viral Trial"], [True],
                          {"COPILOT_SKU_EXCLUDE": []})
        self.assert_flags(["Copilot Studio", "Microsoft 365 E7"], [True, False],
                          {"COPILOT_SKU_PATTERNS": ["COPILOT"], "COPILOT_SKU_EXCLUDE": []})

    def test_logs_use_same_classifier_as_written_flags(self):
        products = ["Microsoft 365 E7", "Microsoft 365 E70", "Microsoft 365 Copilot Viral Trial"]
        namespace, output = self.assert_flags(products, [True, False, False])
        self.assertEqual(namespace["_unmatched"], products[1:])
        self.assertEqual(namespace["matched_by"]["=MICROSOFT 365 E7"], 1)
        lines = output.splitlines()
        self.assertTrue(any("Microsoft 365 E7 " in line and "COUNTED" in line for line in lines))
        self.assertTrue(any("Microsoft 365 E70" in line and "NOT counted" in line for line in lines))
        self.assertTrue(any("Viral Trial" in line and "excluded" in line for line in lines))
        self.assertNotIn("count them all", output)

    def test_report_parsing_preserves_quoted_mixed_products_and_checks_header(self):
        code = cells(COPIES[0])[6]
        for text, valid in [
            ('\ufeffUser Principal Name,Assigned Products\nuser@example.com,"Microsoft 365 E5,Microsoft 365 E7"\n', True),
            ("User Principal Name,Other Column\nuser@example.com,value\n", False),
        ]:
            response = SimpleNamespace(text=text, raise_for_status=lambda: None)
            namespace = {"requests": SimpleNamespace(get=lambda *a, **k: response),
                         "REPORT_PERIOD": "D7", "headers": {}}
            with contextlib.redirect_stdout(io.StringIO()):
                if valid:
                    exec(compile(code, "report-fetch", "exec"), namespace)
                    self.assert_flags([namespace["rows"][0]["Assigned Products"]], [True])
                else:
                    with self.assertRaisesRegex(ValueError, "missing 'Assigned Products'"):
                        exec(compile(code, "report-fetch", "exec"), namespace)

    def test_active_pbits_consume_flags_not_assigned_product_classifiers(self):
        paths = [p for p in ROOT.rglob("*.pbit") if "archive" not in p.parts]
        self.assertEqual(len(paths), 5)
        for path in paths:
            with self.subTest(path=path), zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                model = json.loads(archive.read("DataModelSchema").decode("utf-16-le"))["model"]
                table = next(t for t in model["tables"] if t["name"] == "Copilot Licensed")
                expression = table["partitions"][0]["source"]["expression"]
                expression = "\n".join(expression) if isinstance(expression, list) else expression
                self.assertNotIn("Assigned Products", expression)
                self.assertNotIn("Assigned_Products", expression)
                self.assertIn('"Has license"', expression)
                if "3. Fabric" in path.parts:
                    self.assertIn('FabricTable("copilot_licensed_users")', expression)
                    self.assertIn('"Has_license"', expression)
                    self.assertIn('"HasCopilot"', expression)
                else:
                    self.assertIn('#"Org Data File"', expression)
                    self.assertIn("Csv.Document", expression)

    def test_supplied_flags_feed_optional_processor_without_sku_inference(self):
        path = ROOT / "1. Local CSV" / "scripts" / "Purview_CopilotInteraction_Processor_v4.0.0.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        nodes = [
            node for node in tree.body
            if (isinstance(node, ast.FunctionDef) and node.name == "compute_license_status")
            or (isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "_LICENSE_TRUTHY" for target in node.targets))
        ]
        namespace = {"functools": functools}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
        flags, _ = classify(["Microsoft 365 E7", "Microsoft 365 E5"])
        status = namespace["compute_license_status"]
        self.assertEqual([status(row["HasCopilot"]) for row in flags["rows"]],
                         ["M365 Copilot Licensed", "Unlicensed"])
        self.assertEqual(status("Microsoft 365 E7"), "Unlicensed")


if __name__ == "__main__":
    unittest.main()
