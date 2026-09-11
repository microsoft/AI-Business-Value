"""Guard model-fix preservation and the notebook distribution that blocked PR 37."""
import hashlib
import importlib.util
import json
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "3. Fabric" / "notebooks"
MIRRORS = (
    ROOT / "3. Fabric" / "archive" / "extended" / "_shared" / "notebooks",
    ROOT / "3. Fabric" / "archive" / "extended" / "Fabric + Copilot Studio" / "notebooks" / "_core",
)

# SQL bytes remain pinned; OneLake pins the reviewed glossary correction while
# checking the helper separately against its canonical source.
SCHEMA_HASHES = {
    "ValueLens - Fabric.pbit": {
        "DataModelSchema": "54d6b739e72d9ec61a7c1dd23872cf868012020dabc24ed7340a5564101455aa",
        "UnappliedChanges": "77ac91786bb9cdc370bbb6c427fd86418bcd392a62ded03fdc4004f0e972f0fb",
    },
    "ValueLens - Fabric OneLake.pbit": {
        "DataModelSchema": "58160bccbc84bec95477bbd5d086649a5e1bc32b2e8b8e135e0c3f8e45e2ef29",
        "UnappliedChanges": "c17c69d874ed2924d9f26a884867d04892b79823552cd95936dcc3f94e46cd0e",
    },
}


class ConsolidatedReleaseTests(unittest.TestCase):
    def test_exactly_two_core_transport_templates(self):
        self.assertEqual(
            {path.name for path in (ROOT / "3. Fabric").glob("*.pbit")},
            set(SCHEMA_HASHES),
        )
        self.assertFalse((ROOT / "3. Fabric" / "ValueLens - Fabric (OneLake).pbit").exists())

    def test_previous_schema_fixes_preserved_without_model_rewrite(self):
        spec = importlib.util.spec_from_file_location(
            "onelake_packager", ROOT / "scripts" / "Update-OneLake-Template.py"
        )
        packager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(packager)
        for name, expected in SCHEMA_HASHES.items():
            with zipfile.ZipFile(ROOT / "3. Fabric" / name) as archive:
                for member, sha in expected.items():
                    payload = archive.read(member)
                    if "OneLake" in name:
                        document = json.loads(payload.decode("utf-16-le"))
                        actual = packager.unrelated_hash(document, member)
                        record, field = packager.helper_record(document, member)
                        canonical = packager.SOURCE.read_text(encoding="utf-8").split("\n")
                        self.assertEqual(record[field], canonical, (name, member))
                    else:
                        actual = hashlib.sha256(payload).hexdigest()
                    self.assertEqual(actual, sha, (name, member))

    def test_all_shared_notebooks_match_canonical_bytes(self):
        sources = [p for p in CORE.glob("*.ipynb") if p.name != "Copilot_Audit_Log_Processor.ipynb"]
        self.assertEqual(len(sources), 8)
        for source in sources:
            for folder in MIRRORS:
                self.assertTrue((folder / source.name).is_file(), (folder, source.name))
                self.assertEqual(source.read_bytes(), (folder / source.name).read_bytes(), (folder, source.name))

    def test_consolidated_notebook_cells_compile(self):
        for name in (
            "Copilot_Agent365_Lander.ipynb",
            "Copilot_Agent365_Registry_Ingester.ipynb",
            "Copilot_Licensed_Users_Direct_Ingester.ipynb",
            "ValueLens_Data_Check.ipynb",
        ):
            notebook = json.loads((CORE / name).read_text(encoding="utf-8"))
            self.assertEqual(notebook["nbformat"], 4)
            for index, cell in enumerate(notebook["cells"]):
                if cell["cell_type"] != "code":
                    continue
                code = cell["source"]
                code = "".join(code) if isinstance(code, list) else code
                compile(code, f"{name}:cell{index}", "exec")
                self.assertFalse(any(o.get("output_type") == "error" for o in cell.get("outputs", [])),
                                 (name, index))


if __name__ == "__main__":
    unittest.main()
