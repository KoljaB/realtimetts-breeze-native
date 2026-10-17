from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "release_guard_breeze_under_test", ROOT / "tools" / "release_guard.py"
)
assert SPEC is not None and SPEC.loader is not None
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class BreezeNativeDevelopmentProfileTests(unittest.TestCase):
    @staticmethod
    def profile() -> dict[str, object]:
        return guard._component_profile("RealtimeTTSBreezeNativeDev", publishing=True)

    def test_profile_inherits_trust_and_runtime_contract_without_qwen_binding(self) -> None:
        stable = guard.COMPONENT_PROFILES["RealtimeTTSQwenNative"]
        profile = self.profile()
        for key in ("signer", "signer_fingerprint", "service_required", "publishable"):
            with self.subTest(key=key):
                self.assertEqual(profile[key], stable[key])
        self.assertEqual(profile["service_name"], "breeze-native-qualification.service")
        self.assertNotEqual(profile["service_name"], stable["service_name"])
        self.assertEqual(profile["distribution"], "realtimetts-breeze-native")
        self.assertEqual(
            profile["packages"],
            ((
                "realtimetts_breeze_native",
                "src/realtimetts_breeze_native",
                "realtimetts_breeze_native",
            ),),
        )
        self.assertEqual(
            profile["required_wheel_platforms"],
            ("manylinux_2_35_x86_64", "win_amd64"),
        )
        self.assertEqual(profile["publish_sdist"], True)
        self.assertEqual(
            profile["remote_repository"],
            "github.com/koljab/realtimetts-breeze-native",
        )
        self.assertEqual(profile["remote_branch"], "main")
        self.assertEqual(profile["native_revision"], profile["native_build_info"]["source_revision"])

    def test_dev_version_policy_accepts_only_nonzero_010_dev_versions(self) -> None:
        profile = self.profile()
        for version in ("0.1.0.dev1", "0.1.0.dev9", "0.1.0.dev10"):
            with self.subTest(version=version):
                guard._validate_profile_version(profile, version)
        for version in ("0.1.0.dev0", "0.1.0", "0.1.1.dev1", "1.0.0.dev1"):
            with self.subTest(version=version):
                with self.assertRaisesRegex(guard.GuardError, "version"):
                    guard._validate_profile_version(profile, version)

    def test_testpypi_policy_rejects_other_indexes_and_extra_artifacts(self) -> None:
        profile = self.profile()
        for repository, index_url in (
            ("pypi", ""),
            ("internal", ""),
            ("testpypi", "https://mirror.example/{name}/{version}"),
        ):
            with self.subTest(repository=repository, index_url=index_url):
                with self.assertRaisesRegex(guard.GuardError, r"(?:repository|indexes)"):
                    guard._assert_publish_policy(
                        SimpleNamespace(repository=repository, index_url=index_url),
                        profile,
                    )
        guard._assert_publish_policy(
            SimpleNamespace(repository="testpypi", index_url=""), profile
        )
        primary = Path("realtimetts_breeze_native-0.1.0.dev1-py3-none-manylinux_2_35_x86_64.whl")
        sdist = Path("realtimetts_breeze_native-0.1.0.dev1.tar.gz")
        windows = Path("realtimetts_breeze_native-0.1.0.dev1-py3-none-win_amd64.whl")
        self.assertEqual(
            guard._publication_artifacts(profile, primary, sdist, [windows]),
            [primary, sdist, windows],
        )

    def test_remote_refs_are_pinned_to_breeze_repository_main(self) -> None:
        profile = self.profile()
        head = "b" * 40
        version = "0.1.0.dev1"
        with (
            mock.patch.object(
                guard,
                "_git",
                return_value=SimpleNamespace(
                    stdout="git@github.com:koljab/realtimetts-breeze-native.git\n"
                ),
            ),
            mock.patch.object(
                guard.subprocess,
                "run",
                return_value=SimpleNamespace(
                    returncode=0,
                    stdout=(
                        f"{head} refs/heads/main\n"
                        f"{head} refs/tags/{version}\n"
                        f"{head} refs/tags/{version}^{{}}\n"
                    ),
                    stderr="",
                ),
            ),
        ):
            result = guard._assert_remote_release_refs(
                Path("."), "origin", "main", version, head, version, profile
            )
        self.assertEqual(
            result["remote"], "github.com/koljab/realtimetts-breeze-native"
        )
        with self.assertRaisesRegex(guard.GuardError, "differs from pinned branch"):
            guard._assert_remote_release_refs(
                Path("."), "origin", "master", version, head, version, profile
            )


