from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import build_package
from realtimetts_breeze_native_cuda12 import launcher
from tests.test_native_package import _cache_text, native_fixture  # noqa: F401


def test_cuda_profile_is_linux_only_and_separate() -> None:
    profile = build_package.backend_profile("cuda12")
    assert profile["package"] == "realtimetts_breeze_native_cuda12"
    assert build_package.worker_filename("linux_x86_64", "cuda12") == "breeze-server"
    with pytest.raises(build_package.BuildInputError, match="native wheel platform"):
        build_package.worker_filename("win_amd64", "cuda12")
    with pytest.raises(build_package.BuildInputError, match="native backend"):
        build_package.backend_profile("rocm")
    flags = profile["cache_flags"]
    assert flags["GGML_CUDA"] == "ON" and flags["GGML_VULKAN"] == "OFF"
    assert flags["CMAKE_CUDA_ARCHITECTURES"] == build_package.CUDA_ARCHITECTURES
    assert build_package.REQUIRED_CACHE_FLAGS["GGML_VULKAN"] == "ON"


def test_cuda_stage_requires_cuda_flags_and_records_backend(
    native_fixture: dict[str, Path], tmp_path: Path  # noqa: F811
) -> None:
    build = native_fixture["build"]
    (build / "breeze-server").write_bytes(b"cuda-test-binary")
    with pytest.raises(build_package.BuildInputError, match="CMake flag"):
        build_package.assemble(native_fixture["source"], build, tmp_path / "vulkan-stage",
                               "linux_x86_64", "cuda12")
    values = {**build_package.CUDA_CACHE_FLAGS}
    (build / "CMakeCache.txt").write_text(_cache_text(native_fixture["source"], values),
                                          encoding="utf-8")
    destination = build_package.assemble(native_fixture["source"], build, tmp_path / "stage",
                                         "linux_x86_64", "cuda12")
    assert destination.parent.parent.name == "realtimetts_breeze_native_cuda12"
    info = json.loads(destination.with_name("build-info.json").read_text(encoding="utf-8"))
    assert info["backend"] == "cuda12"
    assert info["distribution"] == "realtimetts_breeze_native_cuda12"
    assert info["cmake"]["cache_flags"]["GGML_CUDA"] == "ON"
    assert any("NVIDIA driver" in item for item in info["host_runtime_dependencies"])


def test_worker_env_prepends_nvidia_wheel_libraries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime, cublas = tmp_path / "cuda_runtime" / "lib", tmp_path / "cublas" / "lib"
    monkeypatch.setattr(launcher, "runtime_library_dirs", lambda: [runtime, cublas])
    env = launcher.worker_env({"LD_LIBRARY_PATH": "/opt/host"})
    assert env["LD_LIBRARY_PATH"].split(os.pathsep) == [str(runtime), str(cublas), "/opt/host"]
    assert launcher.worker_env({})["LD_LIBRARY_PATH"].split(os.pathsep) == [str(runtime), str(cublas)]


def test_cuda_launcher_passes_library_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(launcher, "executable_path", lambda: Path("breeze-server"))
    monkeypatch.setattr(launcher, "worker_env", lambda: {"LD_LIBRARY_PATH": "/nvidia"})
    monkeypatch.setattr(launcher.subprocess, "call",
                        lambda command, env: calls.append((command, env)) or 5)
    assert launcher.main(["model.gguf"]) == 5
    assert calls == [(["breeze-server", "model.gguf"], {"LD_LIBRARY_PATH": "/nvidia"})]
