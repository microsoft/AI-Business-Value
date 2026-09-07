"""Portable structural release checks; Desktop refresh/rendering still need live QA."""
import json
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "3. Fabric"
FACT = "Chat + Agent Interactions (Audit Logs)"
VALUE_PAGE = "0a7ca92c179ad5909bba"
WORK_TYPE = ("3fb2cea77d7f969fdbd0", "8ce7b5c4bd0d04cce10d")


def literal(value):
    return {"expr": {"Literal": {"Value": value}}}


def comparison(visual):
    roles = visual.get("visual", {}).get("query", {}).get("queryState", {})
    for role in roles.values():
        for projection in role.get("projections", []):
            column = projection.get("field", {}).get("Column", {})
            if column == {"Expression": {"SourceRef": {"Entity": FACT}}, "Property": "Agent Filter"}:
                return True
    return False


class CoreTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archives = []
        for name in ("ValueLens - Fabric.pbit", "ValueLens - Fabric OneLake.pbit"):
            with zipfile.ZipFile(ROOT / name) as archive:
                if archive.testzip() is not None:
                    raise AssertionError(f"Corrupt archive: {name}")
                members = {n: archive.read(n) for n in archive.namelist()}
            docs = {n: json.loads(b) for n, b in members.items()
                    if n.startswith("Report/definition/") and n.endswith(".json")}
            cls.archives.append((name, members, docs))

    def test_transport_variants_share_identical_report(self):
        a, b = self.archives
        self.assertEqual({n: v for n, v in a[1].items() if n.startswith("Report/")},
                         {n: v for n, v in b[1].items() if n.startswith("Report/")})

    def test_no_populated_model_and_neutral_parameter_bindings(self):
        for name, members, _ in self.archives:
            self.assertNotIn("DataModel", members, name)
            model = json.loads(members["DataModelSchema"].decode("utf-16-le"))["model"]
            queries = json.loads(members["UnappliedChanges"].decode("utf-16-le"))["queries"]
            for expression in model.get("expressions", []):
                text = expression["expression"]
                text = "\n".join(text) if isinstance(text, list) else text
                if "IsParameterQuery" not in text:
                    continue
                query = next(q for q in queries if q["name"] == expression["name"])
                pending = query["text"]
                pending = "\n".join(pending) if isinstance(pending, list) else pending
                self.assertEqual(text.split(" meta ")[0].strip(), "null")
                self.assertEqual(pending.split(" meta ")[0].strip(), "null")
                self.assertEqual(query["lineageTag"], expression["lineageTag"])

    def test_one_comparison_per_page_with_consistent_title(self):
        for _, _, docs in self.archives:
            pages = [d["name"] for n, d in docs.items() if n.endswith("/page.json")]
            self.assertEqual(len(pages), 13)
            for page in pages:
                controls = [d for n, d in docs.items() if f"/pages/{page}/visuals/" in n and comparison(d)]
                self.assertEqual(len(controls), 1, page)
                title = controls[0]["visual"]["visualContainerObjects"]["title"]
                self.assertTrue(any(t["properties"].get("text") == literal("'Cowork vs Agent'") for t in title))

    def test_slicer_title_sizes(self):
        for _, _, docs in self.archives:
            for name, doc in docs.items():
                visual = doc.get("visual", {})
                if "slicer" not in visual.get("visualType", "").lower():
                    continue
                for title in visual["visualContainerObjects"]["title"]:
                    self.assertEqual(title["properties"]["fontSize"], literal("'8'"), name)
                for header in visual.get("objects", {}).get("header", []):
                    self.assertEqual(header["properties"]["textSize"], literal("8D"), name)

    def test_bookmarks_explicitly_exclude_comparison_controls(self):
        for _, _, docs in self.archives:
            all_ids = {d["name"] for n, d in docs.items() if n.endswith("/visual.json")}
            ids = {d["name"] for n, d in docs.items() if n.endswith("/visual.json") and comparison(d)}
            for name, bookmark in docs.items():
                if not name.endswith(".bookmark.json"):
                    continue
                options = bookmark.get("options", {})
                self.assertIs(options.get("applyOnlyToTargetVisuals"), True, name)
                targets = set(options.get("targetVisualNames", []))
                self.assertFalse(ids & targets)
                self.assertTrue(targets <= all_ids)
                for section in bookmark.get("explorationState", {}).get("sections", {}).values():
                    self.assertFalse(ids.intersection(section.get("visualContainers", {})))

    def test_value_table_and_time_saved_work_type_visibility(self):
        for _, _, docs in self.archives:
            for name, bookmark in docs.items():
                if not name.endswith(".bookmark.json") or bookmark.get("displayName") not in ("Time Saved", "Value Table"):
                    continue
                section = bookmark["explorationState"]["sections"].get(VALUE_PAGE)
                if section is None:
                    continue
                for visual in WORK_TYPE:
                    display = section["visualContainers"][visual]["singleVisual"].get("display")
                    self.assertEqual(display, {"mode": "hidden"} if bookmark["displayName"] == "Value Table" else None)
                    self.assertIn(visual, bookmark["options"]["targetVisualNames"])

    def test_field_parameter_spans(self):
        for _, _, docs in self.archives:
            for name, doc in docs.items():
                for role in doc.get("visual", {}).get("query", {}).get("queryState", {}).values():
                    count = len(role.get("projections", []))
                    for parameter in role.get("fieldParameters", []):
                        self.assertGreaterEqual(parameter["index"], 0, name)
                        self.assertGreaterEqual(parameter["length"], 0, name)
                        self.assertLessEqual(parameter["index"] + parameter["length"], count, name)


if __name__ == "__main__":
    unittest.main()
