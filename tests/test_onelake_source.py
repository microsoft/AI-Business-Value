"""Guard the single Service-discoverable source and lossless template packaging."""
import importlib.util
import hashlib
import json
import re
import unittest
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "onelake_packager", ROOT / "scripts" / "Update-OneLake-Template.py"
)
PACKAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGER)

GLOSSARY = "\U0001f4d6 Metric Glossary"
HEADERS = (
    ("Page", "STRING"), ("PageDescription", "STRING"),
    ("Metric", "STRING"), ("Description", "STRING"),
    ("PageOrder", "INTEGER"), ("MetricOrder", "INTEGER"),
)
DAX_TOKEN = re.compile(
    r'(?P<skip>\s+|//[^\n]*|--[^\n]*|/\*.*?\*/)'
    r'|(?P<string>"(?:[^"]|"")*")|(?P<integer>[+-]?[0-9]+)'
    r'|(?P<identifier>[A-Za-z_][A-Za-z_0-9]*)|(?P<punctuation>[(){},;])',
    re.DOTALL,
)


def glossary_rows(expression):
    """Parse the literal glossary DATATABLE, never splitting inside DAX strings."""
    text = "\n".join(expression) if isinstance(expression, list) else expression
    tokens = []
    offset = 0
    while offset < len(text):
        match = DAX_TOKEN.match(text, offset)
        if match is None:
            raise ValueError(f"Unsupported DAX at character {offset}")
        kind, value = match.lastgroup, match.group()
        if kind == "string":
            value = value[1:-1].replace('""', '"')
        elif kind == "integer":
            value = int(value)
        elif kind == "identifier":
            value = value.upper()
        if kind != "skip":
            tokens.append((kind, value))
        offset = match.end()
    stream = iter(tokens)

    def take(kind, value=None):
        token = next(stream, None)
        if token is None or token[0] != kind or (value is not None and token[1] != value):
            raise ValueError(f"Expected {kind} {value!r}, got {token!r}")
        return token[1]

    def punctuation(value):
        take("punctuation", value)

    take("identifier", "DATATABLE")
    punctuation("(")
    for name, dtype in HEADERS:
        take("string", name)
        punctuation(",")
        take("identifier", dtype)
        punctuation(",")
    punctuation("{")
    rows = []
    while True:
        punctuation("{")
        row = []
        for column in range(6):
            if column:
                punctuation(",")
            row.append(take("string" if column < 4 else "integer"))
        punctuation("}")
        rows.append(row)
        separator = take("punctuation")
        if separator == "}":
            break
        if separator != ",":
            raise ValueError("Expected row separator")
    punctuation(")")
    remaining = list(stream)
    if remaining not in ([], [("punctuation", ";")]):
        raise ValueError("Unexpected code after DATATABLE")
    return rows


def sort_groups(rows, label_column, order_column):
    groups = defaultdict(set)
    for row in rows:
        groups[row[label_column].casefold()].add(row[order_column])
    return groups


def content_hash(value):
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


