import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts directory is in sys.path
SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import rollout_tenant_image as rti


@pytest.fixture
def sample_tenants():
    return [
        {
            "tenant_id": "system-canary",
            "ring": 0,
            "release_channel": "CANARY",
            "target_group_arn": "arn:aws:elasticloadbalancing:tg-canary",
            "domain": "canary.png261.dev",
            "service_name": "service-system-canary",
        },
        {
            "tenant_id": "beta-customer-1",
            "ring": 1,
            "release_channel": "BETA",
            "target_group_arn": "arn:aws:elasticloadbalancing:tg-beta1",
            "domain": "beta1.png261.dev",
            "service_name": "service-beta-customer-1",
        },
        {
            "tenant_id": "beta-customer-2",
            "ring": 1,
            "release_channel": "BETA",
            "target_group_arn": "arn:aws:elasticloadbalancing:tg-beta2",
            "domain": "beta2.png261.dev",
            "service_name": "service-beta-customer-2",
        },
        {
            "tenant_id": "vip-enterprise-corp",
            "ring": 2,
            "release_channel": "STABLE",
            "target_group_arn": "arn:aws:elasticloadbalancing:tg-vip",
            "domain": "vip.png261.dev",
            "service_name": "service-vip-enterprise-corp",
        },
    ]


def test_filter_tenants_patch(sample_tenants):
    """PATCH release type must include 100% of tenants across all rings."""
    filtered = rti.filter_tenants_by_release_type(sample_tenants, "PATCH")
    assert len(filtered) == 4
    tenant_ids = [t["tenant_id"] for t in filtered]
    assert "system-canary" in tenant_ids
    assert "vip-enterprise-corp" in tenant_ids


def test_filter_tenants_beta(sample_tenants):
    """BETA release type must strictly exclude Ring 2 VIP/Stable customers."""
    filtered = rti.filter_tenants_by_release_type(sample_tenants, "BETA")
    assert len(filtered) == 3
    tenant_ids = [t["tenant_id"] for t in filtered]
    assert "system-canary" in tenant_ids
    assert "beta-customer-1" in tenant_ids
    assert "beta-customer-2" in tenant_ids
    assert "vip-enterprise-corp" not in tenant_ids


def test_filter_tenants_breakthrough_phased(sample_tenants):
    """BREAKTHROUGH release must allow staged execution."""
    stage1 = rti.filter_tenants_by_release_type(
        sample_tenants, "BREAKTHROUGH", stage="CANARY_AND_BETA"
    )
    assert len(stage1) == 3
    assert "vip-enterprise-corp" not in [t["tenant_id"] for t in stage1]

    stage2 = rti.filter_tenants_by_release_type(
        sample_tenants, "BREAKTHROUGH", stage="VIP_ONLY"
    )
    assert len(stage2) == 1
    assert stage2[0]["tenant_id"] == "vip-enterprise-corp"


def test_tag_classifier_logic():
    """Verify regex logic used in CI/CD pipeline correctly categorizes tags."""

    def classify_tag(tag: str) -> str:
        tag_lower = tag.lower()
        if "patch" in tag_lower or "hotfix" in tag_lower:
            return "PATCH"
        elif any(k in tag_lower for k in ["beta", "rc", "preview"]):
            return "BETA"
        return "BREAKTHROUGH"

    assert classify_tag("v30.0.17-patch.1") == "PATCH"
    assert classify_tag("v30.0.17-hotfix.20261012") == "PATCH"
    assert classify_tag("v30.0.18-beta.1") == "BETA"
    assert classify_tag("v31.0.0-rc2") == "BETA"
    assert classify_tag("v31.0.0") == "BREAKTHROUGH"
    assert classify_tag("v31.0.0-ga") == "BREAKTHROUGH"


def test_deploy_single_tenant_dry_run():
    """Verify deploy_single_tenant dry-run executes cleanly with zero AWS mutation."""
    mock_session = MagicMock()
    tenant = {
        "tenant_id": "test-tenant",
        "service_name": "service-test-tenant",
        "target_group_arn": "arn:aws:tg:123",
        "domain": "test.png261.dev",
    }
    success, msg = rti.deploy_single_tenant(
        session=mock_session,
        cluster_name="test-cluster",
        tenant=tenant,
        new_image="nextcloud:30.0.18",
        dry_run=True,
    )
    assert success is True
    assert "[DRY-RUN]" in msg


@patch("rollout_tenant_image.get_active_tenants")
def test_fleet_rollout_dry_run_success(mock_get_tenants, sample_tenants):
    """Verify fleet rollout in dry-run mode completes successfully."""
    mock_get_tenants.return_value = sample_tenants
    mock_session = MagicMock()

    with patch("rollout_tenant_image.get_boto3_session", return_value=mock_session):
        success = rti.run_fleet_rollout(
            new_image="nextcloud:30.0.18-patch.1",
            release_type="PATCH",
            canary_id="system-canary",
            concurrency=2,
            soak_seconds=0,
            dry_run=True,
        )
        assert success is True


@patch("rollout_tenant_image.get_active_tenants")
@patch("rollout_tenant_image.deploy_single_tenant")
def test_fleet_rollout_canary_failure_aborts(
    mock_deploy, mock_get_tenants, sample_tenants
):
    """Verify that when Canary fails, the entire fleet rollout is halted immediately."""
    mock_get_tenants.return_value = sample_tenants
    # Canary fails
    mock_deploy.return_value = (False, "Container health check timed out")
    mock_session = MagicMock()

    with patch("rollout_tenant_image.get_boto3_session", return_value=mock_session):
        success = rti.run_fleet_rollout(
            new_image="nextcloud:bad-image",
            release_type="PATCH",
            canary_id="system-canary",
            concurrency=2,
            soak_seconds=0,
            dry_run=False,
        )
        assert success is False
        # deploy_single_tenant should only be called once (for the Canary), not for remaining tenants
        assert mock_deploy.call_count == 1