class BreezeNativePlatformValidationTests(unittest.TestCase):
    @staticmethod
    def _source(repo: Path) -> list[dict[str, str]]:
        package = repo / "src" / "realtimetts_breeze_native"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("VERSION = 'dev'\n", encoding="utf-8")
        (package / "launcher.py").write_text("def main(): pass\n", encoding="utf-8")
        return [{
            "package_dir": "realtimetts_breeze_native",
            "source_package_dir": "src/realtimetts_breeze_native",
            "runtime_module": "realtimetts_breeze_native",
        }]

    @staticmethod
    def _wheel(
        root: Path,
        platform: str,
        *,
        binary: bytes = b"breeze-worker-binary",
        advertised_binary: bytes | None = None,
        advertised_dependency: bytes | None = None,
        source_override: bytes | None = None,
        omit_dependency: bool = False,
        extra_dependency_entry: bool = False,
    ) -> Path:
        profile = guard.COMPONENT_PROFILES["RealtimeTTSBreezeNativeDev"]
        version = "0.1.0.dev1"
        filename = (
            f"realtimetts_breeze_native-{version}-py3-none-{platform}.whl"
        )
        path = root / filename
        contract = profile["native_build_info"]
        platform_contract = contract["platforms"][platform]
        worker = platform_contract["binary"]
        advertised = binary if advertised_binary is None else advertised_binary
        dependency_name = (
            "breeze-runtime.dll"
            if platform == "win_amd64"
            else "libbreeze-runtime.so"
        )
        dependency = b"runtime-dependency"
        advertised_dependency = (
            dependency if advertised_dependency is None else advertised_dependency
        )
        native_dependencies = [{
            "name": dependency_name,
            "sha256": hashlib.sha256(advertised_dependency).hexdigest(),
        }]
        if extra_dependency_entry:
            stale = b"stale-dependency"
            native_dependencies.append({
                "name": "stale-runtime.so",
                "sha256": hashlib.sha256(stale).hexdigest(),
            })
        info = {
            "format": contract["format"],
            "distribution": contract["distribution"],
            "platform": platform_contract["source_platform"],
            "source_revision": contract["source_revision"],
            "ggml_revision": contract["ggml_revision"],
            "control_patch_sha256": contract["control_patch_sha256"],
            "native_binary": {
                "name": Path(worker).name,
                "sha256": hashlib.sha256(advertised).hexdigest(),
            },
            "native_dependencies": native_dependencies,
            "cmake": contract["cmake"],
        }
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "realtimetts_breeze_native/__init__.py",
                source_override if source_override is not None else "VERSION = 'dev'\n",
            )
            archive.writestr(
                "realtimetts_breeze_native/launcher.py",
                "def main(): pass\n",
            )
            archive.writestr(f"realtimetts_breeze_native/{worker}", binary)
            if not omit_dependency:
                archive.writestr(
                    f"realtimetts_breeze_native/bin/{dependency_name}",
                    dependency,
                )
            archive.writestr(
                "realtimetts_breeze_native/bin/build-info.json",
                json.dumps(info, sort_keys=True),
            )
            archive.writestr(
                f"realtimetts_breeze_native-0.1.0.dev1.dist-info/METADATA",
                "Metadata-Version: 2.1\n"
                "Name: realtimetts-breeze-native\n"
                "Version: 0.1.0.dev1\n",
            )
            archive.writestr(
                f"realtimetts_breeze_native-0.1.0.dev1.dist-info/WHEEL",
                "Wheel-Version: 1.0\n"
                f"Tag: py3-none-{platform}\n",
            )
        return path

    @staticmethod
    def _sdist(root: Path, *, include_native_payload: bool) -> Path:
        path = root / "realtimetts_breeze_native-0.1.0.dev1.tar.gz"
        root_name = "realtimetts_breeze_native-0.1.0.dev1"

        def add(archive: tarfile.TarFile, name: str, data: bytes) -> None:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))

        with tarfile.open(path, "w:gz") as archive:
            add(
                archive,
                f"{root_name}/PKG-INFO",
                b"Name: realtimetts-breeze-native\nVersion: 0.1.0.dev1\n",
            )
            add(
                archive,
                f"{root_name}/src/realtimetts_breeze_native/__init__.py",
                b"VERSION = 'dev'\n",
            )
            add(
                archive,
                f"{root_name}/src/realtimetts_breeze_native/launcher.py",
                b"def main(): pass\n",
            )
            if include_native_payload:
                add(
                    archive,
                    f"{root_name}/src/realtimetts_breeze_native/bin/breeze-server",
                    b"extensionless native worker",
                )
                add(
                    archive,
                    f"{root_name}/src/realtimetts_breeze_native/bin/build-info.json",
                    b"{}",
                )
        return path

    def test_repaired_linux_and_windows_wheels_validate_build_info_and_source_parity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            specs = self._source(root)
            linux = self._wheel(root, "manylinux_2_35_x86_64")
            windows = self._wheel(root, "win_amd64", binary=b"windows-breeze-worker")
            profile = guard.COMPONENT_PROFILES["RealtimeTTSBreezeNativeDev"]
            metadata = guard._wheel_metadata(linux)
            guard._validate_platform_wheels(
                profile, metadata, linux, [windows], root, specs
            )

    def test_native_worker_hash_and_source_changes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            specs = self._source(root)
            linux = self._wheel(
                root,
                "manylinux_2_35_x86_64",
                binary=b"actual",
                advertised_binary=b"staged",
            )
            windows = self._wheel(root, "win_amd64")
            profile = guard.COMPONENT_PROFILES["RealtimeTTSBreezeNativeDev"]
            metadata = guard._wheel_metadata(linux)
            with self.assertRaisesRegex(guard.GuardError, "worker hash"):
                guard._validate_platform_wheels(
                    profile, metadata, linux, [windows], root, specs
                )

            linux = self._wheel(
                root,
                "manylinux_2_35_x86_64",
                source_override="tampered\n",
            )
            with self.assertRaisesRegex(guard.GuardError, "source package"):
                guard._validate_platform_wheels(
                    profile, guard._wheel_metadata(linux), linux, [windows], root, specs
                )

    def test_exact_platform_set_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            specs = self._source(root)
            linux = self._wheel(root, "manylinux_2_35_x86_64")
            profile = guard.COMPONENT_PROFILES["RealtimeTTSBreezeNativeDev"]
            with self.assertRaisesRegex(guard.GuardError, "platform set"):
                guard._validate_platform_wheels(
                    profile, guard._wheel_metadata(linux), linux, [], root, specs
                )

    def test_required_wheel_extras_are_exact_and_wheels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            specs = self._source(root)
            linux = self._wheel(root, "manylinux_2_35_x86_64")
            windows = self._wheel(root, "win_amd64", binary=b"windows-breeze-worker")
            profile = guard.COMPONENT_PROFILES["RealtimeTTSBreezeNativeDev"]
            metadata = guard._wheel_metadata(linux)
            guard._validate_platform_wheels(profile, metadata, linux, [windows], root, specs)

            with self.assertRaisesRegex(guard.GuardError, "duplicate native wheel platform"):
                guard._validate_platform_wheels(profile, metadata, linux, [linux], root, specs)
            with self.assertRaisesRegex(guard.GuardError, "platform set"):
                guard._validate_platform_wheels(profile, metadata, linux, [], root, specs)
            wrong = root / "realtimetts_breeze_native-0.1.0.dev1-py3-none-manylinux_2_35_aarch64.whl"
            wrong.write_bytes(linux.read_bytes())
            with self.assertRaisesRegex(guard.GuardError, "wheel filename platform and internal WHEEL tag"):
                guard._validate_platform_wheels(profile, metadata, linux, [wrong], root, specs)
            with self.assertRaisesRegex(guard.GuardError, "all be wheels"):
                guard._validate_platform_wheels(
                    profile, metadata, linux, [root / "unexpected.tar.gz"], root, specs
                )

    def test_native_dependency_manifest_is_exact_and_hashed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            specs = self._source(root)
            profile = guard.COMPONENT_PROFILES["RealtimeTTSBreezeNativeDev"]
            windows = self._wheel(root, "win_amd64")

            tampered = self._wheel(
                root, "manylinux_2_35_x86_64", advertised_dependency=b"tampered"
            )
            with self.assertRaisesRegex(guard.GuardError, "native dependency hash"):
                guard._validate_platform_wheels(
                    profile, guard._wheel_metadata(tampered), tampered, [windows], root, specs
                )

            omitted = self._wheel(
                root, "manylinux_2_35_x86_64", omit_dependency=True
            )
            with self.assertRaisesRegex(guard.GuardError, "native dependency"):
                guard._validate_platform_wheels(
                    profile, guard._wheel_metadata(omitted), omitted, [windows], root, specs
                )

            stale = self._wheel(
                root, "manylinux_2_35_x86_64", extra_dependency_entry=True
            )
            with self.assertRaisesRegex(guard.GuardError, "native dependency"):
                guard._validate_platform_wheels(
                    profile, guard._wheel_metadata(stale), stale, [windows], root, specs
                )

    def test_sdist_rejects_extensionless_worker_and_build_info(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            specs = self._source(root)
            wheel = self._wheel(root, "manylinux_2_35_x86_64")
            profile = guard.COMPONENT_PROFILES["RealtimeTTSBreezeNativeDev"]
            valid = self._sdist(root, include_native_payload=False)
            guard._validate_package_artifacts(
                root, wheel, valid, specs, None, profile
            )
            invalid = self._sdist(root, include_native_payload=True)
            with self.assertRaisesRegex(guard.GuardError, "forbidden payload"):
                guard._validate_package_artifacts(
                    root, wheel, invalid, specs, None, profile
                )

if __name__ == "__main__":
    unittest.main()
