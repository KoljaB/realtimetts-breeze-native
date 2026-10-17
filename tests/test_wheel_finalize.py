from __future__ import annotations

import base64
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


def _zip_info(name: str, mode: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = mode << 16
    return info


def _record_digest(payload: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(
        hashlib.sha256(payload).digest()
    ).rstrip(b"=").decode()


def test_repair_finalize_refreshes_worker_and_record_hashes(tmp_path: Path):
    wheel = tmp_path / "demo-py3-none-manylinux_2_35_x86_64.whl"
    package_dir = "realtimetts_breeze_native/"
    bin_dir = package_dir + "bin/"
    info_name = bin_dir + "build-info.json"
    worker_name = bin_dir + "breeze-server"
    dependency_name = bin_dir + "libvulkan-bundled.so"
    dist_info_dir = "demo-0.1.dist-info/"
    record_name = dist_info_dir + "RECORD"
    info = {
        "format": 1,
        "native_binary": {"name": "breeze-server", "sha256": "stale"},
        "native_dependencies": [],
    }
    worker_info = _zip_info(worker_name, 0o100755)
    dependency_info = _zip_info(dependency_name, 0o100644)
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(_zip_info(package_dir, 0o40755), b"")
        archive.writestr(_zip_info(bin_dir, 0o40755), b"")
        archive.writestr(_zip_info(dist_info_dir, 0o40755), b"")
        archive.writestr(worker_info, b"repaired-elf")
        archive.writestr(dependency_info, b"bundled-loader")
        archive.writestr(info_name, json.dumps(info).encode())
        archive.writestr(record_name, b"old\n")

    finalize_wheel.finalize(wheel)

    with zipfile.ZipFile(wheel) as archive:
        updated = json.loads(archive.read(info_name))
        infos = {info.filename: info for info in archive.infolist()}
        rows = list(csv.reader(io.StringIO(archive.read(record_name).decode())))
        payloads = {
            name: archive.read(name)
            for name, info in infos.items()
            if not info.is_dir()
        }

    assert updated["native_binary"]["sha256"] == hashlib.sha256(
        b"repaired-elf"
    ).hexdigest()
    assert updated["native_dependencies"] == [{
        "name": "libvulkan-bundled.so",
        "sha256": hashlib.sha256(b"bundled-loader").hexdigest(),
    }]
    assert infos[worker_name].external_attr == worker_info.external_attr
    assert infos[dependency_name].external_attr == dependency_info.external_attr
    assert {name for name, info in infos.items() if info.is_dir()} == {
        package_dir,
        bin_dir,
        dist_info_dir,
    }

    row_map = {row[0]: row[1:] for row in rows}
    assert set(row_map) == set(payloads)
    assert row_map[record_name] == ["", ""]
    for name, payload in payloads.items():
        if name == record_name:
            continue
        assert row_map[name] == [_record_digest(payload), str(len(payload))]
    assert package_dir not in row_map
    assert bin_dir not in row_map
    assert dist_info_dir not in row_map
