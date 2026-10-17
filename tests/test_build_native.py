from __future__ import annotations

import hashlib
from pathlib import Path

import build_native
import build_package


def test_cmake_definitions_are_the_reviewed_static_vulkan_set():
    values = build_native.cmake_definitions(None)
    assert "-DCMAKE_BUILD_TYPE=Release" in values
    assert values == [
        "-DCMAKE_BUILD_TYPE=Release",
        *[
            f"-D{name}={value}"
            for name, value in build_package.REQUIRED_CACHE_FLAGS.items()
        ],
    ]


def test_linux_sdk_uses_case_sensitive_include_layout(tmp_path: Path):
    values = build_native.cmake_definitions(tmp_path, "linux_x86_64")
    assert f"-DVulkan_INCLUDE_DIR={tmp_path / 'include'}" in values
    assert f"-DVulkan_INCLUDE_DIR={tmp_path / 'Include'}" not in values


def test_verified_sdk_rejects_wrong_checksum(tmp_path: Path, monkeypatch):
    installer = tmp_path / "sdk.exe"
    installer.write_bytes(b"wrong")
    monkeypatch.setattr(build_native, "UPSTREAM_URL", build_package.UPSTREAM_URL)
    from tools import install_vulkan_sdk
    assert install_vulkan_sdk.sha256(installer) != install_vulkan_sdk.SHA256


def test_platform_build_uses_visual_studio_architecture(tmp_path: Path):
    calls: list[list[str]] = []
    old = build_native._run
    try:
        build_native._run = lambda command, **kwargs: calls.append(command)
        source = tmp_path / "source"
        build = tmp_path / "build"
        build_native.configure_and_build(
            source, build, "win_amd64", "Visual Studio 17 2022", None, []
        )
    finally:
        build_native._run = old
    assert calls[0][calls[0].index("-A") + 1] == "x64"
    assert "-DBREEZE_BUILD_SERVER=ON" in calls[0]
    assert "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded" in calls[0]


def test_fresh_clone_detaches_to_pinned_revision(monkeypatch, tmp_path: Path):
    source = tmp_path / "source"
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[:2] == ["git", "clone"]:
            source.mkdir()
            (source / ".git").mkdir()
            (source / "third_party" / "ggml").mkdir(parents=True)

    monkeypatch.setattr(build_native, "_run", fake_run)
    monkeypatch.setattr(build_native, "_revision", lambda path: (
        build_package.GGML_REVISION
        if path.name == "ggml"
        else build_package.UPSTREAM_REVISION
    ))
    monkeypatch.setattr(build_native, "_status", lambda path: "")
    build_native.ensure_pinned_source(source)
    assert "--no-checkout" in calls[0]
    assert calls[1][-2:] == ["--detach", build_package.UPSTREAM_REVISION]
    assert "submodule" in calls[2]
