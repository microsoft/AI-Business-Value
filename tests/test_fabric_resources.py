"""Focused checks for Fabric docs/resources added in this change."""

import json
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FABRIC = ROOT / "3. Fabric"
CHECKER = FABRIC / "docs" / "checker"
ARCHITECTURE = FABRIC / "ValueLens_Fabric_Architecture.excalidraw"

REQUIRED_NODE_IDS = {
    "graph_audit",
    "audit_ingester",
    "parsed_delta",
    "audit_processor",
    "curated_delta",
    "power_bi_import",
    "licence_source_ingester",
    "licence_snapshot",
    "org_source_ingester",
    "org_snapshot",
    "registry_source_ingester",
    "agents_365",
    "feedback_source_ingester",
    "user_feedback",
}

REQUIRED_EDGES = {
    ("graph_audit", "audit_ingester"),
    ("audit_ingester", "parsed_delta"),
    ("parsed_delta", "audit_processor"),
    ("audit_processor", "curated_delta"),
    ("curated_delta", "power_bi_import"),
    ("licence_source_ingester", "licence_snapshot"),
    ("licence_snapshot", "audit_processor"),
    ("licence_snapshot", "power_bi_import"),
    ("org_source_ingester", "org_snapshot"),
    ("org_snapshot", "power_bi_import"),
    ("registry_source_ingester", "agents_365"),
    ("agents_365", "audit_processor"),
    ("agents_365", "power_bi_import"),
    ("feedback_source_ingester", "user_feedback"),
    ("user_feedback", "power_bi_import"),
}

FORBIDDEN_EDGES = {
    ("parsed_delta", "power_bi_import"),
    ("org_source_ingester", "audit_processor"),
    ("org_snapshot", "audit_processor"),
    ("licence_source_ingester", "parsed_delta"),
}


class FabricResourceTests(unittest.TestCase):
    def _load_architecture_elements(self):
        scene = json.loads(ARCHITECTURE.read_text(encoding="utf-8"))
        return [element for element in scene["elements"] if not element.get("isDeleted")]

    def _bound_edges(self):
        edges = {}
        for element in self._load_architecture_elements():
            if element.get("type") != "arrow":
                continue
            start = (element.get("startBinding") or {}).get("elementId")
            end = (element.get("endBinding") or {}).get("elementId")
            self.assertIsNotNone(start, f"{element['id']} missing startBinding.elementId")
            self.assertIsNotNone(end, f"{element['id']} missing endBinding.elementId")
            edges[element["id"]] = (start, end)
        return edges

    def test_architecture_assets_exist(self):
        for name in [
            "ValueLens_Fabric_Architecture.excalidraw",
            "ValueLens_Fabric_Architecture.svg",
            "ValueLens_Fabric_Architecture.png",
        ]:
            self.assertTrue((FABRIC / name).exists(), name)

    def test_architecture_uses_semantic_node_ids(self):
        node_ids = {
            element["id"]
            for element in self._load_architecture_elements()
            if element.get("type") == "rectangle"
        }
        self.assertTrue(REQUIRED_NODE_IDS.issubset(node_ids), REQUIRED_NODE_IDS - node_ids)

    def test_architecture_required_edges_are_bound(self):
        actual_edges = set(self._bound_edges().values())
        self.assertTrue(REQUIRED_EDGES.issubset(actual_edges), REQUIRED_EDGES - actual_edges)

    def test_architecture_forbidden_edges_are_absent(self):
        actual_edges = set(self._bound_edges().values())
        self.assertTrue(FORBIDDEN_EDGES.isdisjoint(actual_edges), FORBIDDEN_EDGES & actual_edges)

    def test_checker_assets_exist(self):
        for name in [
            "ValueLens-Fabric-Quick-TSQL-Checks.sql",
            "ValueLens-Fabric-Quick-TSQL-Checks.docx",
        ]:
            self.assertTrue((CHECKER / name).exists(), name)

    def test_checker_sql_contains_reviewed_queries(self):
        sql_text = (CHECKER / "ValueLens-Fabric-Quick-TSQL-Checks.sql").read_text(encoding="utf-8")
        self.assertIn("COUNT_BIG(*)", sql_text)
        self.assertIn("distinct_prompt_messages", sql_text)
        self.assertIn("ThreadId", sql_text)
        self.assertIn("Derives Monday weeks from CreationDate", sql_text)
        self.assertIn("NOT a Spark SQL notebook", sql_text)

    def test_checker_docx_contains_expected_text(self):
        docx_path = CHECKER / "ValueLens-Fabric-Quick-TSQL-Checks.docx"
        with zipfile.ZipFile(docx_path) as archive:
            document = archive.read("word/document.xml").decode("utf-8")
        for expected in [
            "ValueLens Fabric | Quick SQL checks",
            "Lakehouse SQL analytics endpoint",
            "COUNT_BIG",
            "Current licensed-user snapshot",
        ]:
            self.assertIn(expected, document)

    def test_fabric_readme_references_checker_and_import_mode(self):
        readme = (FABRIC / "README.md").read_text(encoding="utf-8")
        self.assertIn("Both are **Import**, not Direct Lake.", readme)
        self.assertIn("Files/product_feedback/", readme)
        self.assertIn("Checker pack (read-only T-SQL)", readme)


if __name__ == "__main__":
    unittest.main()
