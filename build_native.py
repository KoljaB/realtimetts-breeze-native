"""Clone, patch, build, and package the pinned Breeze native worker."""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

import build_package

UPSTREAM_URL = build_package.UPSTREAM_URL
UPSTREAM_WEBUI_EMBED_SHA256 = (
    "4e71bb55410c1dbe3d0a5a3e23d1a4bf1ae550b654058aef36b42dda6d9b36ac"
)
WEBUI_EMBED_SCRIPT = build_package.ROOT / "tools" / "embed_webui.cmake"


class NativeBuildError(RuntimeError):
    """The reproducible native build could not be completed."""


def _run(command: list[str], *, cwd: Path | None = None,
         env: dict[str, str] | None = None) -> None:
    print("$ " + " ".join(command))
    try:
        subprocess.run(command, cwd=os.fspath(cwd) if cwd else None,
                       env=env, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise NativeBuildError(f"command failed: {command[0]}") from exc


def _git_command(path: Path, *args: str) -> list[str]:
    return ["git", "-c", f"safe.directory={path.as_posix()}",
            "-C", os.fspath(path), *args]


def _revision(path: Path) -> str:
    try:
        return subprocess.run(
            _git_command(path, "rev-parse", "HEAD"), check=True,
            capture_output=True, text=True,
        ).stdout.strip().lower()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise NativeBuildError(f"cannot read Git revision: {path}") from exc


def _status(path: Path) -> str:
    return subprocess.run(
        _git_command(path, "status", "--porcelain", "--untracked-files=all"),
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def ensure_pinned_source(source: Path) -> Path:
    source = source.resolve()
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--no-checkout", UPSTREAM_URL,
              os.fspath(source)])
        _run(_git_command(source, "fetch", "--no-tags", "origin",
                          build_package.UPSTREAM_REVISION))
        _run(_git_command(source, "checkout", "--detach",
                          build_package.UPSTREAM_REVISION))
    if not (source / ".git").exists():
        raise NativeBuildError(f"source is not a Git checkout: {source}")
    if _revision(source) != build_package.UPSTREAM_REVISION:
        raise NativeBuildError(
            f"source is not {build_package.UPSTREAM_REVISION}; use a fresh work directory"
        )
    _run(_git_command(source, "submodule", "update", "--init", "--recursive"))
    ggml = source / "third_party" / "ggml"
    if _revision(ggml) != build_package.GGML_REVISION:
        raise NativeBuildError(f"ggml is not {build_package.GGML_REVISION}")
    if _status(source):
        raise NativeBuildError("source checkout is dirty before applying controls")
    return source


def ensure_pinned_spirv_headers(source: Path) -> Path:
    source = source.resolve()
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--no-checkout",
              build_package.SPIRV_HEADERS_URL, os.fspath(source)])
        _run(_git_command(source, "fetch", "--no-tags", "origin",
                          build_package.SPIRV_HEADERS_REVISION))
        _run(_git_command(source, "checkout", "--detach",
                          build_package.SPIRV_HEADERS_REVISION))
    if not (source / ".git").exists():
        raise NativeBuildError(f"SPIRV-Headers is not a Git checkout: {source}")
    if _revision(source) != build_package.SPIRV_HEADERS_REVISION:
        raise NativeBuildError(
            "SPIRV-Headers is not the pinned revision; use a fresh work directory"
        )
    if _status(source):
        raise NativeBuildError("SPIRV-Headers checkout is dirty")
    return source


def apply_controls(source: Path) -> None:
    _run([sys.executable, "-B",
          os.fspath(build_package.ROOT / "tools" / "prepare_breeze_cpp.py"),
          os.fspath(source)], cwd=build_package.ROOT)


def prepare_webui_embed(source: Path) -> None:
    target = source / "cmake" / "embed_webui.cmake"
    replacement = WEBUI_EMBED_SCRIPT.read_bytes()
    try:
        current = target.read_bytes()
    except OSError as exc:
        raise NativeBuildError(
            f"cannot read upstream WebUI embed script: {target}"
        ) from exc
    if current == replacement:
        return
    normalized = current.replace(b"\r\n", b"\n")
    if hashlib.sha256(normalized).hexdigest() != UPSTREAM_WEBUI_EMBED_SHA256:
        raise NativeBuildError(
            "unexpected upstream WebUI embed script; refuse to replace"
        )
    temporary = target.with_name(target.name + ".realtimetts-webui.tmp")
    try:
        temporary.write_bytes(replacement)
        temporary.replace(target)
    except OSError as exc:
        raise NativeBuildError(
            f"cannot install bounded WebUI embed script: {target}"
        ) from exc


def configure_spirv_headers(source: Path, build: Path, install: Path,
                           platform: str, generator: str) -> Path:
    for directory in (build, install):
        if directory.exists() and any(directory.iterdir()):
            raise NativeBuildError(f"SPIRV-Headers directory is not empty: {directory}")
    build.mkdir(parents=True, exist_ok=True)
    install.mkdir(parents=True, exist_ok=True)
    command = ["cmake", "-S", os.fspath(source), "-B", os.fspath(build),
               "-G", generator, "-DCMAKE_BUILD_TYPE=Release",
               "-DSPIRV_HEADERS_ENABLE_TESTS=OFF",
               "-DSPIRV_HEADERS_ENABLE_INSTALL=ON",
               f"-DCMAKE_INSTALL_PREFIX={install}"]
    if platform == "win_amd64" and generator.lower().startswith("visual studio"):
        command.extend(["-A", "x64"])
    _run(command)
    _run(["cmake", "--build", os.fspath(build), "--config", "Release",
          "--target", "install", "--parallel"])
    configs = sorted(install.rglob("SPIRV-HeadersConfig.cmake"))
    if len(configs) != 1:
        raise NativeBuildError(
            f"expected one installed SPIRV-HeadersConfig.cmake under {install}"
        )
    return configs[0].parent


