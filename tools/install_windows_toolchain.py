"""Install the hashed GCC and Vulkan shader tools used for Windows wheels.

GGML_NATIVE stays OFF in build_native.py; these compiler choices do not embed
CI-host CPU settings in the worker. No toolchain is required by wheel users.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import shutil
import subprocess
from install_vulkan_sdk import download_verified

WINLIBS = "winlibs-x86_64-posix-seh-gcc-12.2.0-llvm-16.0.0-mingw-w64ucrt-10.0.0-r5.7z"
WINLIBS_URL = "https://github.com/brechtsanders/winlibs_mingw/releases/download/12.2.0-16.0.0-10.0.0-ucrt-r5/" + WINLIBS
WINLIBS_SHA256 = "ff680d2544a4233e50218bc56ab3c2c7684b7b3ed9946336db7dbb457c6a8385"
PACKAGES = {
    "shaderc-2026.3-1": "0af3be0981f194806859a521c8ea944e084a69bb720d59aae2adedfd88c14adc",
    "glslang-16.3.0-1": "5a90c8ae45b42b500fa03669aa1a94d154dcd13e0bb254f86df004b903826c03",
    "spirv-tools-3~1.4.357.0-1": "ba11b4bad606f6ececc5bf5910f97077071624851c81a25fafc6b0ec88c58b84",
    "vulkan-headers-1~1.4.357.0-1": "96749e9c3c10bd7dd6624530006b4ed5c165c0f1bc37125522e046c63aed649c",
    "vulkan-loader-1~1.4.357.0-1": "4d34983aea34116582700b285279df21cd0ee8519025330e7ac0650bb02f138f",
}


def install(root: Path) -> None:
    root = root.resolve()
    archives = root / "archives"
    seven_zip = shutil.which("7z") or str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "7-Zip/7z.exe")
    archive = download_verified(WINLIBS_URL, archives / WINLIBS, WINLIBS_SHA256)
    subprocess.run([seven_zip, "x", "-y", f"-o{root}", str(archive)], check=True, stdout=subprocess.DEVNULL)
    for package, checksum in PACKAGES.items():
        name = "mingw-w64-ucrt-x86_64-" + package + "-any.pkg.tar.zst"
        archive = download_verified("https://repo.msys2.org/mingw/ucrt64/" + name, archives / name, checksum)
        subprocess.run(["tar", "-xf", str(archive), "-C", str(root)], check=True)
    for tool in (root / "mingw64/bin/g++.exe", root / "ucrt64/bin/glslc.exe"):
        subprocess.run([str(tool), "--version"], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    install(parser.parse_args().output_root)
