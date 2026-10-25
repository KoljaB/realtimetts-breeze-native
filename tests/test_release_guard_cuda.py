from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_package  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "release_guard_cuda_under_test", ROOT / "tools" / "release_guard.py"
)
assert SPEC is not None and SPEC.loader is not None
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)

VULKAN = "RealtimeTTSBreezeNativeDev"
CUDA = "RealtimeTTSBreezeNativeCUDA12Dev"


class PackagingAndGuardAgreeTests(unittest.TestCase):
    def test_guard_pins_the_packaged_control_patch(self) -> None:
        for name in (VULKAN, CUDA):
            with self.subTest(profile=name):
                contract = guard.COMPONENT_PROFILES[name]["native_build_info"]
                self.assertEqual(contract["control_patch_sha256"],
                                 build_package.CONTROL_PATCH_SHA256)
                self.assertEqual(contract["source_revision"], build_package.UPSTREAM_REVISION)
                self.assertEqual(contract["ggml_revision"], build_package.GGML_REVISION)

    def test_guard_pins_the_packaged_cmake_flags(self) -> None:
        for name, backend in ((VULKAN, "vulkan"), (CUDA, "cuda12")):
            with self.subTest(profile=name):
                contract = guard.COMPONENT_PROFILES[name]["native_build_info"]
                profile = build_package.backend_profile(backend)
                self.assertEqual(contract["cmake"]["cache_flags"], profile["cache_flags"])
                self.assertEqual(contract["distribution"], profile["package"])

    def test_cuda_profile_publishes_only_the_linux_cuda_wheel(self) -> None:
        profile = guard._component_profile(CUDA, publishing=True)
        self.assertEqual(profile["distribution"], "realtimetts-breeze-native-cuda12")
        self.assertEqual(profile["required_wheel_platforms"], ("manylinux_2_35_x86_64",))
        self.assertEqual(profile["publish_repository"], "testpypi")
        self.assertEqual(list(profile["native_build_info"]["platforms"]),
                         ["manylinux_2_35_x86_64"])


class VersionPolicyTests(unittest.TestCase):
    def test_dev_and_release_candidate_versions_are_accepted(self) -> None:
        for name in (VULKAN, CUDA):
            profile = guard._component_profile(name, publishing=True)
            for version in ("0.1.0.dev1", "0.1.0rc1", "0.1.0rc3", "0.1.0rc10"):
                with self.subTest(profile=name, version=version):
                    guard._validate_profile_version(profile, version)
            for version in ("0.1.0rc0", "0.1.0", "0.1.1rc1", "0.1.0rc1.dev1"):
                with self.subTest(profile=name, version=version):
                    with self.assertRaisesRegex(guard.GuardError, "version"):
                        guard._validate_profile_version(profile, version)


class CudaBuildInfoTests(unittest.TestCase):
    @staticmethod
    def _wheel(root: Path, flags: dict[str, str]) -> Path:
        contract = guard.COMPONENT_PROFILES[CUDA]["native_build_info"]
        binary = b"cuda-breeze-worker"
        info = {
            "format": contract["format"],
            "distribution": contract["distribution"],
            "backend": "cuda12",
            "platform": "linux_x86_64",
            "source_revision": contract["source_revision"],
            "ggml_revision": contract["ggml_revision"],
            "control_patch_sha256": contract["control_patch_sha256"],
            "native_binary": {"name": "breeze-server",
                              "sha256": hashlib.sha256(binary).hexdigest()},
            "native_dependencies": [],
            "cmake": {"source_matches": True, "build_type": "Release", "cache_flags": flags},
        }
        path = root / "cuda.whl"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("realtimetts_breeze_native_cuda12/bin/breeze-server", binary)
            archive.writestr("realtimetts_breeze_native_cuda12/bin/build-info.json",
                             json.dumps(info))
        return path

    def _validate(self, flags: dict[str, str]) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self._wheel(Path(temporary), flags)
            with zipfile.ZipFile(path) as archive:
                members = set(archive.namelist())
                guard._validate_native_build_info(
                    guard.COMPONENT_PROFILES[CUDA], archive, members,
                    "manylinux_2_35_x86_64",
                    ["realtimetts_breeze_native_cuda12/bin/breeze-server"],
                )

    def test_cuda_build_info_is_accepted(self) -> None:
        self._validate(dict(build_package.CUDA_CACHE_FLAGS))

    def test_vulkan_build_info_is_rejected_for_the_cuda_distribution(self) -> None:
        with self.assertRaisesRegex(guard.GuardError, "CMake contract"):
            self._validate(dict(build_package.REQUIRED_CACHE_FLAGS))

    def test_other_cuda_architectures_are_rejected(self) -> None:
        flags = {**build_package.CUDA_CACHE_FLAGS, "CMAKE_CUDA_ARCHITECTURES": "89"}
        with self.assertRaisesRegex(guard.GuardError, "CMake contract"):
            self._validate(flags)


if __name__ == "__main__":
    unittest.main()
