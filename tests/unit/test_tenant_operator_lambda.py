"""Unit Test Suite for Storix SuperAdmin Tenant Operator Lambda.
Validates authentication, MFA, fail-closed security, RBAC, metric safety,
and Step Functions task dispatching using isolated mocks.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure test AWS environment before importing lambda module
os.environ["AWS_ACCESS_KEY_ID"] = "mock_key"
os.environ["AWS_SECRET_ACCESS_KEY"] = "mock_secret"
os.environ["AWS_DEFAULT_REGION"] = "ap-southeast-1"
os.environ["AWS_REGION"] = "ap-southeast-1"
os.environ["ENVIRONMENT_NAME"] = "test"
os.environ["TABLE_NAME"] = "test-nextcloud-tenant-registry"
os.environ["ADMIN_USERS_TABLE"] = "test-nextcloud-admin-users"
os.environ["AUDIT_LOGS_TABLE"] = "test-nextcloud-audit-logs"

# Add lambda directory to sys.path
LAMBDA_DIR = Path(__file__).resolve().parents[2] / "modules" / "06-superadmin"
if not LAMBDA_DIR.exists():
    LAMBDA_DIR = Path(__file__).resolve().parents[2] / "infra" / "modules" / "06-superadmin"
sys.path.insert(0, str(LAMBDA_DIR))

import tenant_operator_lambda as tol  # noqa: E402


class TestTenantOperatorLambdaUnit(unittest.TestCase):
    """Unit test cases for tenant_operator_lambda.py."""

    def setUp(self):
        self.mock_signing_key = "test-signing-key-1234567890123456"

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Metric Safety & Recursion Prevention
    # ──────────────────────────────────────────────────────────────────────────
    def test_safe_put_metric_data_success(self):
        """Verify safe_put_metric_data safely delegates to CloudWatch client."""
        with patch.object(tol.cloudwatch, "put_metric_data") as mock_put:
            tol.safe_put_metric_data(
                Namespace="Storix/Test",
                MetricData=[{"MetricName": "TestMetric", "Value": 1.0}],
            )
            mock_put.assert_called_once_with(
                Namespace="Storix/Test",
                MetricData=[{"MetricName": "TestMetric", "Value": 1.0}],
            )

    def test_safe_put_metric_data_suppresses_exception(self):
        """Verify safe_put_metric_data never crashes or recurses on CloudWatch error."""
        with patch.object(tol.cloudwatch, "put_metric_data", side_effect=Exception("AWS Throttled")):
            # Should not raise exception
            try:
                tol.safe_put_metric_data(
                    Namespace="Storix/Test",
                    MetricData=[{"MetricName": "TestMetric", "Value": 1.0}],
                )
            except Exception as exc:
                self.fail(f"safe_put_metric_data raised unexpected exception: {exc}")

    # ──────────────────────────────────────────────────────────────────────────
    # 2. RBAC Permission Matrix
    # ──────────────────────────────────────────────────────────────────────────
    def test_rbac_superadmin_full_access(self):
        """Verify SuperAdmin role has wildcard authorization across all operations."""
        self.assertTrue(tol.check_rbac_permission("SuperAdmin", "PROVISION_TENANT"))
        self.assertTrue(tol.check_rbac_permission("SuperAdmin", "SUSPEND_TENANT"))
        self.assertTrue(tol.check_rbac_permission("SuperAdmin", "EXECUTE_OCC_COMMAND"))
        self.assertTrue(tol.check_rbac_permission("SuperAdmin", "ANY_CUSTOM_ACTION"))

    def test_rbac_unknown_role_rejected(self):
        """Verify unauthorized roles cannot execute sensitive administrative operations."""
        self.assertFalse(tol.check_rbac_permission("Guest", "PROVISION_TENANT"))
        self.assertFalse(tol.check_rbac_permission("ReadOnly", "DELETE_TENANT"))
        self.assertFalse(tol.check_rbac_permission(None, "LOGIN"))

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Session Token Creation & Verification
    # ──────────────────────────────────────────────────────────────────────────
    def test_session_token_creation_and_verification(self):
        """Verify session token is properly signed, contains RBAC claims, and verifies cleanly."""
        token = tol.create_session_token(
            username="superadmin",
            role="SuperAdmin",
            key=self.mock_signing_key,
        )
        self.assertIn(".", token)
        payload = tol.verify_session_token(token, key=self.mock_signing_key)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["user"], "superadmin")
        self.assertEqual(payload["role"], "SuperAdmin")
        self.assertTrue(payload["mfa"])
        self.assertGreater(payload["exp"], time.time())

    def test_session_token_tampered_signature_rejected(self):
        """Verify tampered session tokens fail verification."""
        token = tol.create_session_token(
            username="superadmin",
            role="SuperAdmin",
            key=self.mock_signing_key,
        )
        payload_b64, sig = token.split(".", 1)
        tampered_sig = sig[:-4] + "0000"
        tampered_token = f"{payload_b64}.{tampered_sig}"
        self.assertIsNone(tol.verify_session_token(tampered_token, key=self.mock_signing_key))

    def test_session_token_wrong_key_rejected(self):
        """Verify session token signed with different key is rejected."""
        token = tol.create_session_token(
            username="superadmin",
            role="SuperAdmin",
            key=self.mock_signing_key,
        )
        self.assertIsNone(tol.verify_session_token(token, key="different-key-99999999999"))

    def test_session_token_expired_rejected(self):
        """Verify expired session token is rejected."""
        expired_payload = {
            "user": "superadmin",
            "role": "SuperAdmin",
            "exp": int(time.time()) - 100,  # Expired
        }
        p_bytes = json.dumps(expired_payload, separators=(",", ":")).encode("utf-8")
        p_b64 = base64.urlsafe_b64encode(p_bytes).decode("ascii").rstrip("=")
        sig = hmac.new(
            self.mock_signing_key.encode("utf-8"),
            p_b64.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        expired_token = f"{p_b64}.{sig}"
        self.assertIsNone(tol.verify_session_token(expired_token, key=self.mock_signing_key))

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Challenge Token & MFA Security
    # ──────────────────────────────────────────────────────────────────────────
    def test_challenge_token_hashes_otp_and_does_not_leak_plaintext(self):
        """Verify MFA challenge token stores SHA256 of OTP code, never plaintext."""
        raw_otp = "491823"
        token = tol.create_challenge_token(
            username="operator",
            role="SuperAdmin",
            otp_code=raw_otp,
            key=self.mock_signing_key,
        )
        payload_b64 = token.split(".", 1)[0]
        padding = 4 - (len(payload_b64) % 4)
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode("ascii")).decode("utf-8"))

        self.assertNotIn("otp_code", payload)
        self.assertNotIn(raw_otp, json.dumps(payload))
        expected_hash = hashlib.sha256(raw_otp.encode()).hexdigest()
        self.assertEqual(payload.get("otp_hash"), expected_hash)
        self.assertEqual(payload.get("type"), "mfa_challenge")

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Fail-Closed Behavior
    # ──────────────────────────────────────────────────────────────────────────
    def test_fail_closed_when_signing_keys_unavailable(self):
        """Verify create_session_token raises RuntimeError and handler returns HTTP 503."""
        with patch.object(tol, "get_signing_key", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                tol.create_session_token("admin", "SuperAdmin")
            self.assertIn("Fail-closed", str(ctx.exception))

            # Test lambda_handler returns 503
            http_event = {
                "httpMethod": "POST",
                "headers": {"content-type": "application/json"},
                "body": json.dumps({"action": "LOGIN"}),
            }
            with patch.object(tol, "_handle_request", side_effect=RuntimeError("Authentication service signing keys unavailable. Fail-closed.")):
                resp = tol.lambda_handler(http_event, None)
                self.assertEqual(resp["statusCode"], 503)
                body = json.dumps(resp["body"]) if isinstance(resp["body"], dict) else resp["body"]
                self.assertIn("Fail-closed", body)

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Step Functions Task Handling
    # ──────────────────────────────────────────────────────────────────────────
    def test_step_functions_task_dispatch(self):
        """Verify Step Functions direct tasks route and return structured status."""
        event = {"action": "SEED_ADMIN_USERS", "tenant_id": "tenant-unit-test"}
        res = tol.lambda_handler(event, None)
        self.assertEqual(res.get("status"), "ADMIN_USERS_SEEDED")
        self.assertEqual(res.get("tenant_id"), "tenant-unit-test")
        self.assertTrue(res.get("seeded"))


if __name__ == "__main__":
    unittest.main()
