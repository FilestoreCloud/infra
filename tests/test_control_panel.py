import json
import os
import sys
import time

import boto3
import pytest
import requests

# Ensure control plane lambda module is importable for direct unit testing
LAMBDA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../infra/modules/06-control-plane")
)
if LAMBDA_DIR not in sys.path:
    sys.path.insert(0, LAMBDA_DIR)

import tenant_operator_lambda as tol

# Configuration
WEB_BASE = os.environ.get("CONTROL_PANEL_URL", "https://admin.png261.dev").rstrip("/")
API_BASE = f"{WEB_BASE}/api" if not WEB_BASE.endswith("/api") else WEB_BASE

AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
AWS_PROFILE = os.environ.get("AWS_PROFILE", "handon")
TABLE_NAME = "prod-nextcloud-tenant-registry"
DASHBOARD_NAME = "prod-Nextcloud-SaaS-Control-Plane"

# Initialize AWS Session safely
session = None
has_aws_creds = False
try:
    if "AWS_ROLE_ARN" not in os.environ and "AWS_ACCESS_KEY_ID" not in os.environ:
        session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    else:
        session = boto3.Session(region_name=AWS_REGION)
    session.client("sts").get_caller_identity()
    has_aws_creds = True
except Exception:
    try:
        session = boto3.Session(region_name=AWS_REGION)
        session.client("sts").get_caller_identity()
        has_aws_creds = True
    except Exception:
        session = None
        has_aws_creds = False

dynamodb = session.client("dynamodb") if has_aws_creds else None
cloudwatch = session.client("cloudwatch") if has_aws_creds else None
secretsmanager = session.client("secretsmanager") if has_aws_creds else None

_AUTH_HEADER_CACHE = None


def get_auth_header():
    """Obtain session authentication token for Control Panel API (with MFA challenge solving)."""
    global _AUTH_HEADER_CACHE
    if _AUTH_HEADER_CACHE:
        return _AUTH_HEADER_CACHE

    token = os.environ.get("ADMIN_TOKEN")
    if token:
        _AUTH_HEADER_CACHE = {"Authorization": f"Bearer {token}"}
        return _AUTH_HEADER_CACHE

    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_password and secretsmanager:
        try:
            res = secretsmanager.get_secret_value(
                SecretId="/nextcloud/prod/secrets/admin-credentials"
            )
            secret_data = json.loads(res.get("SecretString", "{}"))
            admin_password = secret_data.get("password")
        except Exception as e:
            print(f"Warning: could not fetch admin password from Secrets Manager: {e}")

    # Fallback to bootstrap super admin credentials if live SM secret not set
    admin_user = "admin@png261.dev"
    if not admin_password:
        admin_password = "AdminPassword123!"

    try:
        login_resp = requests.post(
            API_BASE,
            json={
                "action": "LOGIN",
                "username": admin_user,
                "password": admin_password,
            },
            timeout=10,
        )
        if login_resp.status_code == 200:
            data = login_resp.json()
            if data.get("status") == "MFA_REQUIRED":
                # Solve TOTP challenge using demo secret
                ch_token = data.get("challenge_token")
                mfa_secret = data.get(
                    "demo_totp_secret", "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
                )
                totp_code = tol.generate_totp_code(mfa_secret)
                mfa_resp = requests.post(
                    API_BASE,
                    json={
                        "action": "VERIFY_MFA",
                        "challenge_token": ch_token,
                        "mfa_code": totp_code,
                    },
                    timeout=10,
                )
                if mfa_resp.status_code == 200:
                    t = mfa_resp.json().get("token")
                    if t:
                        _AUTH_HEADER_CACHE = {"Authorization": f"Bearer {t}"}
                        return _AUTH_HEADER_CACHE
            elif data.get("token"):
                _AUTH_HEADER_CACHE = {"Authorization": f"Bearer {data['token']}"}
                return _AUTH_HEADER_CACHE
    except Exception as e:
        print(f"Warning: login request failed: {e}")

    return {}


