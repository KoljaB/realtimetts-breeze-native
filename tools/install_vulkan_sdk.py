"""Download and install the pinned portable LunarG Vulkan SDK for CI."""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

VERSION = "1.3.296.0"
WINDOWS_URL = (
    "https://sdk.lunarg.com/sdk/download/1.3.296.0/windows/"
    "VulkanSDK-1.3.296.0-Installer.exe?Human=true"
)
WINDOWS_SHA256 = "acb4ae0786fd3e558f8b3c36cc3eba91638984217ba8a6795ec64d2f9ffd8c4b"
WINDOWS_FILENAME = f"VulkanSDK-{VERSION}-Installer.exe"
LINUX_URL = (
    "https://sdk.lunarg.com/sdk/download/1.3.296.0/linux/"
    "vulkansdk-linux-x86_64-1.3.296.0.tar.xz?Human=true"
)
LINUX_SHA256 = "79b0a1593dadc46180526250836f3e53688a9a5fb42a0e5859eb72316dc4d53e"
LINUX_FILENAME = f"vulkansdk-linux-x86_64-{VERSION}.tar.xz"
USER_AGENT = (
    "realtimetts-breeze-native-ci/0.1 "
    "(+https://github.com/KoljaB/realtimetts-breeze-native)"
)
# Backward-compatible aliases for callers that validated the Windows installer.
URL = WINDOWS_URL
SHA256 = WINDOWS_SHA256


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified(url: str, destination: Path, expected_sha256: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and sha256(destination) == expected_sha256:
        return destination
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, \
                temporary.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    if sha256(temporary) != expected_sha256:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Vulkan SDK checksum mismatch: {url}")
    temporary.replace(destination)
    return destination


def linux_sdk_path(output_root: Path) -> Path:
    return output_root.resolve() / VERSION / "x86_64"


def _extract_archive(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:xz") as source:
        members = source.getmembers()
        for member in members:
            target = (destination / member.name).resolve()
            if not target.is_relative_to(destination):
                raise RuntimeError(f"Vulkan SDK archive escapes destination: {member.name}")
            if member.issym() or member.islnk():
                link_target = (target.parent / member.linkname).resolve()
                if not link_target.is_relative_to(destination):
                    raise RuntimeError(f"Vulkan SDK link escapes destination: {member.name}")
        source.extractall(destination)


def _find_windows_sdk() -> Path:
    candidates = []
    if os.environ.get("VULKAN_SDK"):
        candidates.append(Path(os.environ["VULKAN_SDK"]))
    candidates.extend([
        Path("C:/VulkanSDK") / VERSION,
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) /
        "Vulkan SDK" / VERSION,
    ])
    for candidate in candidates:
        if (candidate / "Include" / "vulkan" / "vulkan.h").is_file():
            return candidate.resolve()
    raise RuntimeError("Vulkan SDK install completed but no SDK headers were found")


def install(output_root: Path, platform: str) -> Path:
    output_root = output_root.resolve()
    if platform == "linux":
        archive = download_verified(
            LINUX_URL, output_root / LINUX_FILENAME, LINUX_SHA256
        )
        sdk = linux_sdk_path(output_root)
        if not (sdk / "include" / "vulkan" / "vulkan.h").is_file():
            _extract_archive(archive, output_root)
        if not (sdk / "bin" / "glslc").is_file():
            raise RuntimeError(f"LunarG Linux SDK is missing glslc: {sdk}")
    elif platform == "windows":
        installer = download_verified(
            WINDOWS_URL, output_root / WINDOWS_FILENAME, WINDOWS_SHA256
        )
        subprocess.run([
            os.fspath(installer), "--accept-licenses", "--default-answer",
            "--confirm-command", "install", "copy_only=1",
        ], check=True)
        sdk = _find_windows_sdk()
    else:
        raise ValueError(f"unsupported SDK platform: {platform}")
    (output_root / "sdk-dir.txt").write_text(
        os.fspath(sdk) + "\n", encoding="utf-8", newline="\n"
    )
    return sdk


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--platform", choices=("linux", "windows"),
        default="windows" if os.name == "nt" else "linux",
    )
    args = parser.parse_args()
    sdk = install(args.output_root, args.platform)
    print(sdk)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
