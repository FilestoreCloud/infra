"""Test Nextcloud core system status, versions, and OCS capabilities."""

from __future__ import annotations


def test_nextcloud_public_status(tenant_fixture):
    """Verify that /status.php returns HTTP 200 with installed=true and valid version."""
    resp = tenant_fixture.get_status()
    assert resp.status_code == 200, (
        f"Expected 200 from status.php, got {resp.status_code}"
    )

    data = resp.json()
    assert data.get("installed") is True, (
        "Nextcloud instance must be marked as installed"
    )
    assert data.get("maintenance") is False, (
        "Nextcloud instance should not be in maintenance mode"
    )
    version = data.get("version", "")
    assert version.startswith("30."), (
        f"Expected Nextcloud major version 30, got {version}"
    )


def test_nextcloud_ocs_capabilities(tenant_fixture):
    """Verify core capabilities via OCS Capabilities API."""
    resp = tenant_fixture.get_capabilities()
    assert resp.status_code == 200, (
        f"OCS Capabilities failed with status {resp.status_code}"
    )

    json_body = resp.json()
    assert "ocs" in json_body
    capabilities = json_body["ocs"]["data"]["capabilities"]

    # 1. Verify Core Capabilities
    assert "core" in capabilities, "Core capabilities missing"
    assert capabilities["core"]["status"]["installed"] is True

    # 2. Verify Files Capabilities
    assert "files" in capabilities, "Files capabilities missing"
    assert capabilities["files"]["bigfilechunking"] is True

    # 3. Verify Files Sharing Capabilities
    assert "files_sharing" in capabilities, "Files sharing capability missing"
    assert capabilities["files_sharing"]["api_enabled"] is True
    assert capabilities["files_sharing"]["public"]["enabled"] is True