class OneLakeSourceTests(unittest.TestCase):
    def test_source_is_bound_once_outside_table_function(self):
        source = PACKAGER.SOURCE.read_text(encoding="utf-8")
        self.assertEqual(source.count("AzureStorage.DataLake("), 1)
        self.assertLess(source.index("AzureStorage.DataLake("), source.index("ReadTable ="))
        prefix = source[:source.index("ReadTable =")]
        self.assertNotIn("Text.Trim(", prefix)
        self.assertNotIn("Text.Lower(", prefix)
        self.assertNotIn("tableName", prefix)
        self.assertIn('& "/Tables"', prefix)
        self.assertIn("DeltaLake.Table(Directory)", source)

    def test_navigation_rejects_missing_and_ambiguous_matches(self):
        source = PACKAGER.SOURCE.read_text(encoding="utf-8")
        self.assertIn("Table.Combine({Direct} & Nested)", source)
        self.assertIn("if Count = 1 then Matches{0}[Content]", source)
        self.assertIn('Error.Record("OneLake.TableNotFound"', source)
        self.assertIn('Error.Record("OneLake.AmbiguousTable"', source)
        self.assertNotIn("otherwise null", source)

    def test_packager_is_idempotent_and_rejects_unrelated_changes(self):
        original = PACKAGER.TEMPLATE.read_bytes()
        rebuilt, changed = PACKAGER.build_template(original, PACKAGER.SOURCE.read_bytes())
        self.assertEqual(changed, [])
        self.assertEqual(original, rebuilt)
        PACKAGER.validate_rebuild(original, rebuilt)
        _, payloads, _ = PACKAGER.read_archive(original)
        document = json.loads(payloads["DataModelSchema"].decode("utf-16-le"))
        altered = json.loads(payloads["DataModelSchema"].decode("utf-16-le"))
        altered["model"]["tables"][0]["name"] = "Unexpected change"
        self.assertNotEqual(
            PACKAGER.unrelated_hash(document, "DataModelSchema"),
            PACKAGER.unrelated_hash(altered, "DataModelSchema"),
        )

    def test_packaged_glossary_has_global_sort_dependencies(self):
        with zipfile.ZipFile(PACKAGER.TEMPLATE) as archive:
            document = json.loads(archive.read("DataModelSchema").decode("utf-16-le"))
        tables = [table for table in document["model"]["tables"] if table["name"] == GLOSSARY]
        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertEqual(len(table["partitions"]), 1)
        source = table["partitions"][0]["source"]
        self.assertEqual(source["type"], "calculated")
        rows = glossary_rows(source["expression"])
        self.assertEqual(len(rows), 113)
        columns = {column["name"]: column for column in table["columns"]}
        self.assertEqual(set(columns), {name for name, _ in HEADERS})
        for label, order, label_index, order_index, count in (
            ("Metric", "MetricOrder", 2, 5, 100),
            ("Page", "PageOrder", 0, 4, 14),
        ):
            self.assertEqual(columns[label]["sortByColumn"], order)
            groups = sort_groups(rows, label_index, order_index)
            self.assertEqual(len(groups), count)
            self.assertEqual(
                {label: sorted(values) for label, values in groups.items() if len(values) != 1},
                {}, f"{label} must map to one {order} across all pages",
            )

    def test_packaged_glossary_preserves_content_and_original_minimum_orders(self):
        with zipfile.ZipFile(PACKAGER.TEMPLATE) as archive:
            document = json.loads(archive.read("DataModelSchema").decode("utf-16-le"))
        table = next(table for table in document["model"]["tables"] if table["name"] == GLOSSARY)
        rows = glossary_rows(table["partitions"][0]["source"]["expression"])
        # Baselines from the pre-repair package: all non-MetricOrder values in
        # row order, and the minimum original order for each casefolded label.
        self.assertEqual(content_hash([row[:5] for row in rows]),
                         "88e3326d862b8c4751306a49a43b1158040331ae5a5fc74d57db328285fb8e37")
        groups = sort_groups(rows, 2, 5)
        self.assertTrue(all(len(values) == 1 for values in groups.values()))
        self.assertEqual(content_hash(sorted((label, min(values)) for label, values in groups.items())),
                         "fa3083e16677380a02d5ec02968800e6543e9d597643b762aae016f2a29b4fb8")

    def test_glossary_parser_handles_escaped_strings_comments_and_case_variants(self):
        header = "DATATABLE(" + "".join(f'"{name}", {dtype},' for name, dtype in HEADERS)
        expression = header + '''
        { // punctuation in strings is not DAX structure
          {"Page A", "Line one
Line two", "AI Tasks", "A ""quote"", {brace}; // literal /* text */", +1, 108},
          /* a comment with "quotes", } and , */
          {"Page B", "", "ai tasks", "-- literal", -2, 201}
        }); -- trailing comment
        '''
        rows = glossary_rows(expression)
        self.assertEqual(rows[0], [
            "Page A", "Line one\nLine two", "AI Tasks",
            'A "quote", {brace}; // literal /* text */', 1, 108,
        ])
        self.assertEqual(rows[1], ["Page B", "", "ai tasks", "-- literal", -2, 201])
        self.assertEqual(sort_groups(rows, 2, 5), {"ai tasks": {108, 201}})
        for invalid in (expression + " EVALUATE", expression + " /* unclosed",
                        header + '{{"unterminated}', expression.replace("+1,", "1.5,")):
            with self.subTest(invalid=invalid[-40:]), self.assertRaises(ValueError):
                glossary_rows(invalid)


if __name__ == "__main__":
    unittest.main()