def cmake_definitions(sdk: Path | None, platform: str = "") -> list[str]:
    result = ["-DCMAKE_BUILD_TYPE=Release"]
    result.extend(
        f"-D{name}={value}"
        for name, value in build_package.REQUIRED_CACHE_FLAGS.items()
    )
    if platform == "win_amd64":
        result.append("-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded")
    if sdk:
        sdk = sdk.resolve()
        include_dir = sdk / ("Include" if platform == "win_amd64" else "include")
        result.extend([
            f"-DVULKAN_SDK={sdk}", f"-DVulkan_ROOT={sdk}",
            f"-DVulkan_INCLUDE_DIR={include_dir}",
        ])
        if platform == "win_amd64":
            result.append(f"-DVulkan_LIBRARY={sdk / 'Lib' / 'vulkan-1.lib'}")
    return result


def configure_and_build(source: Path, build: Path, platform: str,
                        generator: str, sdk: Path | None,
                        cmake_args: Iterable[str],
                        spirv_headers_dir: Path | None = None) -> None:
    build.mkdir(parents=True, exist_ok=True)
    command = ["cmake", "-S", os.fspath(source), "-B", os.fspath(build),
               "-G", generator]
    if platform == "win_amd64" and generator.lower().startswith("visual studio"):
        command.extend(["-A", "x64"])
    command.extend(cmake_definitions(sdk, platform))
    command.extend(cmake_args)
    if spirv_headers_dir:
        command.append(f"-DSPIRV-Headers_DIR={spirv_headers_dir.resolve()}")
    env = os.environ.copy()
    if sdk:
        sdk = sdk.resolve()
        env["VULKAN_SDK"] = os.fspath(sdk)
        sdk_bin = sdk / ("Bin" if (sdk / "Bin").is_dir() else "bin")
        if sdk_bin.is_dir():
            env["PATH"] = os.pathsep.join(
                [os.fspath(sdk_bin), env.get("PATH", "")]
            )
        prefixes = [os.fspath(sdk), os.fspath(sdk / "lib" / "VulkanLoader")]
        if env.get("CMAKE_PREFIX_PATH"):
            prefixes.append(env["CMAKE_PREFIX_PATH"])
        env["CMAKE_PREFIX_PATH"] = os.pathsep.join(prefixes)
    _run(command, env=env)
    _run(["cmake", "--build", os.fspath(build), "--config", "Release",
          "--target", "breeze-server", "--parallel"], env=env)


def stage_and_package(source: Path, build: Path, stage: Path, platform: str,
                      wheelhouse: Path) -> list[Path]:
    if stage.exists() and any(stage.iterdir()):
        raise NativeBuildError(f"stage is not empty: {stage}")
    if wheelhouse.exists() and any(wheelhouse.iterdir()):
        raise NativeBuildError(f"wheelhouse is not empty: {wheelhouse}")
    stage.mkdir(parents=True, exist_ok=True)
    wheelhouse.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "BREEZE_SOURCE_DIR": os.fspath(source),
        "BREEZE_BUILD_DIR": os.fspath(build),
        "BREEZE_NATIVE_STAGE_DIR": os.fspath(stage),
        "BREEZE_WHEEL_PLATFORM": platform,
    })
    _run([sys.executable, "-B", os.fspath(build_package.ROOT / "build_package.py")],
         cwd=build_package.ROOT, env=env)
    for kind in ("sdist", "wheel"):
        _run([sys.executable, "-m", "build", f"--{kind}",
              "--outdir", os.fspath(wheelhouse), os.fspath(build_package.ROOT)],
             cwd=build_package.ROOT, env=env)
    return sorted(wheelhouse.iterdir())


def main(argv: list[str] | None = None) -> int:
    default_platform = "win_amd64" if os.name == "nt" else "linux_x86_64"
    default_generator = "Visual Studio 17 2022" if os.name == "nt" else "Ninja"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=sorted(build_package.PLATFORMS),
                        default=default_platform)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--stage-dir", type=Path)
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--generator", default=default_generator)
    parser.add_argument("--vulkan-sdk", type=Path)
    parser.add_argument("--cmake-arg", action="append", default=[])
    args = parser.parse_args(argv)
    base = (args.work_dir or
            Path(tempfile.gettempdir()) / "realtimetts-breeze-native" /
            args.platform).resolve()
    source = (args.source_dir or base / "source").resolve()
    build = (args.build_dir or base / "build").resolve()
    spirv_headers_source = (base / "spirv-headers").resolve()
    spirv_headers_build = (base / "spirv-headers-build").resolve()
    spirv_headers_install = (base / "spirv-headers-install").resolve()
    stage = (args.stage_dir or base / "stage").resolve()
    wheelhouse = (args.wheelhouse or base / "wheels").resolve()
    sdk = args.vulkan_sdk or (
        Path(os.environ["VULKAN_SDK"]) if os.environ.get("VULKAN_SDK") else None
    )
    if sdk and not sdk.is_dir():
        raise NativeBuildError(f"Vulkan SDK directory does not exist: {sdk}")
    ensure_pinned_source(source)
    apply_controls(source)
    prepare_webui_embed(source)
    ensure_pinned_spirv_headers(spirv_headers_source)
    spirv_headers_dir = configure_spirv_headers(
        spirv_headers_source, spirv_headers_build, spirv_headers_install,
        args.platform, args.generator
    )
    configure_and_build(source, build, args.platform, args.generator, sdk,
                        args.cmake_arg, spirv_headers_dir)
    for artifact in stage_and_package(source, build, stage, args.platform,
                                      wheelhouse):
        print(f"artifact: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
