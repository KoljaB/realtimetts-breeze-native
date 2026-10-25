from __future__ import annotations

import ctypes
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

# CUDA 12 runtime libraries come from NVIDIA's wheels; the driver is the host's.
_RUNTIME_PACKAGES = ("nvidia.cuda_runtime", "nvidia.cublas")


def executable_path() -> Path:
    path = Path(__file__).resolve().parent / "bin" / "breeze-server"
    if not path.is_file():
        raise FileNotFoundError(f"packaged Breeze CUDA worker is missing: {path}")
    if not os.access(path, os.X_OK):
        raise PermissionError(f"packaged Breeze CUDA worker is not executable: {path}")
    return path


def runtime_library_dirs() -> list[Path]:
    dirs = []
    for name in _RUNTIME_PACKAGES:
        spec = importlib.util.find_spec(name)
        for location in (spec.submodule_search_locations or []) if spec else []:
            lib = Path(location) / "lib"
            if lib.is_dir():
                dirs.append(lib)
    return dirs


def cuda_available() -> bool:
    """Whether the host NVIDIA driver can be loaded."""
    try:
        ctypes.CDLL("libcuda.so.1")
    except OSError:
        return False
    return True


def worker_env(base=None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    paths = [os.fspath(path) for path in runtime_library_dirs()]
    if env.get("LD_LIBRARY_PATH"):
        paths.append(env["LD_LIBRARY_PATH"])
    if paths:
        env["LD_LIBRARY_PATH"] = os.pathsep.join(paths)
    return env


def worker_command(args=()):
    return [os.fspath(executable_path()), *[os.fspath(arg) for arg in args]]


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: realtimetts-breeze-native-cuda12 <breeze-server arguments...>", file=sys.stderr)
        return 2
    return subprocess.call(worker_command(args), env=worker_env())
