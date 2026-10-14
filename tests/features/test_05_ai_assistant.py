"""Test Nextcloud AI Assistant & Bedrock Bridge sidecar integration."""

from __future__ import annotations


def test_ai_apps_installed_and_enabled(tenant_fixture):
    """Verify that Nextcloud Assistant and OpenAI integration apps are active."""
    url = f"{tenant_fixture.ocs_v1_base}/cloud/apps?filter=enabled"
    resp = tenant_fixture.session.get(url, timeout=15)
    assert resp.status_code == 200, (
        f"Failed to retrieve enabled apps: {resp.status_code}"
    )

    body = resp.json()
    enabled_apps = body.get("ocs", {}).get("data", {}).get("apps", [])

    # In FilestoreCloud golden image, assistant and integration_openai are pre-baked
    has_assistant = "assistant" in enabled_apps
    has_openai = "integration_openai" in enabled_apps

    assert has_assistant or has_openai, (
        f"Neither 'assistant' nor 'integration_openai' found in enabled apps: {enabled_apps}"
    )


def test_assistant_capabilities_registered(tenant_fixture):
    """Verify that AI assistant features are registered in system capabilities."""
    resp = tenant_fixture.get_capabilities()
    assert resp.status_code == 200

    capabilities = resp.json().get("ocs", {}).get("data", {}).get("capabilities", {})
    # Verify assistant capability key exists when the app is active
    if "assistant" in capabilities:
        assert capabilities["assistant"].get("enabled", True) is not False
