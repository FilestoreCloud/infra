"""Test Nextcloud AI Assistant & Bedrock Bridge sidecar integration."""

from __future__ import annotations

import os

import pytest
import requests


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
    assert resp.status_code == 200, (
        f"Failed to retrieve capabilities: {resp.status_code}"
    )

    capabilities = resp.json().get("ocs", {}).get("data", {}).get("capabilities", {})

    # Strict assertion: AI capabilities must be registered (eliminating shallow bypass)
    has_ai_capability = "assistant" in capabilities or "text_processing" in capabilities
    assert has_ai_capability, (
        f"Neither 'assistant' nor 'text_processing' found in capabilities: {list(capabilities.keys())}"
    )

    if "assistant" in capabilities:
        assert capabilities["assistant"].get("enabled", True) is not False
    if "text_processing" in capabilities:
        assert capabilities["text_processing"] is not None


def test_bedrock_bridge_active_inference():
    """Execute active inference query against Bedrock Bridge sidecar.

    Validates HTTP 200 response and non-empty LLM completion from Claude 3.5 Sonnet
    via the LiteLLM container on port 4000.
    """
    raw_url = (
        os.environ.get("AI_BRIDGE_URL")
        or os.environ.get("AI_API_URL")
        or os.environ.get("LITELLM_ENDPOINT")
        or "http://127.0.0.1:4000/v1"
    ).rstrip("/")

    if raw_url.endswith("/chat/completions"):
        endpoint = raw_url
    elif raw_url.endswith("/v1"):
        endpoint = f"{raw_url}/chat/completions"
    else:
        endpoint = f"{raw_url}/v1/chat/completions"

    model = os.environ.get("BEDROCK_MODEL_ID", "claude-3-5-sonnet")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Hello! Confirm assistant is operational in one sentence.",
            }
        ],
        "max_tokens": 100,
    }

    headers = {
        "Content-Type": "application/json",
    }
    api_key = (
        os.environ.get("AI_BRIDGE_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or "sk-storix-test"
    )
    headers["Authorization"] = f"Bearer {api_key}"

    timeout = float(os.environ.get("AI_BRIDGE_TIMEOUT", "30.0"))

    try:
        resp = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        pytest.skip(f"AI sidecar bridge not reachable at {endpoint}: {exc}")

    assert resp.status_code == 200, (
        f"AI sidecar bridge returned HTTP {resp.status_code}: {resp.text}"
    )

    body = resp.json()
    assert "choices" in body, f"Response JSON missing 'choices' key: {body}"
    choices = body.get("choices", [])
    assert len(choices) > 0, f"Response 'choices' array is empty: {body}"

    first_choice = choices[0]
    message = first_choice.get("message", {})
    completion_text = message.get("content", "")

    if isinstance(completion_text, list):
        # Support structured content block payloads if returned
        completion_text = "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in completion_text
        )

    assert isinstance(completion_text, str), (
        f"Completion content is not a string: {type(completion_text)}"
    )
    assert len(completion_text.strip()) > 0, (
        f"AI sidecar bridge returned empty completion content: {body}"
    )
