"""Clone, patch, build, and package the pinned Breeze native worker."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

import build_package

UPSTREAM_URL = build_package.UPSTREAM_URL


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


def apply_controls(source: Path) -> None:
    _run([sys.executable, "-B",
          os.fspath(build_package.ROOT / "tools" / "prepare_breeze_cpp.py"),
          os.fspath(source)], cwd=build_package.ROOT)


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
        result.extend([
            f"-DVULKAN_SDK={sdk}", f"-DVulkan_ROOT={sdk}",
            f"-DVulkan_INCLUDE_DIR={sdk / 'Include'}",
        ])
        if platform == "win_amd64":
            result.append(f"-DVulkan_LIBRARY={sdk / 'Lib' / 'vulkan-1.lib'}")
    return result


def configure_and_build(source: Path, build: Path, platform: str,
                        generator: str, sdk: Path | None,
                        cmake_args: Iterable[str]) -> None:
    build.mkdir(parents=True, exist_ok=True)
    command = ["cmake", "-S", os.fspath(source), "-B", os.fspath(build),
               "-G", generator]
    if platform == "win_amd64" and generator.lower().startswith("visual studio"):
        command.extend(["-A", "x64"])
    command.extend(cmake_definitions(sdk, platform))
    command.extend(cmake_args)
    env = os.environ.copy()
    if sdk:
        env["VULKAN_SDK"] = os.fspath(sdk.resolve())
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
    stage = (args.stage_dir or base / "stage").resolve()
    wheelhouse = (args.wheelhouse or base / "wheels").resolve()
    sdk = args.vulkan_sdk or (
        Path(os.environ["VULKAN_SDK"]) if os.environ.get("VULKAN_SDK") else None
    )
    if sdk and not sdk.is_dir():
        raise NativeBuildError(f"Vulkan SDK directory does not exist: {sdk}")
    ensure_pinned_source(source)
    apply_controls(source)
    configure_and_build(source, build, args.platform, args.generator, sdk,
                        args.cmake_arg)
    for artifact in stage_and_package(source, build, stage, args.platform,
                                      wheelhouse):
        print(f"artifact: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