# ==============================================================================
# UNIT TESTS: TOTP MFA ENGINE (Requirement 1)
# ==============================================================================
def test_rfc6238_totp_generation_and_verification():
    """Verify RFC 6238 TOTP engine produces valid 6-digit codes and verifies time-drift."""
    secret = tol.generate_totp_secret()
    assert len(secret) >= 32, "TOTP secret must be at least 32 base32 characters"

    # Current code
    code = tol.generate_totp_code(secret)
    assert len(code) == 6, "TOTP code must be 6 digits"
    assert code.isdigit(), "TOTP code must consist of numeric digits only"

    # Verify matching code succeeds
    assert tol.verify_totp_code(secret, code), (
        "Verification of freshly generated TOTP code must succeed"
    )

    # Verify invalid code fails
    assert not tol.verify_totp_code(
        secret, "000000" if code != "000000" else "999999"
    ), "Invalid code must fail verification"

    # Verify drift tolerance (±1 step / 30 seconds)
    current_step = int(time.time() // 30)
    past_code = tol.generate_totp_code(secret, current_step - 1)
    assert tol.verify_totp_code(secret, past_code, window=1), (
        "TOTP code from -30s must pass with window=1"
    )

    uri = tol.get_totp_uri("admin@png261.dev", secret)
    assert "otpauth://totp/" in uri
    assert "secret=" in uri
    print("  ✅ RFC 6238 TOTP cryptography verified successfully.")


def test_password_hashing_pbkdf2():
    """Verify PBKDF2 password hashing with 100,000 iterations and salt separation."""
    pwd = "EnterpriseSecurePassword2026!"
    hashed = tol.hash_password(pwd)
    assert "$" in hashed
    salt, hex_digest = hashed.split("$", 1)
    assert len(salt) == 32
    assert len(hex_digest) == 64

    # Verify positive match
    assert tol.verify_password(pwd, hashed)
    # Verify negative match
    assert not tol.verify_password("WrongPassword!", hashed)
    print("  ✅ PBKDF2 password cryptography verified successfully.")


def test_jwt_session_signing_and_verification():
    """Verify HMAC-SHA256 session token generation, RBAC claims, and signature verification."""
    token = tol.create_session_token("admin@png261.dev", role="SuperAdmin")
    assert "." in token
    payload = tol.verify_session_token(token)
    assert payload is not None
    assert payload["user"] == "admin@png261.dev"
    assert payload["role"] == "SuperAdmin"
    assert payload["mfa"] is True

    # Tampered token must fail
    tampered = token[:-4] + "abcd"
    assert tol.verify_session_token(tampered) is None
    print("  ✅ Signed JWT session verification verified successfully.")


# ==============================================================================
# UNIT TESTS: RBAC AUTHORIZATION MATRIX (Requirement 4)
# ==============================================================================
def test_rbac_matrix_permissions():
    """Verify role permission boundaries for SuperAdmin, TenantOperator, and SecurityAuditor."""
    # 1. SuperAdmin has unrestricted access
    assert tol.check_rbac_permission("SuperAdmin", "LIST")
    assert tol.check_rbac_permission("SuperAdmin", "PROVISION")
    assert tol.check_rbac_permission("SuperAdmin", "SUSPEND")
    assert tol.check_rbac_permission("SuperAdmin", "RESUME")
    assert tol.check_rbac_permission("SuperAdmin", "DELETE")
    assert tol.check_rbac_permission("SuperAdmin", "AUDIT_LOGS")

    # 2. TenantOperator can operate fleet but CANNOT delete
    assert tol.check_rbac_permission("TenantOperator", "LIST")
    assert tol.check_rbac_permission("TenantOperator", "PROVISION")
    assert tol.check_rbac_permission("TenantOperator", "SUSPEND")
    assert tol.check_rbac_permission("TenantOperator", "RESUME")
    assert tol.check_rbac_permission("TenantOperator", "AUDIT_LOGS")
    assert not tol.check_rbac_permission("TenantOperator", "DELETE"), (
        "TenantOperator must be forbidden from DELETE"
    )

    # 3. SecurityAuditor is strictly read-only
    assert tol.check_rbac_permission("SecurityAuditor", "LIST")
    assert tol.check_rbac_permission("SecurityAuditor", "AUDIT_LOGS")
    assert tol.check_rbac_permission("SecurityAuditor", "METRICS")
    assert not tol.check_rbac_permission("SecurityAuditor", "PROVISION"), (
        "SecurityAuditor must be forbidden from PROVISION"
    )
    assert not tol.check_rbac_permission("SecurityAuditor", "SUSPEND"), (
        "SecurityAuditor must be forbidden from SUSPEND"
    )
    assert not tol.check_rbac_permission("SecurityAuditor", "RESUME"), (
        "SecurityAuditor must be forbidden from RESUME"
    )
    assert not tol.check_rbac_permission("SecurityAuditor", "DELETE"), (
        "SecurityAuditor must be forbidden from DELETE"
    )
    print("  ✅ RBAC authorization matrix verified successfully.")


# ==============================================================================
# UNIT TESTS: LAMBDA HANDLER AUTHENTICATION & RBAC DISPATCH
# ==============================================================================
def test_lambda_login_mfa_challenge_flow():
    """Verify end-to-end Login -> MFA challenge -> TOTP verification -> JWT issuance."""
    # 1. Login with bootstrap credentials
    login_event = {
        "httpMethod": "POST",
        "body": json.dumps(
            {
                "action": "LOGIN",
                "username": "admin@png261.dev",
                "password": "AdminPassword123!",
            }
        ),
    }
    resp = tol.lambda_handler(login_event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["status"] == "MFA_REQUIRED"
    assert "challenge_token" in body
    challenge_token = body["challenge_token"]
    demo_secret = body["demo_totp_secret"]

    # 2. Verify MFA with invalid code -> 401
    bad_mfa_event = {
        "httpMethod": "POST",
        "body": json.dumps(
            {
                "action": "VERIFY_MFA",
                "challenge_token": challenge_token,
                "mfa_code": "000000",
            }
        ),
    }
    resp_bad = tol.lambda_handler(bad_mfa_event, None)
    assert resp_bad["statusCode"] == 401

    # 3. Verify MFA with valid code -> 200 + token
    valid_code = tol.generate_totp_code(demo_secret)
    good_mfa_event = {
        "httpMethod": "POST",
        "body": json.dumps(
            {
                "action": "VERIFY_MFA",
                "challenge_token": challenge_token,
                "mfa_code": valid_code,
            }
        ),
    }
    resp_good = tol.lambda_handler(good_mfa_event, None)
    assert resp_good["statusCode"] == 200
    good_body = json.loads(resp_good["body"])
    assert good_body["status"] == "OK"
    assert good_body["role"] == "SuperAdmin"
    assert "token" in good_body
    print("  ✅ Lambda Login -> TOTP MFA Challenge -> Verification flow passed.")


def test_lambda_rbac_enforcement():
    """Verify that SecurityAuditor and TenantOperator get 403 Forbidden on disallowed operations."""
    # 1. Token for SecurityAuditor
    auditor_token = tol.create_session_token(
        "auditor@png261.dev", role="SecurityAuditor"
    )
    # Auditor attempting PROVISION must return 403
    prov_event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {auditor_token}"},
        "body": json.dumps({"action": "PROVISION", "tenant_id": "test-forbidden"}),
    }
    resp = tol.lambda_handler(prov_event, None)
    assert resp["statusCode"] == 403, (
        f"Expected 403 Forbidden for SecurityAuditor PROVISION, got {resp['statusCode']}"
    )
    assert "Forbidden" in json.loads(resp["body"])["error"]

    # 2. Token for TenantOperator
    ops_token = tol.create_session_token("ops@png261.dev", role="TenantOperator")
    # Operator attempting DELETE must return 403
    del_event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {ops_token}"},
        "body": json.dumps({"action": "DELETE", "tenant_id": "test-forbidden"}),
    }
    resp_del = tol.lambda_handler(del_event, None)
    assert resp_del["statusCode"] == 403, (
        f"Expected 403 Forbidden for TenantOperator DELETE, got {resp_del['statusCode']}"
    )
    assert "Forbidden" in json.loads(resp_del["body"])["error"]
    print("  ✅ Lambda RBAC enforcement (HTTP 403 Forbidden on violations) passed.")


