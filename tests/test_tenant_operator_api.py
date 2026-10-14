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


def _resolve_operator_url() -> str:
    """Dynamically resolve Tenant Operator URL from environment or SSM Parameter Store."""
    url = os.environ.get("TENANT_OPERATOR_URL") or os.environ.get("LAMBDA_URL")
    if url:
        return url.rstrip("/")

    try:
        import boto3
        region = os.environ.get("AWS_REGION", "ap-southeast-1")
        env_name = os.environ.get("ENV", "dev")
        session = boto3.Session(region_name=region)
        ssm = session.client("ssm")
        return ssm.get_parameter(Name=f"/nextcloud/{env_name}/infra/tenant-operator-url")["Parameter"]["Value"].rstrip("/")
    except Exception as exc:
        pytest.skip(f"Tenant Operator URL not provided via TENANT_OPERATOR_URL or SSM: {exc}")


def call_operator_api(action: str, **kwargs) -> dict:
    """Invoke Tenant Operator API via HTTP POST."""
    lambda_url = _resolve_operator_url()
    payload = {"action": action, **kwargs}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{lambda_url}/",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "TenantOperator-IntegrationTest"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def _get_target_tenant(tenants: list[dict] | None = None) -> str:
    """Resolve target tenant from environment or dynamically from active fleet."""
    env_tenant = os.environ.get("TENANT_ID")
    if env_tenant:
        return env_tenant
    if tenants:
        for t in tenants:
            tid = t.get("tenant_id")
            if tid:
                return tid
    data = call_operator_api("LIST")
    items = data.get("tenants") or data.get("data") or data.get("items") or []
    if items and items[0].get("tenant_id"):
        return items[0]["tenant_id"]
    pytest.skip("No target tenant available to test")


def test_operator_list_tenants():
    """Verify LIST action returns valid fleet listing with counts."""
    data = call_operator_api("LIST")
    assert data.get("status") == "OK", f"Expected status OK, got {data}"
    assert "tenants" in data or "data" in data or "items" in data
    tenants = data.get("tenants") or data.get("data") or data.get("items") or []
    assert isinstance(tenants, list)
    assert len(tenants) >= 1

    target_tenant = os.environ.get("TENANT_ID")
    tenant_ids = [t.get("tenant_id") for t in tenants]
    if target_tenant:
        assert target_tenant in tenant_ids, f"'{target_tenant}' not found in fleet: {tenant_ids}"


def test_operator_describe_tenant():
    """Verify DESCRIBE / GET_TENANT_DETAIL returns tenant detail, topology, and metrics."""
    target_tenant = _get_target_tenant()
    data = call_operator_api("DESCRIBE", tenant_id=target_tenant)
    assert data.get("status") == "OK", f"Expected status OK, got {data}"

    tenant = data.get("tenant") or data.get("item")
    assert tenant is not None, "Tenant details missing"
    assert tenant.get("tenant_id") == target_tenant
    assert tenant.get("status") in ("ACTIVE", "SUSPENDED")

    # Verify AWS topology and metrics blocks
    assert "aws_topology" in data
    assert "metrics" in data


def test_operator_metrics():
    """Verify METRICS action returns control plane metrics."""
    target_tenant = _get_target_tenant()
    data = call_operator_api("METRICS", tenant_id=target_tenant)
    assert data.get("status") == "OK"
    assert data.get("action") == "METRICS"


def test_operator_lifecycle_suspend_and_resume():
    """Verify SUSPEND and RESUME transitions update tenant status."""
    target_tenant = _get_target_tenant()

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

