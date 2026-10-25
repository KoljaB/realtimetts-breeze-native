"""Validate a pinned Breeze build and stage one native worker."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


PACKAGE_NAME = "realtimetts_breeze_native"
PACKAGE_VERSION = "0.1.0rc3"
UPSTREAM_URL = "https://github.com/HoppouAI/Breeze-TTS-2.cpp.git"
UPSTREAM_REVISION = "a0e177f91242ebbd2ea8d61548d742c89e4b9e06"
GGML_REVISION = "36da57138425487184aa1da2eee2cde155909c6f"
SPIRV_HEADERS_URL = "https://github.com/KhronosGroup/SPIRV-Headers.git"
SPIRV_HEADERS_REVISION = "2a9b6f951c7d6b04b6c21fe1bf3f475b68b84801"
CONTROL_PATCH_SHA256 = (
    "12c938d19fcf612bbfffc39791b7741d0303c2ffb6cfd554034e08051c25e9b3"
)
PLATFORMS = frozenset({"linux_x86_64", "win_amd64"})
REQUIRED_CACHE_FLAGS = {
    "BREEZE_BUILD_CLI": "OFF",
    "BREEZE_BUILD_SERVER": "ON",
    "BREEZE_BUILD_SHARED": "OFF",
    "BREEZE_BUILD_TESTS": "OFF",
    "BREEZE_CUDA": "OFF",
    "BREEZE_MP3": "OFF",
    "BREEZE_VULKAN": "ON",
    "BUILD_SHARED_LIBS": "OFF",
    "GGML_CUDA": "OFF",
    "GGML_NATIVE": "OFF",
    "GGML_OPENMP": "OFF",
    "GGML_VULKAN": "ON",
}
ROOT = Path(__file__).resolve().parent
CONTROL_PATCH = ROOT / "tools" / "breeze_cpp_controls.json"


class BuildInputError(ValueError):
    """The supplied native build cannot be assembled safely."""


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(path: Path, expected: str) -> None:
    try:
        actual = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={path.as_posix()}",
                "-C",
                os.fspath(path),
                "rev-parse",
                "HEAD",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip().lower()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BuildInputError(f"cannot read Git revision for {path}") from exc
    if actual != expected:
        raise BuildInputError(f"Git revision for {path} does not match {expected}")


def _cache(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise BuildInputError(f"CMake cache is missing: {path}")
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith(("//", "#")) and "=" in line:
            left, value = line.split("=", 1)
            if ":" in left:
                values[left.split(":", 1)[0]] = value.strip()
    return values


def _env(name: str) -> Path:
    value = os.environ.get(name, "").strip()
    if not value:
        raise BuildInputError(f"{name} is required")
    return Path(value).resolve()


def worker_filename(platform: str) -> str:
    if platform not in PLATFORMS:
        raise BuildInputError(
            f"native wheel platform must be one of {sorted(PLATFORMS)}, got {platform!r}"
        )
    return "breeze-server.exe" if platform == "win_amd64" else "breeze-server"


def _check_patch(source: Path) -> None:
    try:
        subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools" / "prepare_breeze_cpp.py"),
             str(source), "--check"],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BuildInputError("native control patch is not installed") from exc



def _runtime_dlls(binary: Path, platform: str) -> list[Path]:
    if platform != "win_amd64":
        return []
    return sorted(
        (
            path for path in binary.parent.glob("*.dll")
            if path.is_file() and path.name.lower() != "vulkan-1.dll"
        ),
        key=lambda path: path.name.lower(),
    )

def assemble(
    source_dir: Path, build_dir: Path, stage_dir: Path, platform: str
) -> Path:
    source, build, stage = (
        source_dir.resolve(),
        build_dir.resolve(),
        stage_dir.resolve(),
    )
    name = worker_filename(platform)
    if stage.is_relative_to(ROOT):
        raise BuildInputError(f"staging must be outside the repository: {stage}")
    if not source.is_dir() or not build.is_dir():
        raise BuildInputError("source and build directories must exist")
    if not CONTROL_PATCH.is_file() or _hash(CONTROL_PATCH) != CONTROL_PATCH_SHA256:
        raise BuildInputError("control patch is missing or changed")
    _git(source, UPSTREAM_REVISION)
    _git(source / "third_party" / "ggml", GGML_REVISION)
    _check_patch(source)

    cache = _cache(build / "CMakeCache.txt")
    home = cache.get("CMAKE_HOME_DIRECTORY", "")
    if not home or Path(home).resolve() != source:
        raise BuildInputError("CMAKE_HOME_DIRECTORY does not match BREEZE_SOURCE_DIR")
    if cache.get("CMAKE_BUILD_TYPE", "").lower() != "release":
        raise BuildInputError("CMAKE_BUILD_TYPE must be Release")
    for key, expected in REQUIRED_CACHE_FLAGS.items():
        if cache.get(key, "").upper() != expected:
            raise BuildInputError(f"CMake flag {key} must be {expected}")

    workers = [path for path in build.rglob(name) if path.is_file()]
    if len(workers) != 1 or workers[0].stat().st_size == 0:
        raise BuildInputError(f"expected one non-empty {name} under {build}")
    binary = workers[0]
    if stage.exists() and (not stage.is_dir() or any(stage.iterdir())):
        raise BuildInputError(f"staging directory must be empty: {stage}")
    payload = stage / PACKAGE_NAME / "bin"
    payload.mkdir(parents=True, exist_ok=True)
    destination = payload / name
    shutil.copy2(binary, destination)
    if platform == "linux_x86_64":
        destination.chmod(destination.stat().st_mode | 0o111)
    dependencies = _runtime_dlls(binary, platform)
    for dependency in dependencies:
        shutil.copy2(dependency, payload / dependency.name)
    info = {
        "format": 1,
        "version": PACKAGE_VERSION,
        "source_url": UPSTREAM_URL,
        "distribution": PACKAGE_NAME,
        "platform": platform,
        "source_revision": UPSTREAM_REVISION,
        "ggml_revision": GGML_REVISION,
        "spirv_headers_url": SPIRV_HEADERS_URL,
        "spirv_headers_revision": SPIRV_HEADERS_REVISION,
        "control_patch_sha256": CONTROL_PATCH_SHA256,
        "native_binary": {"name": name, "sha256": _hash(binary)},
        "native_dependencies": [
            {"name": path.name, "sha256": _hash(path)} for path in dependencies
        ],
        "host_runtime_dependencies": ["Vulkan loader and ICD supplied by host"],
        "cmake": {
            "source_matches": True,
            "build_type": "Release",
            "cache_flags": REQUIRED_CACHE_FLAGS,
        },
    }
    (payload / "build-info.json").write_text(
        json.dumps(info, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return destination


def main() -> int:
    destination = assemble(
        _env("BREEZE_SOURCE_DIR"),
        _env("BREEZE_BUILD_DIR"),
        _env("BREEZE_NATIVE_STAGE_DIR"),
        os.environ.get("BREEZE_WHEEL_PLATFORM", "").strip(),
    )
    print(f"Staged {PACKAGE_NAME}: {destination}")
    print(f"Native binary SHA-256: {_hash(destination)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