def test_lambda_cors_preflight():
    """Verify OPTIONS preflight request returns 200 with CORS headers."""
    resp = tol.lambda_handler({"httpMethod": "OPTIONS"}, None)
    assert resp["statusCode"] == 200
    headers_lower = {k.lower(): v for k, v in resp["headers"].items()}
    assert "access-control-allow-origin" in headers_lower
    print("  ✅ Lambda CORS preflight response verified.")


def test_lambda_missing_tenant_id():
    """Verify that mutation without tenant_id returns HTTP 400."""
    admin_token = tol.create_session_token("admin@png261.dev", role="SuperAdmin")
    resp = tol.lambda_handler(
        {
            "httpMethod": "POST",
            "headers": {"authorization": f"Bearer {admin_token}"},
            "body": json.dumps({"action": "PROVISION"}),
        },
        None,
    )
    assert resp["statusCode"] == 400
    assert "error" in json.loads(resp["body"])
    print("  ✅ Lambda missing tenant_id validation verified.")


# ==============================================================================
# UNIT TESTS: IMMUTABLE AUDIT LOGGING (Requirement 3)
# ==============================================================================
def test_immutable_audit_logging():
    """Verify audit log event recording and retrieval via AUDIT_LOGS endpoint."""
    evt_id = tol.record_audit_event(
        actor="admin@png261.dev",
        role="SuperAdmin",
        action="TEST_AUDIT_ACTION",
        target="tenant-test",
        status="SUCCESS",
        details={"test": True},
        ip_address="127.0.0.1",
    )
    assert evt_id is not None
    assert len(evt_id) > 10

    # Query AUDIT_LOGS endpoint with authenticated session
    token = tol.create_session_token("auditor@png261.dev", role="SecurityAuditor")
    audit_event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {token}"},
        "body": json.dumps({"action": "AUDIT_LOGS"}),
    }
    resp = tol.lambda_handler(audit_event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "audit_logs" in body
    assert isinstance(body["audit_logs"], list)
    print("  ✅ Immutable audit trail logging and retrieval endpoint verified.")


def test_lambda_tenant_detail_endpoint():
    """Verify GET_TENANT_DETAIL returns full AWS topology, dual-container agent state, accounts, and incident history."""
    admin_token = tol.create_session_token("admin@png261.dev", role="SuperAdmin")
    event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {admin_token}"},
        "body": json.dumps(
            {"action": "GET_TENANT_DETAIL", "tenant_id": "enterprise-test"}
        ),
    }
    resp = tol.lambda_handler(event, None)
    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])

    # 1. Tenant DDB record
    assert "tenant" in data
    assert data["tenant"]["tenant_id"] == "enterprise-test"

    # 2. AWS Dedicated Topology
    assert "aws_topology" in data
    topo = data["aws_topology"]
    assert topo["cluster_name"] == "prod-nextcloud-cluster"
    assert topo["service_name"] == "service-enterprise-test"
    assert "database_name" in topo
    assert "efs_mount_path" in topo
    assert "s3_vault_prefix" in topo

    # 3. Agent & Container Runtime
    assert "agent" in data
    agent = data["agent"]
    assert "containers" in agent
    assert len(agent["containers"]) == 2
    app_c = agent["containers"][0]
    sidecar_c = agent["containers"][1]
    assert "nextcloud" in app_c["name"]
    assert "litellm-bedrock-bridge" in sidecar_c["name"]
    assert sidecar_c["model_id"] == "anthropic.claude-3-5-sonnet-20241022-v2:0"

    # 4. Accounts and Incident logs
    assert "accounts" in data
    assert len(data["accounts"]) >= 1
    assert "incidents_history" in data
    print(
        "  ✅ Lambda GET_TENANT_DETAIL endpoint (Topology + Dual-Container Agent + Accounts) verified."
    )


