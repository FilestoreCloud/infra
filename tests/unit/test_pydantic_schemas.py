"""
Unit Tests for Pydantic Contract and Model Validation.
"""
import sys
import unittest
from pathlib import Path

# Add lambda directory to sys.path
LAMBDA_DIR = Path(__file__).resolve().parents[2] / "modules" / "06-superadmin"
if not LAMBDA_DIR.exists():
    LAMBDA_DIR = Path(__file__).resolve().parents[2] / "infra" / "modules" / "06-superadmin"
sys.path.insert(0, str(LAMBDA_DIR))

from pydantic import ValidationError  # noqa: E402
from operator_core.schemas import (  # noqa: E402
    AuditLogEvent,
    SessionTokenClaims,
    TenantRecord,
    TenantStatus,
)


class TestPydanticSchemas(unittest.TestCase):
    def test_valid_tenant_record(self):
        tenant = TenantRecord(
            tenant_id="enterprise-tenant",
            domain="enterprise.storix.io",
            status=TenantStatus.ACTIVE,
            quota_gb=500,
            admin_email="admin@enterprise.com",
        )
        self.assertEqual(tenant.tenant_id, "enterprise-tenant")
        self.assertEqual(tenant.quota_gb, 500)
        self.assertEqual(tenant.status, TenantStatus.ACTIVE)

    def test_invalid_tenant_id_regex(self):
        with self.assertRaises(ValidationError):
            TenantRecord(
                tenant_id="INVALID_UPPERCASE",
                domain="invalid.storix.io",
                quota_gb=100,
            )

    def test_bare_wildcard_rejected_by_validator(self):
        with self.assertRaises(ValidationError) as ctx:
            TenantRecord(
                tenant_id="tenant-wildcard",
                domain="*",
                quota_gb=100,
            )
        self.assertIn("Bare wildcard '*' is strictly forbidden", str(ctx.exception))

    def test_negative_quota_rejected(self):
        with self.assertRaises(ValidationError):
            TenantRecord(
                tenant_id="tenant-neg",
                domain="neg.storix.io",
                quota_gb=0,  # ge=1 constraint
            )

    def test_audit_log_event_validation(self):
        event = AuditLogEvent(
            event_id="evt-101",
            timestamp="2026-10-16T10:00:00Z",
            actor="sec-admin",
            role="SuperAdmin",
            action="SUSPEND_TENANT",
            status="SUCCESS",
        )
        self.assertEqual(event.status, "SUCCESS")

        with self.assertRaises(ValidationError):
            AuditLogEvent(
                event_id="evt-102",
                timestamp="2026-10-16T10:00:00Z",
                actor="sec-admin",
                role="SuperAdmin",
                action="SUSPEND_TENANT",
                status="INVALID_STATUS",  # must match SUCCESS|DENIED|FAILED
            )

    def test_session_token_claims_validation(self):
        claims = SessionTokenClaims(
            user="operator@storix.io",
            sub="operator@storix.io",
            role="Operator",
            mfa=True,
            exp=1700000000,
            nonce="abcdef123456",
        )
        self.assertTrue(claims.mfa)
        self.assertEqual(claims.role, "Operator")


if __name__ == "__main__":
    unittest.main()
