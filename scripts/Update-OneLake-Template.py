"""Repack only the authoritative OneLake PBIT's two FabricTable query copies."""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "3. Fabric" / "ValueLens - Fabric OneLake.pbit"
SOURCE = ROOT / "scripts" / "onelake" / "FabricTable.pq"
PARTS = {
    "DataModelSchema": (("model", "expressions"), "expression"),
    "UnappliedChanges": (("queries",), "text"),
}
ZIP_METADATA = (
    "filename", "orig_filename", "date_time", "compress_type", "comment", "extra",
    "create_system", "create_version", "extract_version", "reserved", "flag_bits",
    "volume", "internal_attr", "external_attr",
)


def helper_record(document, member):
    route, field = PARTS[member]
    records = document
    for key in route:
        records = records[key]
    matches = [record for record in records if record.get("name") == "FabricTable"]
    if len(matches) != 1:
        raise ValueError(f"{member}: expected exactly one FabricTable, found {len(matches)}")
    if not isinstance(matches[0].get(field), list):
        raise ValueError(f"{member}: expected the existing line-array query representation")
    return matches[0], field


def unrelated_document(document, member):
    result = copy.deepcopy(document)
    record, field = helper_record(result, member)
    record[field] = "<FabricTable>"
    return result


def unrelated_hash(document, member):
    normalized = json.dumps(
        unrelated_document(document, member),
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def read_archive(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP members are not safe to update")
        if not set(PARTS).issubset(names):
            raise ValueError("Missing DataModelSchema or UnappliedChanges")
        payloads = {info.filename: archive.read(info) for info in infos}
        return infos, payloads, archive.comment


def validate_rebuild(original, rebuilt):
    before_info, before, before_comment = read_archive(original)
    after_info, after, after_comment = read_archive(rebuilt)
    if list(before) != list(after) or before_comment != after_comment:
        raise ValueError("ZIP members, order or archive comment changed")
    for old, new in zip(before_info, after_info):
        if any(getattr(old, key) != getattr(new, key) for key in ZIP_METADATA):
            raise ValueError(f"ZIP metadata changed: {old.filename}")
        member = old.filename
        if member not in PARTS:
            if before[member] != after[member]:
                raise ValueError(f"Unrelated ZIP member changed: {member}")
            continue
        old_doc = json.loads(before[member].decode("utf-16-le"))
        new_doc = json.loads(after[member].decode("utf-16-le"))
        if unrelated_document(old_doc, member) != unrelated_document(new_doc, member):
            raise ValueError(f"Unrelated model fields changed: {member}")


def build_template(original, canonical):
    # PBIT JSON stores M as line arrays. Preserve every line, including the
    # final empty line; CRLF/LF encoding is not an M logic transformation.
    lines = canonical.decode("utf-8").replace("\r\n", "\n").split("\n")
    if not lines or lines == [""]:
        raise ValueError("The canonical FabricTable helper is empty")
    infos, payloads, comment = read_archive(original)
    changed = []
    for member in PARTS:
        document = json.loads(payloads[member].decode("utf-16-le"))
        record, field = helper_record(document, member)
        if record[field] == lines:
            continue
        record[field] = lines
        payloads[member] = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-16-le")
        changed.append(member)
    if not changed:
        return original, changed
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.comment = comment
        for info in infos:
            archive.writestr(copy.copy(info), payloads[info.filename])
    rebuilt = output.getvalue()
    validate_rebuild(original, rebuilt)
    return rebuilt, changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check both query copies without writing")
    args = parser.parse_args(argv)
    original = TEMPLATE.read_bytes()
    rebuilt, changed = build_template(original, SOURCE.read_bytes())
    if args.check and changed:
        print("OneLake template is stale: " + ", ".join(changed), file=sys.stderr)
        return 1
    if changed:
        if TEMPLATE.read_bytes() != original:
            raise ValueError("Template changed during rebuild; refusing to overwrite")
        TEMPLATE.write_bytes(rebuilt)
        if TEMPLATE.read_bytes() != rebuilt:
            raise ValueError("Written template does not match the validated in-memory ZIP")
    _, payloads, _ = read_archive(rebuilt)
    print("OneLake template: " + ("updated " + ", ".join(changed) if changed else "current"))
    print(f"Preserved {len(payloads) - len(PARTS)} unrelated ZIP member payloads and ZIP metadata")
    print("PBIT SHA256: " + hashlib.sha256(rebuilt).hexdigest())
    for member in PARTS:
        document = json.loads(payloads[member].decode("utf-16-le"))
        print(f"{member} SHA256: {hashlib.sha256(payloads[member]).hexdigest()}")
        print(f"{member} unrelated-fields SHA256: {unrelated_hash(document, member)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(f"OneLake update failed: {error}", file=sys.stderr)
        sys.exit(1)