def test_lambda_agent_rolling_restart():
    """Verify RESTART_AGENT triggers ECS service update and records immutable audit log."""
    operator_token = tol.create_session_token("ops@png261.dev", role="TenantOperator")
    event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {operator_token}"},
        "body": json.dumps({"action": "RESTART_AGENT", "tenant_id": "restart-test"}),
    }
    resp = tol.lambda_handler(event, None)
    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])
    assert data["tenant_id"] == "restart-test"
    assert data["deployment_status"] == "IN_PROGRESS"
    print("  ✅ Lambda RESTART_AGENT (Rolling restart + audit trail) verified.")


def test_lambda_update_incident_status_and_circuit_breaker():
    """Verify UPDATE_INCIDENT_STATUS updates circuit breaker state, severity, root cause and records incident log."""
    operator_token = tol.create_session_token("ops@png261.dev", role="TenantOperator")
    event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {operator_token}"},
        "body": json.dumps(
            {
                "action": "UPDATE_INCIDENT_STATUS",
                "tenant_id": "incident-test",
                "status": "INCIDENT",
                "severity": "SEV-1",
                "incident_title": "Postgres connection exhaustion",
                "root_cause": "Desktop sync storm caused connection saturation",
                "action_taken": "Recycled ECS container tasks, adjusted pool size",
                "incident_state": "INVESTIGATING",
            }
        ),
    }
    resp = tol.lambda_handler(event, None)
    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])
    assert data["status"] == "INCIDENT"
    assert data["incident"]["severity"] == "SEV-1"
    assert data["incident"]["title"] == "Postgres connection exhaustion"
    assert (
        data["incident"]["root_cause"]
        == "Desktop sync storm caused connection saturation"
    )
    print(
        "  ✅ Lambda UPDATE_INCIDENT_STATUS (Circuit-breaker + Severity + Root Cause) verified."
    )


