"""Download and install the pinned portable Windows Vulkan SDK for CI."""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

VERSION = "1.3.296.0"
URL = ("https://sdk.lunarg.com/sdk/download/1.3.296.0/windows/"
       "VulkanSDK-1.3.296.0-Installer.exe")
SHA256 = "acb4ae0786fd3e558f8b3c36cc3eba91638984217ba8a6795ec64d2f9ffd8c4b"
FILENAME = f"VulkanSDK-{VERSION}-Installer.exe"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and sha256(destination) == SHA256:
        return destination
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    with urllib.request.urlopen(URL, timeout=120) as response, \
            temporary.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    if sha256(temporary) != SHA256:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Vulkan SDK checksum mismatch: {URL}")
    temporary.replace(destination)
    return destination


def find_sdk() -> Path:
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


def install(output_root: Path) -> Path:
    output_root = output_root.resolve()
    installer = download_verified(output_root / FILENAME)
    subprocess.run([
        os.fspath(installer), "--accept-licenses", "--default-answer",
        "--confirm-command", "install", "copy_only=1",
    ], check=True)
    sdk = find_sdk()
    (output_root / "sdk-dir.txt").write_text(
        os.fspath(sdk) + "\n", encoding="utf-8", newline="\n"
    )
    return sdk


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    sdk = install(parser.parse_args().output_root)
    print(sdk)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
