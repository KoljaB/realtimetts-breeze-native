"""Finalize a repaired native wheel and refresh provenance/RECORD hashes."""
from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path


def digest(data: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest())
    return "sha256=" + encoded.rstrip(b"=").decode("ascii")


def finalize(path: Path) -> Path:
    path = path.resolve()
    with zipfile.ZipFile(path, "r") as archive:
        entries = {info.filename: (info, archive.read(info.filename))
                   for info in archive.infolist()}
        comment = archive.comment
    info_names = [name for name in entries if name.endswith("/bin/build-info.json")]
    if len(info_names) != 1:
        raise ValueError("wheel must contain one packaged build-info.json")
    info_name = info_names[0]
    package_prefix = info_name[: -len("bin/build-info.json")]
    data = json.loads(entries[info_name][1].decode("utf-8"))
    worker_name = data["native_binary"]["name"]
    worker_name = package_prefix + "bin/" + worker_name
    if worker_name not in entries:
        raise ValueError(f"worker is absent from wheel: {worker_name}")
    data["native_binary"]["sha256"] = hashlib.sha256(
        entries[worker_name][1]
    ).hexdigest()
    dependencies = data.setdefault("native_dependencies", [])
    known_dependencies = {dependency["name"] for dependency in dependencies}
    bin_prefix = package_prefix + "bin/"
    for dependency in dependencies:
        name = bin_prefix + dependency["name"]
        if name not in entries:
            raise ValueError(f"native dependency is absent from wheel: {name}")
        dependency["sha256"] = hashlib.sha256(entries[name][1]).hexdigest()
    for name in sorted(entries):
        if not name.startswith(bin_prefix) or name in {info_name, worker_name}:
            continue
        dependency_name = name[len(bin_prefix):]
        if dependency_name and dependency_name not in known_dependencies:
            dependencies.append({
                "name": dependency_name,
                "sha256": hashlib.sha256(entries[name][1]).hexdigest(),
            })
            known_dependencies.add(dependency_name)
    entries[info_name] = (entries[info_name][0],
                          (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8"))

    record_names = [name for name in entries if name.endswith(".dist-info/RECORD")]
    if len(record_names) != 1:
        raise ValueError("wheel must contain one RECORD")
    record_name = record_names[0]
    entries.pop(record_name)
    records = []
    for name in sorted(entries):
        payload = entries[name][1]
        records.append((name, digest(payload), str(len(payload))))
    records.append((record_name, "", ""))
    import io
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(records)
    entries[record_name] = (zipfile.ZipInfo(record_name), output.getvalue().encode("utf-8"))

    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w") as archive:
        archive.comment = comment
        for name in sorted(entries):
            original, payload = entries[name]
            if name == record_name:
                archive.writestr(original, payload, compress_type=zipfile.ZIP_DEFLATED)
            else:
                archive.writestr(original, payload, compress_type=original.compress_type)
    os.replace(temporary, path)
    return path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: finalize_wheel.py WHEEL")
    print(finalize(Path(sys.argv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