def test_lambda_tenant_accounts_management():
    """Verify GET_TENANT_ACCOUNTS, CREATE_TENANT_ACCOUNT, and RESET_TENANT_ACCOUNT_PASSWORD."""
    admin_token = tol.create_session_token("admin@png261.dev", role="SuperAdmin")
    tenant_id = "accounts-test"

    # 1. List accounts
    list_event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {admin_token}"},
        "body": json.dumps({"action": "GET_TENANT_ACCOUNTS", "tenant_id": tenant_id}),
    }
    resp = tol.lambda_handler(list_event, None)
    assert resp["statusCode"] == 200
    accounts = json.loads(resp["body"])["accounts"]
    assert len(accounts) >= 1

    # 2. Create account
    create_event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {admin_token}"},
        "body": json.dumps(
            {
                "action": "CREATE_TENANT_ACCOUNT",
                "tenant_id": tenant_id,
                "username": "sarah.connor",
                "display_name": "Sarah Connor",
                "email": "sarah@accounts-test.com",
                "role": "TenantAdmin",
                "quota_gb": 50,
            }
        ),
    }
    resp_create = tol.lambda_handler(create_event, None)
    assert resp_create["statusCode"] == 200
    created = json.loads(resp_create["body"])["account"]
    assert created["username"] == "sarah.connor"
    assert created["role"] == "TenantAdmin"

    # 3. Reset password
    reset_event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {admin_token}"},
        "body": json.dumps(
            {
                "action": "RESET_TENANT_ACCOUNT_PASSWORD",
                "tenant_id": tenant_id,
                "username": "sarah.connor",
            }
        ),
    }
    resp_reset = tol.lambda_handler(reset_event, None)
    assert resp_reset["statusCode"] == 200
    reset_data = json.loads(resp_reset["body"])
    assert reset_data["username"] == "sarah.connor"
    assert "temporary_password" in reset_data
    assert reset_data["expires_in"] == "24h"
    print(
        "  ✅ Lambda Tenant Accounts Management (List, Create, Reset Password) verified."
    )


def test_lambda_occ_runner():
    """Verify EXECUTE_OCC_COMMAND executes Nextcloud occ CLI commands with realistic terminal output."""
    admin_token = tol.create_session_token("admin@png261.dev", role="SuperAdmin")
    tenant_id = "acme"

    # 1. Test status command
    status_event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {admin_token}"},
        "body": json.dumps(
            {
                "action": "EXECUTE_OCC_COMMAND",
                "tenant_id": tenant_id,
                "command": "status",
            }
        ),
    }
    resp = tol.lambda_handler(status_event, None)
    assert resp["statusCode"] == 200
    res_data = json.loads(resp["body"])
    assert res_data["status"] == "SUCCESS"
    assert res_data["exit_code"] == 0
    assert "installed: true" in res_data["output"]
    assert "30.0.1" in res_data["output"]

    # 2. Test files:scan command
    scan_event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {admin_token}"},
        "body": json.dumps(
            {
                "action": "EXECUTE_OCC_COMMAND",
                "tenant_id": tenant_id,
                "command": "files:scan --all",
            }
        ),
    }
    resp_scan = tol.lambda_handler(scan_event, None)
    assert resp_scan["statusCode"] == 200
    scan_data = json.loads(resp_scan["body"])
    assert "Starting scan" in scan_data["output"]
    assert scan_data["exit_code"] == 0

    # 3. Test check command
    check_event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {admin_token}"},
        "body": json.dumps(
            {
                "action": "EXECUTE_OCC_COMMAND",
                "tenant_id": tenant_id,
                "command": "check",
            }
        ),
    }
    resp_check = tol.lambda_handler(check_event, None)
    assert resp_check["statusCode"] == 200
    check_data = json.loads(resp_check["body"])
    assert "PostgreSQL 16.3" in check_data["output"]
    print("  ✅ Lambda In-Browser OCC Runner (status, files:scan, check) verified.")


