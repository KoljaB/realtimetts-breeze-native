from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import finalize_wheel


def test_repair_finalize_refreshes_worker_and_record_hashes(tmp_path: Path):
    wheel = tmp_path / "demo-py3-none-manylinux_2_35_x86_64.whl"
    info_name = "realtimetts_breeze_native/bin/build-info.json"
    worker_name = "realtimetts_breeze_native/bin/breeze-server"
    dependency_name = "realtimetts_breeze_native/bin/libvulkan-bundled.so"
    record_name = "demo-0.1.dist-info/RECORD"
    info = {
        "format": 1,
        "native_binary": {"name": "breeze-server", "sha256": "stale"},
        "native_dependencies": [],
    }
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(worker_name, b"repaired-elf")
        archive.writestr(dependency_name, b"bundled-loader")
        archive.writestr(info_name, json.dumps(info).encode())
        archive.writestr(record_name, b"old\n")

    finalize_wheel.finalize(wheel)

    with zipfile.ZipFile(wheel) as archive:
        updated = json.loads(archive.read(info_name))
        assert updated["native_binary"]["sha256"] == hashlib.sha256(
            b"repaired-elf"
        ).hexdigest()
        rows = list(csv.reader(io.StringIO(archive.read(record_name).decode())))
    worker_row = next(row for row in rows if row[0] == worker_name)
    expected = "sha256=" + __import__("base64").urlsafe_b64encode(
        hashlib.sha256(b"repaired-elf").digest()
    ).rstrip(b"=").decode()
    assert worker_row[1] == expected
    assert worker_row[2] == str(len(b"repaired-elf"))
    assert updated["native_dependencies"] == [{
        "name": "libvulkan-bundled.so",
        "sha256": hashlib.sha256(b"bundled-loader").hexdigest(),
    }]
    dependency_row = next(row for row in rows if row[0] == dependency_name)
    assert dependency_row[1] == "sha256=" + __import__("base64").urlsafe_b64encode(
        hashlib.sha256(b"bundled-loader").digest()
    ).rstrip(b"=").decode()
    assert dependency_row[2] == str(len(b"bundled-loader"))
    assert next(row for row in rows if row[0] == record_name)[1:] == ["", ""]
