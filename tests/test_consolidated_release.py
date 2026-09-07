"""Guard model-fix preservation and the notebook distribution that blocked PR 37."""
import hashlib
import json
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "3. Fabric" / "notebooks"
MIRRORS = (
    ROOT / "3. Fabric" / "extended" / "_shared" / "notebooks",
    ROOT / "3. Fabric" / "extended" / "Fabric + Copilot Studio" / "notebooks" / "_core",
)

# Full model and pending-query bytes from the published schema-resilience PR.
SCHEMA_HASHES = {
    "ValueLens - Fabric.pbit": {
        "DataModelSchema": "54d6b739e72d9ec61a7c1dd23872cf868012020dabc24ed7340a5564101455aa",
        "UnappliedChanges": "77ac91786bb9cdc370bbb6c427fd86418bcd392a62ded03fdc4004f0e972f0fb",
    },
    "ValueLens - Fabric OneLake.pbit": {
        "DataModelSchema": "ace897778f0608f1551b0f017dc35c54baf0ec76ca338746d9ff16151ed3e8e0",
        "UnappliedChanges": "10cfb56a879907d25a6aaf67c29017e88f7c3b6a9c912c79abd8fb10c820895a",
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
        for name, expected in SCHEMA_HASHES.items():
            with zipfile.ZipFile(ROOT / "3. Fabric" / name) as archive:
                for member, sha in expected.items():
                    self.assertEqual(hashlib.sha256(archive.read(member)).hexdigest(), sha, (name, member))

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