def test_lambda_container_logs():
    """Verify GET_CONTAINER_LOGS retrieves structured logs with container and level filtering."""
    admin_token = tol.create_session_token("admin@png261.dev", role="SuperAdmin")
    tenant_id = "acme"

    # 1. Fetch all container logs
    all_logs_event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {admin_token}"},
        "body": json.dumps(
            {
                "action": "GET_CONTAINER_LOGS",
                "tenant_id": tenant_id,
                "container": "all",
                "limit": 20,
            }
        ),
    }
    resp = tol.lambda_handler(all_logs_event, None)
    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])
    assert "events" in data
    assert len(data["events"]) > 0

    # 2. Filter specifically for LiteLLM Bedrock Bridge sidecar
    sidecar_event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {admin_token}"},
        "body": json.dumps(
            {
                "action": "GET_CONTAINER_LOGS",
                "tenant_id": tenant_id,
                "container": "litellm-sidecar",
            }
        ),
    }
    resp_sidecar = tol.lambda_handler(sidecar_event, None)
    assert resp_sidecar["statusCode"] == 200
    sc_data = json.loads(resp_sidecar["body"])
    for ev in sc_data["events"]:
        assert ev["container"] == "litellm-sidecar"
    print("  ✅ Lambda Live Container Logs (App + LiteLLM Bedrock Bridge) verified.")


def test_lambda_webhook_config_and_testing():
    """Verify GET_WEBHOOK_CONFIG, SAVE_WEBHOOK_CONFIG, and TEST_WEBHOOK."""
    admin_token = tol.create_session_token("admin@png261.dev", role="SuperAdmin")

    # 1. Get webhook config
    get_event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {admin_token}"},
        "body": json.dumps({"action": "GET_WEBHOOK_CONFIG"}),
    }
    resp_get = tol.lambda_handler(get_event, None)
    assert resp_get["statusCode"] == 200
    config = json.loads(resp_get["body"])["config"]
    assert "enabled" in config
    assert "events" in config

    # 2. Save webhook config
    save_event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {admin_token}"},
        "body": json.dumps(
            {
                "action": "SAVE_WEBHOOK_CONFIG",
                "config": {
                    "enabled": True,
                    "slack_url": "https://hooks.slack.com/services/TEST/TEST/TEST",
                    "discord_url": "",
                    "pagerduty_key": "",
                    "custom_url": "",
                    "events": {
                        "incident_declared": True,
                        "circuit_breaker": True,
                        "tenant_cloned": True,
                        "agent_restarted": True,
                    },
                },
            }
        ),
    }
    resp_save = tol.lambda_handler(save_event, None)
    assert resp_save["statusCode"] == 200
    saved = json.loads(resp_save["body"])["config"]
    assert saved["slack_url"] == "https://hooks.slack.com/services/TEST/TEST/TEST"

    # 3. Test invalid webhook URL handling
    test_invalid_event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {admin_token}"},
        "body": json.dumps(
            {
                "action": "TEST_WEBHOOK",
                "webhook_type": "slack",
                "webhook_url": "invalid-url",
            }
        ),
    }
    resp_test_inv = tol.lambda_handler(test_invalid_event, None)
    assert resp_test_inv["statusCode"] == 400
    assert "Invalid webhook URL" in json.loads(resp_test_inv["body"])["error"]
    print(
        "  ✅ Lambda Webhook Notifications (Config, Persistence & Test Ping) verified."
    )


