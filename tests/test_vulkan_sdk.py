from __future__ import annotations

import hashlib
import io
from pathlib import Path

from tools import install_vulkan_sdk


def test_lunar_g_sdk_inputs_are_pinned_for_both_ci_platforms(tmp_path: Path):
    assert install_vulkan_sdk.VERSION == "1.3.296.0"
    assert install_vulkan_sdk.LINUX_URL.endswith("?Human=true")
    assert install_vulkan_sdk.WINDOWS_URL.endswith("?Human=true")
    assert install_vulkan_sdk.linux_sdk_path(tmp_path).parts[-2:] == (
        install_vulkan_sdk.VERSION,
        "x86_64",
    )
    assert len(install_vulkan_sdk.LINUX_SHA256) == 64
    assert len(install_vulkan_sdk.WINDOWS_SHA256) == 64


def test_download_uses_non_python_user_agent_and_verifies_payload(
    tmp_path: Path, monkeypatch
):
    payload = b"pinned sdk payload"
    request_seen = {}

    def fake_urlopen(request, timeout):
        request_seen["request"] = request
        request_seen["timeout"] = timeout
        return io.BytesIO(payload)

    monkeypatch.setattr(install_vulkan_sdk.urllib.request, "urlopen", fake_urlopen)
    destination = tmp_path / "sdk.bin"
    install_vulkan_sdk.download_verified(
        "https://example.invalid/sdk.bin",
        destination,
        hashlib.sha256(payload).hexdigest(),
    )
    assert destination.read_bytes() == payload
    assert request_seen["timeout"] == 120
    assert request_seen["request"].get_header("User-agent") == install_vulkan_sdk.USER_AGENT
    assert "Python" not in install_vulkan_sdk.USER_AGENT
