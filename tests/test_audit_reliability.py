"""Behavioral notebook checks for audit ingestion reliability and merge safety."""

import ast
import json
import shutil
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "3. Fabric" / "notebooks"
INGESTER = NOTEBOOKS / "Copilot_Audit_Log_Direct_Ingester.ipynb"
PROCESSOR = NOTEBOOKS / "Copilot_Audit_Log_Processor.ipynb"
SCRATCH = Path(tempfile.gettempdir()) / ("valuelens-audit-tests-" + uuid.uuid4().hex)


def cells(path):
    return ["".join(cell["source"]) for cell in json.loads(path.read_text(encoding="utf-8"))["cells"]]


def exec_notebook_cell(path, index, namespace):
    source = cells(path)[index]
    exec(compile(source, f"{path.name}:cell{index}", "exec"), namespace)
    return namespace


def exec_named_defs(path, index, names, namespace=None, include_imports=True):
    tree = ast.parse(cells(path)[index], filename=f"{path.name}:cell{index}")
    body = []
    wanted = set(names)
    for node in tree.body:
        if include_imports and isinstance(node, (ast.Import, ast.ImportFrom)):
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted:
            body.append(node)
    compiled = compile(ast.Module(body=body, type_ignores=[]), f"{path.name}:cell{index}", "exec")
    ns = {} if namespace is None else namespace
    exec(compiled, ns)
    return ns


class FakeCatalog:
    def __init__(self, exists=False):
        self._exists = exists

    def tableExists(self, _name):
        return self._exists


class FakeSpark:
    def __init__(self, exists=False):
        self.catalog = FakeCatalog(exists=exists)

    def table(self, _name):
        raise AssertionError("table() should not be called in this unit test path")


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeNotebookUtilsFS:
    def __init__(self, root):
        self.root = Path(root)
        self.calls = []

    def _normalize(self, path):
        if not isinstance(path, str) or not path:
            raise AssertionError(f"unexpected path: {path!r}")
        return path.replace("\\", "/").rstrip("/")

    def _resolve(self, path):
        normalized = self._normalize(path)
        if normalized.startswith("file:"):
            return Path(normalized[5:])
        if normalized == "Files" or normalized.startswith("Files/"):
            relative = normalized[6:] if normalized.startswith("Files/") else ""
            return self.root / "Files" / Path(relative)
        if normalized.startswith("abfss://"):
            return self.root / "_abfss" / normalized.replace("://", "__", 1).replace("/", "_")
        raise AssertionError(f"unexpected notebookutils path: {path!r}")

    def exists(self, path):
        self.calls.append(("exists", path))
        return self._resolve(path).exists()

    def mkdirs(self, path):
        self.calls.append(("mkdirs", path))
        self._resolve(path).mkdir(parents=True, exist_ok=True)
        return True

    def ls(self, path):
        self.calls.append(("ls", path))
        base = self._resolve(path)
        if not base.exists():
            return []
        prefix = self._normalize(path)
        return [type("Entry", (), {"path": prefix + "/" + child.name})() for child in sorted(base.iterdir())]

    def rm(self, path, recurse=False):
        self.calls.append(("rm", path, recurse))
        target = self._resolve(path)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        return True

    def cp(self, src, dst):
        self.calls.append(("cp", src, dst))
        source = self._resolve(src)
        target = self._resolve(dst)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return True

    def mv(self, src, dst, create_path=False, overwrite=False):
        self.calls.append(("mv", src, dst, overwrite))
        source = self._resolve(src)
        target = self._resolve(dst)
        target.parent.mkdir(parents=True, exist_ok=True)
        if overwrite and target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        shutil.move(str(source), str(target))
        return True

    def head(self, *_args, **_kwargs):
        raise AssertionError("head() should not be used for manifest reads")


class AuditReliabilityTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.ingester_cell16 = cells(INGESTER)[16]
        cls.processor_cell15 = cells(PROCESSOR)[15]

    def setUp(self):
        shutil.rmtree(SCRATCH, ignore_errors=True)
        SCRATCH.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def ingester_helpers(self):
        namespace = {
            "MODE": "incremental",
            "BACKFILL_DAYS": 180,
            "LOOKBACK_DAYS": 7,
            "CHUNK_HOURS": 8,
            "OUTPUT_TABLE": "dbo.Copilot_Interactions_Parsed",
            "spark": FakeSpark(exists=False),
            "_request": lambda *a, **k: None,
            "get_headers": lambda: {},
        }
        return exec_notebook_cell(INGESTER, 6, namespace)

    def stage_helpers(self):
        return exec_named_defs(
            INGESTER,
            10,
            {
                "_normalize_stage_dir",
                "_is_remote_stage_dir",
                "_stage_path_join",
                "_stage_basename",
                "_list_stage_paths",
                "_stage_exists",
                "_stage_remove",
                "_get_notebook_fs",
                "_ensure_stage_dir",
                "list_window_files",
                "purge_window_files",
                "list_active_stage_files",
                "manifest_succeeded",
                "should_refresh_window",
                "window_stage_files_reusable",
                "is_window_reusable",
            },
            {"_as_utc_datetime": self.ingester_helpers()["_as_utc_datetime"]},
        )

    def row_builder(self):
        return exec_named_defs(INGESTER, 10, {"_row"}, self.ingester_helpers())

    def processor_helpers(self):
        return exec_named_defs(
            PROCESSOR,
            2,
            {"normalize_actor_token", "classify_actor_environment", "resolve_write_strategy"},
            include_imports=False,
        )

    def query_helpers(self, namespace=None):
        ns = {
            "MAX_WAIT_MIN_PER_QUERY": 1,
            "POLL_INTERVAL_SEC": 0,
            "_request": lambda *a, **k: None,
            "get_headers": lambda: {},
        }
        if namespace:
            ns.update(namespace)
        return exec_named_defs(INGESTER, 8, {"_read_query_status", "wait_for_query"}, ns)

    def checkpoint_helpers(self, namespace=None):
        ingester = self.ingester_helpers()
        ns = {
            "STAGING_ABS": str(SCRATCH),
            "MANIFEST": str(SCRATCH / "_manifest.json"),
            "LOCAL_STAGE_TMP_DIR": str(SCRATCH),
            "MANIFEST_LOCK": threading.RLock(),
            "manifest": {},
            "LOOKBACK_DAYS": 7,
            "end_date": datetime(2026, 9, 10, tzinfo=timezone.utc),
            "datetime": datetime,
            "timedelta": timedelta,
            "timezone": timezone,
            "stable_window_key": ingester["stable_window_key"],
            "_as_utc_datetime": ingester["_as_utc_datetime"],
            "canonicalize_audit_record": ingester["canonicalize_audit_record"],
            "create_query": lambda ws, we: "qid-1",
            "wait_for_query": lambda qid: {"status": "succeeded", "id": qid},
            "_request": lambda *a, **k: None,
            "get_headers": lambda: {},
        }
        if namespace:
            ns.update(namespace)
        return exec_named_defs(
            INGESTER,
            10,
            {
                "_normalize_stage_dir",
                "_is_remote_stage_dir",
                "_stage_path_join",
                "_stage_basename",
                "_file_uri",
                "_driver_temp_root",
                "_new_local_temp_path",
                "_get_notebook_fs",
                "_ensure_stage_dir",
                "_list_stage_paths",
                "_stage_exists",
                "_stage_remove",
                "_write_stage_text",
                "_write_stage_jsonl",
                "_move_stage_file",
                "_read_stage_json",
                "list_window_files",
                "purge_window_files",
                "list_active_stage_files",
                "_allowed_manifest_statuses",
                "_validate_manifest_payload",
                "_load_manifest",
                "_manifest_temp_path",
                "_save_manifest",
                "manifest_succeeded",
                "should_refresh_window",
                "window_stage_files_reusable",
                "is_window_reusable",
                "_read_manifest_entry",
                "_mark_window",
                "_row",
                "_is_graph_records_url",
                "_validate_graph_records_url",
                "_validate_records_page",
                "_drain",
                "_process",
            },
            ns,
        )

    def remote_checkpoint_helpers(self, namespace=None):
        remote_root = SCRATCH / "_remote"
        fake_fs = FakeNotebookUtilsFS(remote_root)
        ns = {
            "STAGING_ABS": "Files/_audit_staging",
            "MANIFEST": "Files/_audit_staging/_manifest.json",
            "LOCAL_STAGE_TMP_DIR": str(SCRATCH / "_driver_tmp"),
            "NOTEBOOK_FS": fake_fs,
        }
        if namespace:
            ns.update(namespace)
        helpers = self.checkpoint_helpers(ns)
        helpers["_fake_fs"] = fake_fs
        helpers["_remote_root"] = remote_root
        return helpers

    def test_incremental_start_uses_trailing_overlap_but_still_catches_up_from_stale_watermark(self):
        ns = self.ingester_helpers()
        end_dt = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)
        self.assertEqual(
            ns["determine_incremental_start"](end_dt, end_dt - timedelta(days=2), 7),
            end_dt - timedelta(days=7),
        )
        self.assertEqual(
            ns["determine_incremental_start"](end_dt, end_dt - timedelta(days=30), 7),
            end_dt - timedelta(days=30),
        )

    def test_manifest_updates_preserve_memory_when_mounted_reads_are_stale(self):
        # Lakehouse mount reads can lag a successful atomic rename. A worker must
        # not replace newer process-local checkpoints with that older snapshot.
        ns = self.checkpoint_helpers()
        ns["manifest"]["completed-window"] = {"status": "succeeded"}
        ns["_load_manifest"] = lambda: {}
        ns["_mark_window"]("next-window", "waiting")
        self.assertEqual(ns["_read_manifest_entry"]("completed-window")["status"], "succeeded")
        persisted = json.loads(Path(ns["MANIFEST"]).read_text(encoding="utf-8"))
        self.assertEqual(persisted["completed-window"]["status"], "succeeded")

    def test_synthetic_record_key_uses_canonical_json_and_ignores_array_order(self):
        ns = self.ingester_helpers()
        left = json.dumps(
            {
                "CopilotEventData": {
                    "Messages": [
                        {"isPrompt": "true", "Id": "msg-b"},
                        {"Id": "msg-a", "isPrompt": "true"},
                    ],
                    "AccessedResources": [
                        {"Type": "docx", "Action": "read", "SiteUrl": "https://b"},
                        {"SiteUrl": "https://a", "Action": "read", "Type": "docx"},
                    ],
                }
            }
        )
        right = json.dumps(
            {
                "CopilotEventData": {
                    "AccessedResources": [
                        {"Action": "read", "SiteUrl": "https://a", "Type": "docx"},
                        {"SiteUrl": "https://b", "Type": "docx", "Action": "read"},
                    ],
                    "Messages": [
                        {"Id": "msg-a", "isPrompt": "true"},
                        {"isPrompt": "true", "Id": "msg-b"},
                    ],
                }
            }
        )

        self.assertEqual(
            ns["build_source_record_key"](None, "2026-09-10T08:00:00Z", "View", left),
            ns["build_source_record_key"](None, "2026-09-10T08:00:00Z", "View", right),
        )

    def test_stage_row_builder_uses_canonical_identity_and_preserves_real_ids(self):
        row = self.row_builder()["_row"]
        record_a = {
            "id": "record-1",
            "createdDateTime": "2026-09-10T08:00:00Z",
            "auditLogRecordType": "copilotInteraction",
            "operation": "View",
            "associatedAdminUnits": [],
            "associatedAdminUnitsNames": [],
            "auditData": {
                "CreationTime": "2026-09-10T08:00:00Z",
                "CopilotEventData": {
                    "Messages": [
                        {"Id": "msg-b", "isPrompt": "true"},
                        {"isPrompt": "true", "Id": "msg-a"},
                    ],
                    "AccessedResources": [
                        {"Type": "docx", "Action": "read", "SiteUrl": "https://b"},
                        {"Action": "read", "SiteUrl": "https://a", "Type": "docx"},
                    ],
                },
            },
        }
        record_b = {
            **record_a,
            "auditData": {
                "CopilotEventData": {
                    "AccessedResources": [
                        {"SiteUrl": "https://a", "Type": "docx", "Action": "read"},
                        {"Type": "docx", "Action": "read", "SiteUrl": "https://b"},
                    ],
                    "Messages": [
                        {"Id": "msg-a", "isPrompt": "true"},
                        {"isPrompt": "true", "Id": "msg-b"},
                    ],
                },
                "CreationTime": "2026-09-10T08:00:00Z",
            },
        }

        row_a = row(record_a)
        row_b = row(record_b)
        audit = json.loads(row_a["AuditData"])

        self.assertEqual(row_a["SourceRecordKey"], "rid:record-1")
        self.assertEqual(row_a["SourceRecordKey"], row_b["SourceRecordKey"])
        self.assertEqual(row_a["AuditData"], row_b["AuditData"])
        self.assertEqual(
            [message["_StableKey"] for message in audit["CopilotEventData"]["Messages"]],
            ["mid:msg-a", "mid:msg-b"],
        )
        self.assertEqual(
            [resource["_StableOrdinal"] for resource in audit["CopilotEventData"]["AccessedResources"]],
            [0, 1],
        )

    def test_missing_message_ids_use_content_fingerprint_plus_occurrence_not_position(self):
        ns = self.ingester_helpers()
        payload_a = ns["canonicalize_audit_payload"](
            {
                "CopilotEventData": {
                    "Messages": [
                        {"isPrompt": "true", "Text": "Alpha"},
                        {"Text": "Beta", "isPrompt": "true"},
                        {"Text": "Alpha", "isPrompt": "true"},
                    ]
                }
            }
        )
        payload_b = ns["canonicalize_audit_payload"](
            {
                "CopilotEventData": {
                    "Messages": [
                        {"Text": "Alpha", "isPrompt": "true"},
                        {"isPrompt": "true", "Text": "Alpha"},
                        {"isPrompt": "true", "Text": "Beta"},
                    ]
                }
            }
        )

        keys_a = [message["_StableKey"] for message in payload_a["CopilotEventData"]["Messages"]]
        keys_b = [message["_StableKey"] for message in payload_b["CopilotEventData"]["Messages"]]
        self.assertEqual(keys_a, keys_b)
        self.assertEqual(len(keys_a), 3)
        self.assertEqual(len(set(keys_a)), 3)
        self.assertTrue(any(key.endswith("#2") for key in keys_a))

    def test_repeated_resources_keep_distinct_stable_keys_after_canonical_sort(self):
        ns = self.ingester_helpers()
        payload_a = ns["canonicalize_audit_payload"](
            {
                "CopilotEventData": {
                    "AccessedResources": [
                        {"Type": "docx", "Action": "read", "SiteUrl": "https://b"},
                        {"Type": "docx", "Action": "read", "SiteUrl": "https://a"},
                        {"Action": "read", "SiteUrl": "https://a", "Type": "docx"},
                    ]
                }
            }
        )
        payload_b = ns["canonicalize_audit_payload"](
            {
                "CopilotEventData": {
                    "AccessedResources": [
                        {"Action": "read", "SiteUrl": "https://a", "Type": "docx"},
                        {"Type": "docx", "Action": "read", "SiteUrl": "https://b"},
                        {"SiteUrl": "https://a", "Type": "docx", "Action": "read"},
                    ]
                }
            }
        )

        keys_a = [resource["_StableKey"] for resource in payload_a["CopilotEventData"]["AccessedResources"]]
        keys_b = [resource["_StableKey"] for resource in payload_b["CopilotEventData"]["AccessedResources"]]
        self.assertEqual(keys_a, keys_b)
        self.assertEqual(len(keys_a), 3)
        self.assertEqual(len(set(keys_a)), 3)
        self.assertTrue(any(key.endswith("#2") for key in keys_a))

    def test_legacy_incremental_table_without_new_keys_fails_clearly(self):
        ns = self.ingester_helpers()
        with self.assertRaisesRegex(RuntimeError, "missing stable key columns"):
            ns["validate_incremental_target_columns"](
                ["CreationDate", "RecordId", "Message_Id"],
                ns["KEY_COLUMNS"],
                "dbo.Copilot_Interactions_Parsed",
            )

    def test_stage_scope_reuses_recent_windows_only_and_cleans_partial_files(self):
        helpers = self.stage_helpers()
        recent_key = "v2_recent"
        old_key = "v2_old"
        recent = SCRATCH / f"win_{recent_key}_0000.jsonl"
        old = SCRATCH / f"win_{old_key}_0000.jsonl"
        partial = SCRATCH / f"win_{recent_key}_0001.jsonl.partial"
        recent.write_text("{}", encoding="utf-8")
        old.write_text("{}", encoding="utf-8")
        partial.write_text("{}", encoding="utf-8")

        scoped = [Path(p).name for p in helpers["list_active_stage_files"](str(SCRATCH), {recent_key})]
        self.assertEqual(scoped, [recent.name])
        removed = helpers["purge_window_files"](str(SCRATCH), recent_key, include_partial=True)
        self.assertEqual(removed, 2)
        self.assertFalse(recent.exists())
        self.assertFalse(partial.exists())
        self.assertTrue(old.exists())

    def test_remote_stage_publication_uses_notebookutils_without_mount_paths(self):
        ingester = self.ingester_helpers()
        win = (
            datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc),
        )
        key = ingester["stable_window_key"](*win)
        start_url = "https://graph.microsoft.com/beta/security/auditLog/queries/qid-remote/records?$top=999"
        payload = {
            "value": [
                {
                    "id": "record-1",
                    "createdDateTime": "2026-09-10T08:00:00Z",
                    "auditLogRecordType": "copilotInteraction",
                    "operation": "View",
                    "associatedAdminUnits": [],
                    "associatedAdminUnitsNames": [],
                    "auditData": {"CreationTime": "2026-09-10T08:00:00Z"},
                }
            ]
        }
        helpers = self.remote_checkpoint_helpers(
            {
                "create_query": lambda ws, we: "qid-remote",
                "wait_for_query": lambda qid: {"status": "succeeded", "id": qid},
                "_request": lambda method, url, **kwargs: FakeResponse(payload if url == start_url else {"value": []}),
            }
        )

        self.assertEqual(helpers["_process"](win), (key, 1, "done"))
        self.assertEqual(
            helpers["list_window_files"](helpers["STAGING_ABS"], key),
            [f"Files/_audit_staging/win_{key}_0000.jsonl"],
        )
        manifest = helpers["_load_manifest"]()
        self.assertEqual(manifest[key]["status"], "succeeded")
        self.assertEqual(manifest[key]["files"], [f"win_{key}_0000.jsonl"])
        self.assertFalse((helpers["_remote_root"] / "Files" / "_audit_staging" / f"win_{key}_0000.jsonl.partial").exists())
        self.assertTrue(all("/lakehouse/default" not in str(call) for call in helpers["_fake_fs"].calls))

    def test_failed_remote_delete_cannot_publish_stale_pages_as_empty_success(self):
        win = (
            datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc),
        )
        key = self.ingester_helpers()["stable_window_key"](*win)
        helpers = self.remote_checkpoint_helpers({
            "create_query": lambda ws, we: "qid-empty",
            "wait_for_query": lambda qid: {"status": "succeeded", "id": qid},
            "_request": lambda *args, **kwargs: FakeResponse({"value": []}),
        })
        fs = helpers["_fake_fs"]
        stale_path = f"Files/_audit_staging/win_{key}_0000.jsonl"
        stale = fs._resolve(stale_path)
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text('{"id":"stale"}\n', encoding="utf-8")
        original_rm = fs.rm
        fs.rm = lambda path, recurse=False: False if path == stale_path else original_rm(path, recurse)

        with self.assertRaisesRegex(RuntimeError, "Failed to remove staged file"):
            helpers["_process"](win)
        self.assertTrue(stale.exists())
        self.assertEqual(helpers["_load_manifest"]()[key]["status"], "failed")
        self.assertIn("Failed to remove staged file", helpers["_load_manifest"]()[key]["error"])

    def test_remote_copy_and_move_false_results_are_fatal(self):
        for operation in ("cp", "mv"):
            with self.subTest(operation=operation):
                helpers = self.remote_checkpoint_helpers()
                setattr(helpers["_fake_fs"], operation, lambda *args: False)
                with self.assertRaisesRegex(RuntimeError, "Failed to (copy|move)"):
                    helpers["_mark_window"]("failed-publish", "succeeded", rows=0)
                self.assertNotIn("failed-publish", helpers["manifest"])
                self.assertEqual(helpers["_load_manifest"](), {})

    def test_missing_published_files_force_refresh_instead_of_stale_skip(self):
        helpers = self.stage_helpers()
        cutoff = datetime(2026, 9, 3, tzinfo=timezone.utc)
        old_end = datetime(2026, 8, 15, tzinfo=timezone.utc)
        entry = {"status": "succeeded", "rows": 3, "pages": 1, "files": ["win_v2_old_0000.jsonl"]}

        self.assertFalse(helpers["window_stage_files_reusable"](str(SCRATCH), "v2_old", entry))
        self.assertFalse(helpers["is_window_reusable"](str(SCRATCH), "v2_old", old_end, entry, cutoff))

    def test_recent_completed_windows_requery_for_late_arrivals_but_old_completed_windows_skip(self):
        helpers = self.stage_helpers()
        cutoff = datetime(2026, 9, 3, tzinfo=timezone.utc)
        recent_end = datetime(2026, 9, 9, tzinfo=timezone.utc)
        old_end = datetime(2026, 8, 15, tzinfo=timezone.utc)
        succeeded = {"status": "succeeded", "completed_at": "2026-09-01T00:00:00+00:00"}

        self.assertTrue(helpers["should_refresh_window"](recent_end, succeeded, cutoff))
        self.assertFalse(helpers["should_refresh_window"](old_end, succeeded, cutoff))
        self.assertTrue(helpers["should_refresh_window"](old_end, {"status": "failed"}, cutoff))

    def test_processor_merge_strategy_is_explicit_and_never_silent_overwrite_on_missing_id(self):
        helpers = self.processor_helpers()
        self.assertEqual(
            helpers["resolve_write_strategy"]("overwrite", ["CreationDate"], True, [], ["Id"]),
            "overwrite",
        )
        self.assertEqual(
            helpers["resolve_write_strategy"]("merge", ["Id"], False, [], ["Id"]),
            "overwrite",
        )
        with self.assertRaisesRegex(RuntimeError, "requires source key columns"):
            helpers["resolve_write_strategy"]("merge", ["CreationDate"], True, ["Id"], ["Id"])
        with self.assertRaisesRegex(RuntimeError, "requires non-blank values"):
            helpers["resolve_write_strategy"]("merge", ["Id"], True, ["Id"], ["Id"], source_key_health=False)
        with self.assertRaisesRegex(RuntimeError, "missing merge key columns"):
            helpers["resolve_write_strategy"]("merge", ["Id"], True, ["CreationDate"], ["Id"])

    def test_processor_actor_environment_restores_agent_and_cowork_paths(self):
        helpers = self.processor_helpers()
        self.assertEqual(helpers["classify_actor_environment"](app_host="autonomous"), "Agents")
        self.assertEqual(helpers["classify_actor_environment"](app_host="m365 cowork canvas"), "Cowork")
        self.assertEqual(
            helpers["classify_actor_environment"](agent_name="Sales Copilot Agent", environment="Licensed"),
            "Agents",
        )
        self.assertEqual(helpers["classify_actor_environment"](app_host="word", environment="Licensed"), "User")

    def test_notebooks_share_stable_id_contract(self):
        for token in ["'Id'", "'Source_RecordKey'", "'Source_MessageKey'", "'Source_ResourceKey'"]:
            self.assertIn(token, self.ingester_cell16)
        self.assertIn("MERGE_KEYS       = [\"Id\"]", cells(PROCESSOR)[1])
        self.assertIn("resolve_write_strategy", self.processor_cell15)
        self.assertIn("canonicalize_audit_record", cells(INGESTER)[10])
        self.assertIn("SourceRecordKey", cells(INGESTER)[12])
        self.assertIn("ArrayType", cells(INGESTER)[12])
        self.assertIn("msg._StableKey", self.ingester_cell16)
        self.assertIn("res._StableKey", self.ingester_cell16)
        self.assertIn("ambiguous synthetic SourceRecordKey", self.ingester_cell16)
        self.assertIn("dropDuplicates(['Id'])", self.ingester_cell16)

    def test_wait_for_query_distinguishes_success_failure_and_malformed_status(self):
        responses = iter(
            [
                FakeResponse({"status": "running"}),
                FakeResponse({"status": "succeeded", "id": "qid-success"}),
            ]
        )
        helpers = self.query_helpers({"_request": lambda *a, **k: next(responses)})
        payload = helpers["wait_for_query"]("qid-success", max_wait_min=1)
        self.assertEqual(payload["status"], "succeeded")

        helpers = self.query_helpers({"_request": lambda *a, **k: FakeResponse({"status": "failed"})})
        with self.assertRaisesRegex(RuntimeError, "ended with status: failed"):
            helpers["wait_for_query"]("qid-failed", max_wait_min=1)

        helpers = self.query_helpers({"_request": lambda *a, **k: FakeResponse({})})
        with self.assertRaisesRegex(RuntimeError, "missing/invalid status"):
            helpers["wait_for_query"]("qid-malformed", max_wait_min=1)

    def test_manifest_load_allows_absent_but_rejects_corrupt_shape_and_status(self):
        helpers = self.checkpoint_helpers()
        manifest_path = Path(helpers["MANIFEST"])

        self.assertEqual(helpers["_load_manifest"](), {})

        manifest_path.write_text("{bad json", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "not valid JSON"):
            helpers["_load_manifest"]()

        manifest_path.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "must be a JSON object"):
            helpers["_load_manifest"]()

        manifest_path.write_text(json.dumps({"win_bad": {"status": "done"}}), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "invalid status"):
            helpers["_load_manifest"]()

    def test_threaded_checkpoint_updates_persist_valid_json(self):
        helpers = self.checkpoint_helpers()
        manifest_path = Path(helpers["MANIFEST"])

        def update(index):
            helpers["_mark_window"](
                f"v2_{index:03d}",
                "succeeded",
                rows=index,
                completed_at=f"2026-09-10T00:{index % 60:02d}:00+00:00",
            )

        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(update, range(100)))

        persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(len(persisted), 100)
        self.assertEqual(helpers["_load_manifest"](), persisted)
        self.assertTrue(all(entry["status"] == "succeeded" for entry in persisted.values()))
        self.assertFalse(list(SCRATCH.glob(".*.tmp")))

    def test_remote_manifest_roundtrip_avoids_truncated_head_reads(self):
        helpers = self.remote_checkpoint_helpers()

        for index in range(40):
            helpers["_mark_window"](
                f"v2_{index:03d}",
                "succeeded",
                rows=index,
                pages=index % 3,
                completed_at=f"2026-09-10T00:{index % 60:02d}:00+00:00",
            )

        manifest = helpers["_load_manifest"]()
        self.assertEqual(len(manifest), 40)
        self.assertEqual(manifest, helpers["manifest"])

    def test_drain_accepts_empty_page_but_rejects_malformed_payloads_and_off_graph_links(self):
        helpers = self.checkpoint_helpers({"_request": lambda *a, **k: FakeResponse({"value": []})})
        self.assertEqual(helpers["_drain"]("qid-empty", "empty"), (0, 0))
        self.assertEqual(helpers["list_window_files"](str(SCRATCH), "empty", include_partial=True), [])

        helpers = self.checkpoint_helpers({"_request": lambda *a, **k: FakeResponse({})})
        with self.assertRaisesRegex(RuntimeError, "missing value list"):
            helpers["_drain"]("qid-missing", "missing")

        helpers = self.checkpoint_helpers({"_request": lambda *a, **k: FakeResponse({"value": ["oops"]})})
        with self.assertRaisesRegex(RuntimeError, "item 0 must be an object"):
            helpers["_drain"]("qid-items", "items")

        helpers = self.checkpoint_helpers(
            {
                "_request": lambda *a, **k: FakeResponse(
                    {"value": [], "@odata.nextLink": "https://example.com/not-graph"}
                )
            }
        )
        with self.assertRaisesRegex(RuntimeError, "non-Graph records continuation URL"):
            helpers["_drain"]("qid-offgraph", "offgraph")

    def test_process_cleans_partial_files_and_marks_failed_on_wait_or_paging_errors(self):
        ingester = self.ingester_helpers()
        win = (
            datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc),
        )
        key = ingester["stable_window_key"](*win)

        helpers = self.checkpoint_helpers(
            {
                "create_query": lambda ws, we: "qid-failed",
                "wait_for_query": lambda qid: (_ for _ in ()).throw(
                    RuntimeError(f"Query {qid} ended with status: failed")
                ),
            }
        )
        with self.assertRaisesRegex(RuntimeError, "ended with status: failed"):
            helpers["_process"](win)
        failed_manifest = json.loads(Path(helpers["MANIFEST"]).read_text(encoding="utf-8"))
        self.assertEqual(failed_manifest[key]["status"], "failed")
        self.assertNotIn("succeeded", failed_manifest[key]["status"])
        self.assertEqual(helpers["list_window_files"](str(SCRATCH), key, include_partial=True), [])

        start_url = "https://graph.microsoft.com/beta/security/auditLog/queries/qid-cycle/records?$top=999"
        loop_url = "https://graph.microsoft.com/beta/security/auditLog/queries/qid-cycle/records?$skiptoken=abc"
        pages = {
            start_url: FakeResponse({"value": [{}], "@odata.nextLink": loop_url}),
            loop_url: FakeResponse({"value": [{}], "@odata.nextLink": start_url}),
        }
        helpers = self.checkpoint_helpers(
            {
                "create_query": lambda ws, we: "qid-cycle",
                "wait_for_query": lambda qid: {"status": "succeeded", "id": qid},
                "_request": lambda method, url, **kwargs: pages[url],
            }
        )
        with self.assertRaisesRegex(RuntimeError, "repeated pagination link cycle"):
            helpers["_process"](win)
        failed_manifest = json.loads(Path(helpers["MANIFEST"]).read_text(encoding="utf-8"))
        self.assertEqual(failed_manifest[key]["status"], "failed")
        self.assertIn("pagination link cycle", failed_manifest[key]["error"])
        self.assertEqual(helpers["list_window_files"](str(SCRATCH), key, include_partial=True), [])

    def test_remote_failures_cleanup_partial_pages_and_keep_manifest_authoritative(self):
        ingester = self.ingester_helpers()
        win = (
            datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc),
        )
        key = ingester["stable_window_key"](*win)
        start_url = "https://graph.microsoft.com/beta/security/auditLog/queries/qid-bad/records?$top=999"
        next_url = "https://graph.microsoft.com/beta/security/auditLog/queries/qid-bad/records?$skiptoken=1"
        pages = {
            start_url: FakeResponse(
                {
                    "value": [
                        {
                            "id": "record-1",
                            "createdDateTime": "2026-09-10T08:00:00Z",
                            "auditData": {"CreationTime": "2026-09-10T08:00:00Z"},
                        }
                    ],
                    "@odata.nextLink": next_url,
                }
            ),
            next_url: FakeResponse({}),
        }
        helpers = self.remote_checkpoint_helpers(
            {
                "create_query": lambda ws, we: "qid-bad",
                "wait_for_query": lambda qid: {"status": "succeeded", "id": qid},
                "_request": lambda method, url, **kwargs: pages[url],
            }
        )

        with self.assertRaisesRegex(RuntimeError, "missing value list"):
            helpers["_process"](win)
        manifest = helpers["_load_manifest"]()
        self.assertEqual(manifest[key]["status"], "failed")
        self.assertEqual(helpers["list_window_files"](helpers["STAGING_ABS"], key, include_partial=True), [])


if __name__ == "__main__":
    unittest.main()