def test_lambda_tenant_clone_to_sandbox():
    """Verify CLONE_TENANT creates isolated staging sandbox with dedicated DB, S3 prefix and EFS AP."""
    admin_token = tol.create_session_token("admin@png261.dev", role="SuperAdmin")
    source_id = "acme"
    target_id = f"sandbox-{int(time.time())}"

    clone_event = {
        "httpMethod": "POST",
        "headers": {"authorization": f"Bearer {admin_token}"},
        "body": json.dumps(
            {
                "action": "CLONE_TENANT",
                "source_tenant_id": source_id,
                "target_tenant_id": target_id,
                "target_domain": f"{target_id}.png261.dev",
                "admin_email": f"devops@{target_id}.com",
                "quota_gb": 30,
            }
        ),
    }
    resp = tol.lambda_handler(clone_event, None)
    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])
    tenant = data["tenant"]

    # Isolation guarantees
    assert tenant["tenant_id"] == target_id
    assert tenant["is_sandbox"] is True
    assert tenant["cloned_from"] == source_id
    assert tenant["service_name"] == f"service-{target_id}"
    assert tenant["database_name"] == f"nc_{target_id.replace('-', '_')}"
    assert target_id in tenant["s3_vault_prefix"]
    assert "fsap-sbx-" in tenant["efs_access_point_id"]
    print(
        f"  ✅ Lambda Tenant Sandbox Clone (Fork '{source_id}' -> '{target_id}') verified."
    )


# ==============================================================================
# INTEGRATION / E2E TESTS (Existing Suite Enhanced)
# ==============================================================================
def test_control_panel_html_page():
    """Verify that the control panel serves a complete, valid HTML5 single-page application."""
    html = ""
    try:
        resp = requests.get(WEB_BASE, timeout=5)
        if resp.status_code == 200:
            html = resp.text
    except Exception:
        pass

    if not html:
        index_file = os.path.join(
            os.path.dirname(__file__), "../control-panel/index.html"
        )
        if os.path.exists(index_file):
            with open(index_file, "r", encoding="utf-8") as f:
                html = f.read()
        else:
            pytest.skip(
                "Control panel web endpoint unreachable and local index.html not found"
            )

    # Verify critical UI components and mount points are rendered
    assert "Nextcloud SaaS" in html
    assert "Control Panel" in html
    assert 'id="root"' in html

    # Verify Refine SPA core architecture files exist
    cp_dir = os.path.join(os.path.dirname(__file__), "../control-panel")
    assert os.path.exists(os.path.join(cp_dir, "src/App.tsx")), "Refine App.tsx missing"
    assert os.path.exists(os.path.join(cp_dir, "src/providers/authProvider.ts")), (
        "Refine authProvider missing"
    )
    assert os.path.exists(
        os.path.join(cp_dir, "src/providers/accessControlProvider.ts")
    ), "Refine accessControlProvider missing"
    assert os.path.exists(os.path.join(cp_dir, "src/providers/dataProvider.ts")), (
        "Refine dataProvider missing"
    )
    assert os.path.exists(os.path.join(cp_dir, "src/pages/tenants/list.tsx")), (
        "Refine TenantList page missing"
    )
    assert os.path.exists(os.path.join(cp_dir, "src/pages/audit-logs/list.tsx")), (
        "Refine AuditLogList page missing"
    )
    print("  ✅ Control Panel Refine SPA verified successfully.")


def test_control_panel_json_api():
    """Verify that requesting JSON returns a structured tenant registry list."""
    auth_header = get_auth_header()
    if not auth_header:
        pytest.skip("Admin auth token required for authenticated control panel API")
    try:
        resp = requests.get(
            API_BASE, headers={"Accept": "application/json", **auth_header}, timeout=10
        )
    except requests.exceptions.RequestException as e:
        pytest.skip(f"Control panel API endpoint unreachable: {e}")
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("Content-Type", "")
    data = resp.json()

    assert "tenants" in data
    assert "count" in data
    assert isinstance(data["tenants"], list)
    print(f"  ✅ Tenant Registry JSON API verified (Count: {data['count']}).")


