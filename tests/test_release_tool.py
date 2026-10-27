from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_package  # noqa: E402

SPEC = importlib.util.spec_from_file_location("release_tool", ROOT / "tools" / "release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def wheel(tmp_path: Path, backend: str, **overrides) -> Path:
    profile = build_package.backend_profile(backend)
    binary = b"native-worker"
    info = {
        "distribution": profile["package"],
        "backend": backend,
        "source_revision": build_package.UPSTREAM_REVISION,
        "ggml_revision": build_package.GGML_REVISION,
        "control_patch_sha256": build_package.CONTROL_PATCH_SHA256,
        "native_binary": {"name": "breeze-server", "sha256": hashlib.sha256(binary).hexdigest()},
        "cmake": {"cache_flags": profile["cache_flags"]},
    }
    info.update(overrides)
    path = tmp_path / f"{profile['package']}-0.1.0rc4-py3-none-manylinux_2_35_x86_64.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{profile['package']}/bin/breeze-server", binary)
        archive.writestr(f"{profile['package']}/bin/build-info.json", json.dumps(info))
    return path


@pytest.mark.parametrize("backend", ["vulkan", "cuda12"])
def test_build_info_matching_build_package_is_accepted(tmp_path, backend):
    release.check_native_build_info([wheel(tmp_path, backend)], backend)


@pytest.mark.parametrize("field,value,message", [
    ("control_patch_sha256", "0" * 64, "control_patch_sha256"),
    ("source_revision", "0" * 40, "source_revision"),
    ("cmake", {"cache_flags": build_package.REQUIRED_CACHE_FLAGS}, "CMake flags"),
    ("native_binary", {"name": "breeze-server", "sha256": "0" * 64}, "worker hash"),
])
def test_build_info_drift_is_refused(tmp_path, field, value, message):
    path = wheel(tmp_path, "cuda12", **{field: value})
    with pytest.raises(release.ReleaseError, match=message):
        release.check_native_build_info([path], "cuda12")


def test_every_native_distribution_has_a_release_branch() -> None:
    for name in ("realtimetts-breeze-native", "realtimetts-breeze-native-cuda12"):
        assert release.PROJECTS[name]["testpypi"] == ("origin", "main")
        assert release.PROJECTS[name]["native_backend"] in build_package.BACKENDS
