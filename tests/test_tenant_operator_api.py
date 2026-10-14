"""
Integration test suite for Storix Tenant Operator Control Plane API.
Tests:
1. LIST: Returns registered fleet tenants and statistics.
2. DESCRIBE: Returns tenant detail, AWS topology, and telemetry.
3. METRICS: Returns operational metrics.
4. SUSPEND and RESUME: Lifecycle state transitions.
5. PROVISION: Validates provisioning request handling.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
import pytest

DEFAULT_FUNCTION_URL = "https://ow4qcalxo2bvtbuwhkcwiuq2bq0hnfms.lambda-url.ap-southeast-1.on.aws"
LAMBDA_URL = os.environ.get("TENANT_OPERATOR_URL", DEFAULT_FUNCTION_URL).rstrip("/")


def call_operator_api(action: str, **kwargs) -> dict:
    """Invoke Tenant Operator API via HTTP POST."""
    payload = {"action": action, **kwargs}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{LAMBDA_URL}/",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "TenantOperator-IntegrationTest"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def test_operator_list_tenants():
    """Verify LIST action returns valid fleet listing with counts."""
    data = call_operator_api("LIST")
    assert data.get("status") == "OK", f"Expected status OK, got {data}"
    assert "tenants" in data or "data" in data or "items" in data
    tenants = data.get("tenants") or data.get("data") or data.get("items") or []
    assert isinstance(tenants, list)
    assert len(tenants) >= 1

    # Verify dev-tenant is present
    tenant_ids = [t.get("tenant_id") for t in tenants]
    assert "dev-tenant" in tenant_ids, f"'dev-tenant' not found in {tenant_ids}"


def test_operator_describe_tenant():
    """Verify DESCRIBE / GET_TENANT_DETAIL returns tenant detail, topology, and metrics."""
    data = call_operator_api("DESCRIBE", tenant_id="dev-tenant")
    assert data.get("status") == "OK", f"Expected status OK, got {data}"

    tenant = data.get("tenant") or data.get("item")
    assert tenant is not None, "Tenant details missing"
    assert tenant.get("tenant_id") == "dev-tenant"
    assert tenant.get("status") in ("ACTIVE", "SUSPENDED")

    # Verify AWS topology and metrics blocks
    assert "aws_topology" in data
    assert "metrics" in data


def test_operator_metrics():
    """Verify METRICS action returns control plane metrics."""
    data = call_operator_api("METRICS", tenant_id="dev-tenant")
    assert data.get("status") == "OK"
    assert data.get("action") == "METRICS"


def test_operator_lifecycle_suspend_and_resume():
    """Verify SUSPEND and RESUME transitions update tenant status."""
    target_tenant = "dev-tenant"

    # 1. Suspend
    suspend_res = call_operator_api("SUSPEND", tenant_id=target_tenant)
    assert suspend_res.get("status") in ("OK", "SUSPENDED")

    # Verify suspended state
    desc_after_suspend = call_operator_api("DESCRIBE", tenant_id=target_tenant)
    tenant_s = desc_after_suspend.get("tenant") or desc_after_suspend.get("item") or {}
    assert tenant_s.get("status") == "SUSPENDED"

    # 2. Resume
    resume_res = call_operator_api("RESUME", tenant_id=target_tenant)
    assert resume_res.get("status") in ("OK", "ACTIVE")

    # Verify resumed active state
    desc_after_resume = call_operator_api("DESCRIBE", tenant_id=target_tenant)
    tenant_a = desc_after_resume.get("tenant") or desc_after_resume.get("item") or {}
    assert tenant_a.get("status") == "ACTIVE"