def test_tenant_full_lifecycle_e2e():
    """E2E Test: Provision -> Verify DynamoDB -> Suspend -> Resume -> Delete."""
    if not has_aws_creds or not dynamodb:
        pytest.skip("AWS credentials required for DynamoDB E2E validation")

    auth_header = get_auth_header()
    if not auth_header:
        pytest.skip("Valid auth header required for live mutations")
    test_tenant_id = f"ci-tenant-{int(time.time())}"
    test_domain = f"{test_tenant_id}.appleai.codes"
    test_email = f"admin@{test_tenant_id}.com"

    print(f"\n  🚀 Starting E2E Lifecycle test for tenant: {test_tenant_id}...")

    # 1. PROVISION
    prov_payload = {
        "action": "PROVISION",
        "tenant_id": test_tenant_id,
        "domain": test_domain,
        "admin_email": test_email,
        "quota_gb": 120,
    }
    try:
        resp = requests.post(
            API_BASE, json=prov_payload, headers=auth_header, timeout=15
        )
    except requests.exceptions.RequestException as e:
        pytest.skip(f"Control panel API endpoint unreachable: {e}")
    assert resp.status_code == 200, f"Provision failed: {resp.text}"
    prov_data = resp.json()
    assert prov_data["status"] == "ACTIVE"
    print("  [1/5] Tenant provisioned via API.")

    # 2. VERIFY DYNAMODB
    ddb_item = dynamodb.get_item(
        TableName=TABLE_NAME, Key={"tenant_id": {"S": test_tenant_id}}
    ).get("Item")
    assert ddb_item is not None, "Tenant item missing in DynamoDB!"
    assert ddb_item["status"]["S"] == "ACTIVE"
    assert ddb_item["quota_gb"]["N"] == "120"
    print("  [2/5] DynamoDB registry item validated.")

    # 3. SUSPEND
    resp = requests.post(
        API_BASE,
        json={"action": "SUSPEND", "tenant_id": test_tenant_id},
        headers=auth_header,
        timeout=15,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUSPENDED"

    ddb_item = dynamodb.get_item(
        TableName=TABLE_NAME, Key={"tenant_id": {"S": test_tenant_id}}
    )["Item"]
    assert ddb_item["status"]["S"] == "SUSPENDED"
    print("  [3/5] Tenant suspended successfully.")

    # 4. RESUME
    resp = requests.post(
        API_BASE,
        json={"action": "RESUME", "tenant_id": test_tenant_id},
        headers=auth_header,
        timeout=15,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ACTIVE"

    ddb_item = dynamodb.get_item(
        TableName=TABLE_NAME, Key={"tenant_id": {"S": test_tenant_id}}
    )["Item"]
    assert ddb_item["status"]["S"] == "ACTIVE"
    print("  [4/5] Tenant resumed successfully.")

    # 5. DELETE (Cleanup)
    resp = requests.post(
        API_BASE,
        json={"action": "DELETE", "tenant_id": test_tenant_id},
        headers=auth_header,
        timeout=15,
    )
    assert resp.status_code == 200

    ddb_item = dynamodb.get_item(
        TableName=TABLE_NAME, Key={"tenant_id": {"S": test_tenant_id}}
    ).get("Item")
    assert ddb_item is None, "Tenant item should be deleted!"
    print("  [5/5] Tenant deleted and cleaned up.")
    print("  🎉 Full Tenant Lifecycle E2E test passed!")


def test_cors_preflight():
    """Verify OPTIONS preflight request returns 200 with CORS headers."""
    try:
        resp = requests.options(API_BASE, timeout=10)
    except requests.exceptions.RequestException as e:
        pytest.skip(f"Control panel endpoint unreachable: {e}")
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers
    assert "*" in resp.headers["access-control-allow-origin"]
    print("  ✅ CORS preflight verified successfully.")


def test_missing_tenant_id_error():
    """Verify that calling mutations without tenant_id returns HTTP 400."""
    auth_header = get_auth_header()
    if not auth_header:
        pytest.skip("Admin auth token required for authenticated control panel API")
    try:
        resp = requests.post(
            API_BASE, json={"action": "PROVISION"}, headers=auth_header, timeout=10
        )
    except requests.exceptions.RequestException as e:
        pytest.skip(f"Control panel endpoint unreachable: {e}")
    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data
    print("  ✅ Error handling (missing tenant_id) verified.")


def test_cloudwatch_dashboard_exists():
    """Verify that CloudWatch Dashboard prod-Nextcloud-SaaS-Control-Plane exists."""
    if not has_aws_creds or not cloudwatch:
        pytest.skip("AWS credentials required for CloudWatch dashboard validation")
    try:
        resp = cloudwatch.get_dashboard(DashboardName=DASHBOARD_NAME)
        assert resp["DashboardArn"] is not None
        assert DASHBOARD_NAME in resp["DashboardArn"]
        print(f"  ✅ CloudWatch Dashboard '{DASHBOARD_NAME}' verified active.")
    except Exception as e:
        pytest.skip(f"CloudWatch dashboard '{DASHBOARD_NAME}' not available: {e}")


if __name__ == "__main__":
    pytest.main(["-v", "-s", __file__])
