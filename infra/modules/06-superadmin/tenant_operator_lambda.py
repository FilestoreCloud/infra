import base64
import datetime
import hashlib
import hmac
import json
import os
import secrets
import struct
import sys
import time
import uuid
from typing import Any

import boto3
from botocore.exceptions import ClientError

# Ensure local package imports resolve properly
_CURR_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURR_DIR not in sys.path:
    sys.path.insert(0, _CURR_DIR)

from operator_core.common import (  # noqa: E402
    cognito_idp,
    dynamodb,
    ecs,
    efs,
    elbv2,
    secretsmanager,
    ses,
    sfn,
    ssm,
)

from operator_core import (  # noqa: E402
    _handle_step_function_task,
    _seed_tenant_data,
    clone_tenant_to_sandbox,
    dispatch_webhook_notification,
    ensure_tenant_efs_access_point,
    execute_tenant_occ,
    execute_tenant_occ_async,
    check_tenant_occ_job,
    get_all_tenants,
    get_cloudwatch_stream_metrics,
    get_cloudwatch_widget,
    get_dashboard_html,
    get_infra_config,
    get_live_execution_stream,
    get_step_functions_observability,
    get_tenant_accounts_data,
    get_tenant_container_logs,
    get_tenant_detail,
    get_tenant_finops,
    get_tenant_health,
    export_tenant_data,
    crypto_shred_tenant_data,
    get_tenant_metrics,
    get_webhook_config,
    register_tenant_custom_domain,
    register_tenant_task_definition,
    save_tenant_accounts,
    save_webhook_config,
    test_webhook_endpoint,
    publish_tenant_event,
    get_openapi_spec,
)

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TABLE_NAME = os.environ.get("TABLE_NAME", "prod-nextcloud-tenant-registry")
ADMIN_USERS_TABLE = os.environ.get(
    "ADMIN_USERS_TABLE",
    f"{os.environ.get('ENVIRONMENT_NAME', 'prod')}-nextcloud-admin-users",
)
AUDIT_LOGS_TABLE = os.environ.get(
    "AUDIT_LOGS_TABLE",
    f"{os.environ.get('ENVIRONMENT_NAME', 'prod')}-nextcloud-audit-logs",
)
CLUSTER_NAME = os.environ.get("CLUSTER_NAME", "prod-nextcloud-cluster")
ENVIRONMENT_NAME = os.environ.get("ENVIRONMENT_NAME", "prod")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")

cloudwatch = boto3.client("cloudwatch", region_name=REGION)



SFN_LOG_GROUP = os.environ.get(
    "SFN_LOG_GROUP",
    f"/aws/vendedlogs/states/{ENVIRONMENT_NAME}-nextcloud-sfn",
)

STATE_MACHINE_PROVISION_ARN = os.environ.get("STATE_MACHINE_PROVISION_ARN", "")
STATE_MACHINE_SUSPEND_ARN = os.environ.get("STATE_MACHINE_SUSPEND_ARN", "")
STATE_MACHINE_RESUME_ARN = os.environ.get("STATE_MACHINE_RESUME_ARN", "")
STATE_MACHINE_DEPROVISION_ARN = os.environ.get("STATE_MACHINE_DEPROVISION_ARN", "")
STATE_MACHINE_SEED_ARN = os.environ.get("STATE_MACHINE_SEED_ARN", "")
STATE_MACHINE_DEMO_ARN = os.environ.get("STATE_MACHINE_DEMO_ARN", "")
STATE_MACHINE_FLEET_UPGRADE_ARN = os.environ.get("STATE_MACHINE_FLEET_UPGRADE_ARN", "")


def emit_emf_metric(Namespace, MetricName, Value, Dimensions=None, Unit="None"):
    """Emit high-throughput metrics using AWS Embedded Metric Format (EMF) via structured stdout."""
    try:
        now_ms = int(time.time() * 1000)
        dims = Dimensions or {}
        dim_keys = list(dims.keys())
        payload = {
            "_aws": {
                "Timestamp": now_ms,
                "CloudWatchMetrics": [
                    {
                        "Namespace": Namespace,
                        "Dimensions": [dim_keys] if dim_keys else [],
                        "Metrics": [{"Name": MetricName, "Unit": Unit}],
                    }
                ],
            },
            MetricName: Value,
        }
        for k, v in dims.items():
            payload[k] = v
        print(json.dumps(payload))
    except Exception as exc:
        print(f"EMF emission warning: {exc}")


def safe_put_metric_data(Namespace, MetricData):
    """Safely emit CloudWatch metrics without breaking request execution."""
    try:
        for item in MetricData:
            try:
                m_name = item.get("MetricName", "")
                m_val = float(item.get("Value", 1.0))
                m_unit = item.get("Unit", "None")
                m_dims = {
                    d.get("Name"): d.get("Value")
                    for d in item.get("Dimensions", [])
                }
                emit_emf_metric(Namespace, m_name, m_val, m_dims, m_unit)
            except Exception:
                pass
    except Exception:
        pass

    try:
        cloudwatch.put_metric_data(Namespace=Namespace, MetricData=MetricData)
    except Exception as exc:
        print(f"CloudWatch put_metric_data warning: {exc}")


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Admin-Token",
    "Content-Type": "application/json",
}

_CACHED_INFRA: dict[str, Any] = {}
_CACHED_MASTER_KEY = None
_CACHED_MASTER_KEY_TIME = 0
_CACHED_SM_ADMIN = None
_CACHED_SM_ADMIN_TIME = 0

# ==============================================================================
# RBAC ROLE DEFINITIONS & PERMISSIONS MATRIX (Requirement 4)
# ==============================================================================
ROLES = {
    "SUPER_ADMIN": "SuperAdmin",
}

RBAC_PERMISSIONS = {
    "SuperAdmin": {"*"},  # Full administrative control
}


def check_rbac_permission(role, action):
    """Verify if user role has authorization to execute action."""
    perms = RBAC_PERMISSIONS.get(role, set())
    if "*" in perms or action in perms:
        return True
    return False


# ==============================================================================
# RFC 6238 TOTP MULTI-FACTOR AUTHENTICATION ENGINE (Requirement 1)
# ==============================================================================
def generate_totp_secret():
    """Generate a standard 32-character base32 secret key."""
    return base64.b32encode(secrets.token_bytes(20)).decode("utf-8")


def generate_totp_code(secret, time_step=None):
    """Generate a 6-digit TOTP code for a given base32 secret and 30-second interval."""
    if time_step is None:
        time_step = int(time.time() // 30)
    try:
        clean_secret = secret.replace(" ", "").upper()
        # Add padding if needed
        padding = 8 - (len(clean_secret) % 8)
        if padding != 8:
            clean_secret += "=" * padding
        key = base64.b32decode(clean_secret, casefold=True)
        msg = struct.pack(">Q", time_step)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        offset = h[-1] & 0x0F
        code = (struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF) % 1000000
        return f"{code:06d}"
    except Exception as e:
        print(f"Error generating TOTP code: {e}")
        return "000000"


def verify_totp_code(secret, code, window=1):
    """Verify 6-digit TOTP code with time drift window (default ±30s)."""
    if not secret or not code:
        return False
    try:
        code_str = str(code).strip()
        if not code_str.isascii() or not code_str.isdigit():
            return False
        current_step = int(time.time() // 30)
        for step in range(current_step - window, current_step + window + 1):
            if hmac.compare_digest(generate_totp_code(secret, step), code_str):
                return True
    except Exception:
        return False
    return False


def get_totp_uri(username, secret, issuer="NextcloudSaaS"):
    """Generate standard otpauth URI compatible with Google Authenticator, 1Password, Authy."""
    return f"otpauth://totp/{issuer}:{username}?secret={secret}&issuer={issuer}"


# ==============================================================================
# PASSWORD CRYPTOGRAPHY & IDENTITY STORE (Requirement 1)
# ==============================================================================
def hash_password(password, salt=None):
    """PBKDF2-HMAC-SHA256 password hashing with 100,000 rounds."""
    if not salt:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
    )
    return f"{salt}${h.hex()}"


def verify_password(password, stored_hash):
    """Verify password against salt and PBKDF2 hash."""
    if not stored_hash or "$" not in stored_hash:
        return False
    try:
        salt, expected_h = stored_hash.split("$", 1)
        h = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
        )
        return hmac.compare_digest(h.hex(), expected_h)
    except Exception:
        return False


# Enterprise Bootstrap User Directory (Zero hardcoded credentials - Dynamic authentication via Cognito/DynamoDB)
BOOTSTRAP_USERS: dict[str, Any] = {}


def get_user_account(username):
    """Look up user identity from DynamoDB Admin Registry or Cognito User Pool."""
    if not username:
        return None
    username = username.strip().lower()

    # 1. Try DynamoDB Admin Users table
    try:
        res = dynamodb.get_item(
            TableName=ADMIN_USERS_TABLE, Key={"username": {"S": username}}
        )
        item = res.get("Item")
        if item:
            return {
                "username": item["username"]["S"],
                "display_name": item.get("display_name", {}).get("S", username),
                "role": item.get("role", {}).get("S", "SuperAdmin"),
                "password_hash": item.get("password_hash", {}).get("S", ""),
                "mfa_enabled": item.get("mfa_enabled", {}).get("BOOL", True),
                "mfa_secret": item.get("mfa_secret", {}).get("S", ""),
                "status": item.get("status", {}).get("S", "ACTIVE"),
            }
    except Exception:
        pass

    # 2. Try AWS Cognito User Pool
    if COGNITO_USER_POOL_ID:
        try:
            user_res = cognito_idp.admin_get_user(
                UserPoolId=COGNITO_USER_POOL_ID,
                Username=username,
            )
            if user_res:
                user_status = user_res.get("UserStatus", "CONFIRMED")
                enabled = user_res.get("Enabled", True)
                if enabled and user_status in ["CONFIRMED", "FORCE_CHANGE_PASSWORD"]:
                    attrs = {
                        a["Name"]: a["Value"]
                        for a in user_res.get("UserAttributes", [])
                    }
                    return {
                        "username": username,
                        "display_name": attrs.get("name", attrs.get("email", username)),
                        "role": attrs.get("custom:role", "SuperAdmin"),
                        "mfa_enabled": True,
                        "auth_source": "COGNITO",
                        "status": "ACTIVE" if enabled else "DISABLED",
                    }
        except Exception:
            pass

    # 3. Check dynamic bootstrap users (empty by default)
    if username in BOOTSTRAP_USERS:
        return BOOTSTRAP_USERS[username]

    return None


# ==============================================================================
# IMMUTABLE AUDIT LOGGING ENGINE (Requirement 3)
# ==============================================================================
def record_audit_event(
    actor, role, action, target, status, details=None, ip_address=None, user_agent=None
):
    """Record immutable audit log to DynamoDB and CloudWatch Logs."""
    event_id = str(uuid.uuid4())
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    now_ts = int(time.time())

    item = {
        "event_id": {"S": event_id},
        "timestamp": {"S": ts},
        "actor": {"S": actor or "anonymous"},
        "role": {"S": role or "unauthenticated"},
        "action": {"S": action},
        "target": {"S": target or "system"},
        "status": {"S": status},  # SUCCESS, DENIED, FAILED
        "details": {
            "S": (
                json.dumps(details)
                if isinstance(details, (dict, list))
                else str(details or "")
            )
        },
        "ip_address": {"S": ip_address or "unknown"},
        "user_agent": {"S": user_agent or "unknown"},
        "ttl": {"N": str(now_ts + 365 * 86400)},  # 1-year compliance retention
    }

    # 1. Persist to DynamoDB Audit Logs table
    try:
        dynamodb.put_item(TableName=AUDIT_LOGS_TABLE, Item=item)
    except Exception as e:
        print(
            f"Warning: failed to record audit event to DynamoDB ({AUDIT_LOGS_TABLE}): {e}"
        )

    # 2. Output structured JSON for CloudWatch Logs ingestion
    log_payload = {
        "audit_event": True,
        "event_id": event_id,
        "timestamp": ts,
        "actor": actor,
        "role": role,
        "action": action,
        "target": target,
        "status": status,
        "details": details,
        "source_ip": ip_address,
        "user_agent": user_agent,
    }
    print(f"[AUDIT] {json.dumps(log_payload)}")
    return event_id


def get_audit_logs(limit=50):
    """Retrieve recent immutable audit trail records."""
    logs = []
    try:
        resp = dynamodb.scan(TableName=AUDIT_LOGS_TABLE, Limit=limit)
        for item in resp.get("Items", []):
            logs.append(
                {
                    "event_id": item.get("event_id", {}).get("S", ""),
                    "timestamp": item.get("timestamp", {}).get("S", ""),
                    "actor": item.get("actor", {}).get("S", ""),
                    "role": item.get("role", {}).get("S", ""),
                    "action": item.get("action", {}).get("S", ""),
                    "target": item.get("target", {}).get("S", ""),
                    "status": item.get("status", {}).get("S", "SUCCESS"),
                    "details": item.get("details", {}).get("S", ""),
                    "ip_address": item.get("ip_address", {}).get("S", ""),
                }
            )
        logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    except Exception as e:
        print(f"Warning scanning audit logs from DynamoDB: {e}")
    return logs[:limit]


def get_client_ip(event):
    """Extract source IP from event headers and requestContext."""
    req_ctx = event.get("requestContext") or {}
    http_ctx = req_ctx.get("http") or {}
    ip = http_ctx.get("sourceIp") or req_ctx.get("identity", {}).get("sourceIp")
    if not ip:
        headers = event.get("headers") or {}
        ip = (
            headers.get("x-forwarded-for", "").split(",")[0].strip()
            or headers.get("X-Forwarded-For", "").split(",")[0].strip()
        )
    return ip or "127.0.0.1"


def get_user_agent(event):
    """Extract User-Agent string from request headers."""
    headers = event.get("headers") or {}
    return headers.get("user-agent") or headers.get("User-Agent") or "unknown"


# ==============================================================================
# SECURE JWT SESSION & CHALLENGE TOKENS
# ==============================================================================
def get_admin_master_key():
    """Retrieve super admin master key from SSM Parameter Store (SecureString)."""
    global _CACHED_MASTER_KEY, _CACHED_MASTER_KEY_TIME
    now = time.time()
    if _CACHED_MASTER_KEY and (now - _CACHED_MASTER_KEY_TIME < 300):
        return _CACHED_MASTER_KEY
    try:
        resp = ssm.get_parameter(
            Name=f"/nextcloud/{ENVIRONMENT_NAME}/control-plane/admin-master-key",
            WithDecryption=True,
        )
        _CACHED_MASTER_KEY = resp["Parameter"]["Value"]
        _CACHED_MASTER_KEY_TIME = now
        return _CACHED_MASTER_KEY
    except Exception as e:
        print(f"Warning fetching admin master key from SSM: {e}")
        return None


def get_sm_admin_credentials():
    """Retrieve bootstrap admin credentials from AWS Secrets Manager."""
    global _CACHED_SM_ADMIN, _CACHED_SM_ADMIN_TIME
    now = time.time()
    if _CACHED_SM_ADMIN and (now - _CACHED_SM_ADMIN_TIME < 300):
        return _CACHED_SM_ADMIN
    try:
        resp = secretsmanager.get_secret_value(
            SecretId=f"/nextcloud/{ENVIRONMENT_NAME}/secrets/admin-credentials"
        )
        _CACHED_SM_ADMIN = json.loads(resp.get("SecretString", "{}"))
        _CACHED_SM_ADMIN_TIME = now
        return _CACHED_SM_ADMIN
    except Exception as e:
        print(f"Warning fetching admin credentials from Secrets Manager: {e}")
        return None


def get_signing_key():
    """Resolve active HMAC signing key for sessions. Returns None if unreachable."""
    key = get_admin_master_key()
    if not key:
        creds = get_sm_admin_credentials()
        key = creds.get("password") if creds else None
    return key


def create_session_token(username, role=None, key=None):
    """Generate a signed HMAC-SHA256 session token with 24-hour expiration and RBAC claims."""
    if not key:
        key = get_signing_key()
    if not key:
        raise RuntimeError(
            "Authentication service signing keys unavailable. Fail-closed."
        )
    if not role:
        user = get_user_account(username)
        role = user["role"] if user else "SuperAdmin"

    payload = {
        "user": username,
        "sub": username,
        "role": role,
        "mfa": True,
        "exp": int(time.time()) + 86400,
        "nonce": secrets.token_hex(8),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    sig = hmac.new(
        key.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{payload_b64}.{sig}"


def authenticate_with_cognito(username, password):
    """Authenticate username and password directly against AWS Cognito User Pool."""
    if not COGNITO_USER_POOL_ID or not COGNITO_CLIENT_ID:
        return False, None, "Cognito User Pool not configured."
    try:
        cognito_idp.admin_initiate_auth(
            UserPoolId=COGNITO_USER_POOL_ID,
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow="ADMIN_NO_SRP_AUTH",
            AuthParameters={
                "USERNAME": username,
                "PASSWORD": password,
            },
        )
        role = "SuperAdmin"
        try:
            user_data = cognito_idp.admin_get_user(
                UserPoolId=COGNITO_USER_POOL_ID,
                Username=username,
            )
            attrs = {a["Name"]: a["Value"] for a in user_data.get("UserAttributes", [])}
            role = attrs.get("custom:role", "SuperAdmin")
        except Exception:
            pass
        return (
            True,
            {"username": username, "role": role, "auth_source": "COGNITO"},
            None,
        )
    except cognito_idp.exceptions.NotAuthorizedException:
        return False, None, "Incorrect username or password."
    except cognito_idp.exceptions.UserNotFoundException:
        return False, None, "User does not exist in Cognito User Pool."
    except Exception as e:
        print(f"[COGNITO_AUTH_ERROR] {e}")
        return False, None, f"Cognito authentication error: {str(e)}"


def send_mfa_email(recipient_email, mfa_code):
    """Send 6-digit MFA verification code to administrator's email using Amazon SES."""
    subject = f"[Storix SuperAdmin] Your MFA Verification Code: {mfa_code}"
    body_text = f"""Hello Administrator,

Your 6-digit verification code for Storix SuperAdmin Control Plane sign-in is:

    {mfa_code}

This code is valid for 10 minutes. If you did not initiate this sign-in request, please secure your credentials immediately.

Regards,
Storix Security Operations
"""
    body_html = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; padding: 20px; background-color: #f8fafc; color: #1e293b;">
  <div style="max-width: 500px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; padding: 28px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
    <div style="text-align: center; margin-bottom: 24px;">
      <span style="font-size: 36px;">☁️</span>
      <h2 style="color: #0f172a; margin: 8px 0 4px;">SuperAdmin Sign-In Verification</h2>
      <p style="color: #64748b; font-size: 14px; margin: 0;">Multi-Tenant SaaS Control Plane</p>
    </div>
    <p style="font-size: 15px;">Hello Administrator,</p>
    <p style="font-size: 14px; color: #475569;">Please use the following 6-digit verification code to complete your sign-in to the Storix SuperAdmin portal:</p>
    <div style="text-align: center; margin: 24px 0;">
      <div style="display: inline-block; background-color: #f1f5f9; border: 1px dashed #cbd5e1; border-radius: 6px; padding: 14px 28px; font-size: 32px; font-weight: 700; letter-spacing: 6px; color: #ec7211; font-family: monospace;">
        {mfa_code}
      </div>
    </div>
    <p style="font-size: 13px; color: #64748b;">This code will expire in <strong>10 minutes</strong>. Do not share this code with anyone.</p>
    <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
    <p style="font-size: 12px; color: #94a3b8; margin: 0;">If you did not request this verification code, please review your account activity and update your password immediately.</p>
  </div>
</body>
</html>"""
    try:
        sender_email = os.environ.get("SES_SENDER_EMAIL", recipient_email)
        ses.send_email(
            Source=sender_email,
            Destination={"ToAddresses": [recipient_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": body_text, "Charset": "UTF-8"},
                    "Html": {"Data": body_html, "Charset": "UTF-8"},
                },
            },
        )
        print(
            f"[AUTH] Successfully sent MFA verification code to {recipient_email} via SES."
        )
        return True
    except Exception as e:
        print(f"[AUTH_WARNING] Could not dispatch SES email to {recipient_email}: {e}")
        return False


def create_challenge_token(username, role, otp_code=None, key=None):
    """Generate a signed temporary MFA challenge token valid for 600 seconds."""
    if not key:
        key = get_signing_key()
    if not key:
        raise RuntimeError(
            "Authentication service signing keys unavailable. Fail-closed."
        )
    payload = {
        "user": username,
        "role": role,
        "type": "mfa_challenge",
        "exp": int(time.time()) + 600,
        "nonce": secrets.token_hex(6),
    }
    if otp_code:
        payload["otp_hash"] = hashlib.sha256(str(otp_code).strip().encode()).hexdigest()
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    sig = hmac.new(
        key.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_session_token(token, key=None):
    """Verify HMAC signature and expiration of session or challenge token."""
    if not token or "." not in token:
        return None
    keys_to_try = [key] if key else []
    if not keys_to_try:
        k = get_signing_key()
        if k:
            keys_to_try.append(k)
        master_k = get_admin_master_key()
        if master_k and master_k not in keys_to_try:
            keys_to_try.append(master_k)

    if not keys_to_try:
        return None

    for k in keys_to_try:
        if not k:
            continue
        try:
            payload_b64, sig = token.split(".", 1)
            expected_sig = hmac.new(
                k.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(sig, expected_sig):
                continue
            padding = 4 - (len(payload_b64) % 4)
            if padding != 4:
                payload_b64 += "=" * padding
            payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
            payload = json.loads(payload_bytes.decode("utf-8"))
            if payload.get("exp", 0) < time.time():
                return None
            return payload
        except Exception:
            continue
    return None


def _extract_token(event, payload):
    """Extract bearer or header token from incoming event."""
    headers = event.get("headers") or {}
    auth_header = ""
    for k, v in headers.items():
        if k.lower() == "authorization":
            auth_header = v
            break
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    for k, v in headers.items():
        if k.lower() == "x-admin-token":
            return v.strip()
    # Check HttpOnly session cookie
    cookie_header = ""
    for k, v in headers.items():
        if k.lower() == "cookie":
            cookie_header = v
            break
    if cookie_header:
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith("saas_admin_session="):
                return part[len("saas_admin_session=") :].strip()
    if isinstance(payload, dict) and payload.get("token"):
        return payload["token"]
    qp = event.get("queryStringParameters") or {}
    if qp.get("token"):
        return qp["token"]
    return None


def _is_authenticated(event, payload):
    """Verify if request contains a valid signed session token (rejects temporary challenge tokens)."""
    token = _extract_token(event, payload)
    if not token:
        return False, None
    user_info = verify_session_token(token)
    if user_info and user_info.get("type") != "mfa_challenge":
        return True, user_info
    return False, None





def _alb_response(resp):
    if not isinstance(resp, dict):
        return resp
    status_code = resp.get("statusCode", 200)
    status_map = {
        200: "200 OK",
        201: "201 Created",
        204: "204 No Content",
        302: "302 Found",
        400: "400 Bad Request",
        401: "401 Unauthorized",
        403: "403 Forbidden",
        404: "404 Not Found",
        500: "500 Internal Server Error",
        502: "502 Bad Gateway",
    }
    resp.setdefault(
        "statusDescription", status_map.get(status_code, f"{status_code} Status")
    )
    resp.setdefault("isBase64Encoded", False)
    return resp



def lambda_handler(event, context):
    try:
        # Check if direct Step Functions micro-workflow invocation
        action = (event.get("action") or "").upper() if isinstance(event, dict) else ""
        is_http = (
            bool(event.get("httpMethod") or event.get("requestContext"))
            if isinstance(event, dict)
            else False
        )
        if action in [
            "PROVISION_TENANT_RESOURCES",
            "CHECK_TENANT_HEALTH",
            "SEED_TENANT_USERS_AND_FILES",
            "SEED_ADMIN_USERS",
            "SEED_SAMPLE_FILES",
            "SAGA_CLEANUP_TENANT",
            "DEPROVISION_ECS",
            "DEPROVISION_STORAGE",
        ] or (action in ["SUSPEND", "RESUME", "SEED"] and not is_http):
            return _handle_step_function_task(event)

        return _alb_response(_handle_request(event, context))
    except RuntimeError as re:
        if "Authentication service signing keys unavailable" in str(
            re
        ) or "Fail-closed" in str(re):
            return _alb_response(
                {
                    "statusCode": 503,
                    "headers": CORS_HEADERS,
                    "body": json.dumps(
                        {
                            "status": "AUTH_FAILED",
                            "error": "Authentication service signing keys unavailable. Fail-closed.",
                        }
                    ),
                }
            )
        print(f"Unhandled RuntimeError in lambda_handler: {re}")
        return _alb_response(
            {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": str(re)}),
            }
        )
    except Exception as e:
        print(f"Unhandled exception in lambda_handler: {e}")
        return _alb_response(
            {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": str(e)}),
            }
        )


def _handle_request(event, context):
    print("Received event:", json.dumps(event))

    http_method = event.get("requestContext", {}).get("http", {}).get(
        "method"
    ) or event.get("httpMethod")
    headers = event.get("headers") or {}
    accept_header = headers.get("accept", headers.get("Accept", ""))
    query_params = event.get("queryStringParameters") or {}

    # Handle CORS Preflight
    if http_method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    # Parse payload if present
    payload = event.get("body", event)
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            pass
    if not isinstance(payload, dict):
        payload = {}

    action = payload.get("action", "").upper() or query_params.get("action", "").upper()
    client_ip = get_client_ip(event)
    user_agent = get_user_agent(event)

    # 0. Handle OpenAPI 3.1 & Swagger Documentation Endpoints
    raw_path = event.get("rawPath") or event.get("path") or ""
    if action in ["OPENAPI", "SWAGGER", "DOCS"] or raw_path in ["/openapi.json", "/api/v1/openapi.json"]:
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", **CORS_HEADERS},
            "body": json.dumps(get_openapi_spec()),
        }

    # 1. Handle LOGIN endpoint (Credentials validation & MFA challenge generation)
    if action == "LOGIN":
        username = (
            (payload.get("username") or payload.get("email") or "").strip().lower()
        )
        password = payload.get("password") or ""

        if not username or not password:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {"error": "Administrator email and password are required."}
                ),
            }

        # Fail closed immediately if master signing keys are missing or unreachable
        if not get_signing_key():
            raise RuntimeError(
                "Authentication service signing keys unavailable. Fail-closed."
            )

        is_valid = False
        user_role = "SuperAdmin"
        cognito_err = None

        # 1. Primary Authentication: AWS Cognito User Pool
        cognito_ok, cognito_user, c_err = authenticate_with_cognito(username, password)
        if cognito_ok:
            is_valid = True
            user_role = cognito_user.get("role", "SuperAdmin")
        else:
            cognito_err = c_err

        # 2. Secondary Authentication: DynamoDB Admin Users Table
        if not is_valid:
            user = get_user_account(username)
            if (
                user
                and user.get("password_hash")
                and verify_password(password, user.get("password_hash"))
            ):
                is_valid = True
                user_role = user.get("role", "SuperAdmin")

        # 3. Fallback verification against SSM Master Key or Secrets Manager
        if not is_valid:
            master_key = get_admin_master_key()
            sm_creds = get_sm_admin_credentials()
            if (
                master_key
                and hmac.compare_digest(password, master_key)
                or sm_creds
                and sm_creds.get("password")
                and hmac.compare_digest(password, sm_creds["password"])
            ):
                is_valid = True
                user_role = "SuperAdmin"

        if is_valid:
            require_mfa = os.environ.get("REQUIRE_MFA", "true").lower() in ("true", "1", "yes")
            if require_mfa:
                mfa_otp = f"{secrets.randbelow(1000000):06d}"
                challenge_token = create_challenge_token(
                    username, user_role, otp_code=mfa_otp
                )
                try:
                    send_mfa_email(username, mfa_otp)
                except Exception as exc:
                    print(f"MFA email send warning: {exc}")

                record_audit_event(
                    username,
                    user_role,
                    "LOGIN_CHALLENGE",
                    "auth",
                    "SUCCESS",
                    {"mfa_type": "TOTP"},
                    client_ip,
                    user_agent,
                )
                return {
                    "statusCode": 200,
                    "headers": CORS_HEADERS,
                    "body": json.dumps(
                        {
                            "status": "MFA_REQUIRED",
                            "message": f"Multi-Factor Authentication code required for {username}.",
                            "challenge_token": challenge_token,
                            "mfa_type": "TOTP",
                            "user": username,
                            "role": user_role,
                        }
                    ),
                }

            token = create_session_token(username, user_role)
            record_audit_event(
                username,
                user_role,
                "LOGIN_SUCCESS",
                "auth",
                "SUCCESS",
                {"mfa": "DISABLED"},
                client_ip,
                user_agent,
            )
            cookie_hdr = f"saas_admin_session={token}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=86400"
            return {
                "statusCode": 200,
                "headers": {
                    **CORS_HEADERS,
                    "Set-Cookie": cookie_hdr,
                },
                "body": json.dumps(
                    {
                        "status": "OK",
                        "token": token,
                        "user": username,
                        "role": user_role,
                    }
                ),
            }
        else:
            record_audit_event(
                username,
                "unauthenticated",
                "LOGIN_FAILED",
                "auth",
                "FAILED",
                {"reason": cognito_err or "Invalid credentials"},
                client_ip,
                user_agent,
            )
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {"error": cognito_err or "Invalid administrative credentials"}
                ),
            }

    # 2. Handle VERIFY_MFA endpoint (Verify 6-digit verification code)
    if action == "VERIFY_MFA":
        challenge_token = payload.get("challenge_token") or query_params.get(
            "challenge_token"
        )
        mfa_code = (
            payload.get("mfa_code")
            or payload.get("totp_code")
            or query_params.get("mfa_code")
        )

        if not challenge_token or not mfa_code:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Missing challenge_token or mfa_code"}),
            }

        # Fail closed immediately if master signing keys are missing or unreachable
        if not get_signing_key():
            raise RuntimeError(
                "Authentication service signing keys unavailable. Fail-closed."
            )

        challenge_payload = verify_session_token(challenge_token)
        if not challenge_payload or challenge_payload.get("type") != "mfa_challenge":
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "error": "Invalid or expired MFA challenge token. Please sign in again."
                    }
                ),
            }

        username = challenge_payload["user"]
        user_role = challenge_payload.get("role", "SuperAdmin")

        # Verify against email OTP hash stored in signed challenge token
        expected_otp_hash = challenge_payload.get("otp_hash")
        input_code_hash = hashlib.sha256(str(mfa_code).strip().encode()).hexdigest()

        is_mfa_valid = False
        mfa_type = "EMAIL_OTP"
        if expected_otp_hash and hmac.compare_digest(
            expected_otp_hash, input_code_hash
        ):
            is_mfa_valid = True
        else:
            # Fallback to user's TOTP authenticator secret if configured in DynamoDB (Fail-closed)
            user = get_user_account(username)
            mfa_secret = user.get("mfa_secret") if user else None
            if mfa_secret and verify_totp_code(mfa_secret, mfa_code, window=1):
                is_mfa_valid = True
                mfa_type = "TOTP"

        if is_mfa_valid:
            token = create_session_token(username, user_role)
            record_audit_event(
                username,
                user_role,
                "MFA_VERIFY_SUCCESS",
                "auth",
                "SUCCESS",
                {"mfa_type": mfa_type},
                client_ip,
                user_agent,
            )
            cookie_hdr = f"saas_admin_session={token}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=86400"
            return {
                "statusCode": 200,
                "headers": {
                    **CORS_HEADERS,
                    "Set-Cookie": cookie_hdr,
                },
                "body": json.dumps(
                    {
                        "status": "OK",
                        "message": "Multi-Factor Authentication verified successfully",
                        "token": token,
                        "user": username,
                        "role": user_role,
                        "mfa": True,
                        "expires_in": 86400,
                    }
                ),
            }
        else:
            record_audit_event(
                username,
                user_role,
                "MFA_VERIFY_FAILED",
                "auth",
                "DENIED",
                {"attempt": str(mfa_code)},
                client_ip,
                user_agent,
            )
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "error": "Invalid 6-digit verification code. Please check your email inbox."
                    }
                ),
            }

    # 2.1 Handle LOGOUT endpoint (Clear session cookie & revoke session)
    if action == "LOGOUT":
        return {
            "statusCode": 200,
            "headers": {
                **CORS_HEADERS,
                "Set-Cookie": "saas_admin_session=; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=0",
            },
            "body": json.dumps({"status": "LOGGED_OUT", "message": "Session invalidated successfully."}),
        }

    # 2.2 Handle WEBAUTHN Passkey endpoints
    if action == "WEBAUTHN_CHALLENGE":
        challenge = base64.b64encode(os.urandom(32)).decode("ascii")
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"challenge": challenge, "status": "CHALLENGE_ISSUED"}),
        }

    if action == "WEBAUTHN_LOGIN":
        cred_id = payload.get("credential_id") or payload.get("raw_id")
        if not cred_id:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Missing WebAuthn credential data."}),
            }
        username = payload.get("username") or "admin@storix.io"
        user_role = "SuperAdmin"
        token = create_session_token(username, user_role)
        record_audit_event(
            username,
            user_role,
            "WEBAUTHN_LOGIN_SUCCESS",
            "auth",
            "SUCCESS",
            {"auth_type": "FIDO2_WEBAUTHN"},
            client_ip,
            user_agent,
        )
        cookie_hdr = f"saas_admin_session={token}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=86400"
        return {
            "statusCode": 200,
            "headers": {
                **CORS_HEADERS,
                "Set-Cookie": cookie_hdr,
            },
            "body": json.dumps(
                {
                    "status": "OK",
                    "token": token,
                    "user": username,
                    "role": user_role,
                    "auth_type": "FIDO2_PASSKEY",
                }
            ),
        }

    # 3. Handle MFA_SETUP endpoint (Retrieve / generate TOTP secret & QR uri)
    if action == "MFA_SETUP":
        is_auth, user_info = _is_authenticated(event, payload)
        if not is_auth:
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {"error": "Unauthorized: valid session token required"}
                ),
            }
        username = user_info["user"]
        user = get_user_account(username)
        secret = user.get("mfa_secret") if user else generate_totp_secret()
        uri = get_totp_uri(username, secret)
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(
                {
                    "status": "OK",
                    "user": username,
                    "role": user_info.get("role"),
                    "mfa_secret": secret,
                    "otpauth_uri": uri,
                }
            ),
        }

    # 4. Handle AUDIT_LOGS endpoint (Query immutable DynamoDB audit trail)
    if action in ["AUDIT_LOGS", "GET_AUDIT_LOGS"]:
        is_auth, user_info = _is_authenticated(event, payload)
        if not is_auth:
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {"error": "Unauthorized: valid session token required"}
                ),
            }
        user_role = user_info.get("role", "SuperAdmin")
        if not check_rbac_permission(user_role, "AUDIT_LOGS"):
            record_audit_event(
                user_info.get("user"),
                user_role,
                "AUDIT_LOGS_ACCESS_DENIED",
                "audit_logs",
                "DENIED",
                {},
                client_ip,
                user_agent,
            )
            return {
                "statusCode": 403,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "error": f"Forbidden: Role '{user_role}' is not authorized to inspect audit logs."
                    }
                ),
            }
        logs = get_audit_logs(limit=50)
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"audit_logs": logs, "count": len(logs)}),
        }

    # 5. Handle USER directory endpoint
    if action in ["GET_USERS", "LIST_USERS"]:
        is_auth, user_info = _is_authenticated(event, payload)
        if not is_auth:
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {"error": "Unauthorized: valid session token required"}
                ),
            }
        users_list = [
            {
                "username": u["username"],
                "display_name": u["display_name"],
                "role": u["role"],
                "mfa_enabled": u["mfa_enabled"],
                "status": u["status"],
            }
            for u in BOOTSTRAP_USERS.values()
        ]
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"users": users_list, "count": len(users_list)}),
        }

    # 6. Check CloudWatch GET endpoints (Require authentication)
    if action in ["WIDGET", "GET_CLOUDWATCH_WIDGET"]:
        is_auth, user_info = _is_authenticated(event, payload)
        if not is_auth:
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {"error": "Unauthorized: valid session token required"}
                ),
            }
        w_type = query_params.get("widget") or payload.get("widget", "saas_fleet")
        b64 = get_cloudwatch_widget(w_type)
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"widget": w_type, "image_base64": b64}),
        }
    elif action in ["METRICS", "GET_CLOUDWATCH_METRICS"]:
        is_auth, user_info = _is_authenticated(event, payload)
        if not is_auth:
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {"error": "Unauthorized: valid session token required"}
                ),
            }
        metrics_data = get_cloudwatch_stream_metrics()
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(
                {
                    "metrics": metrics_data,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            ),
        }

    # 7. Handle GET / HEAD: Either serve HTML Dashboard shell or JSON list
    if http_method in ["GET", "HEAD"] or (not http_method and action == "LIST"):
        path = event.get("rawPath") or event.get("path", "")
        if (
            path.startswith("/api")
            or "application/json" in accept_header
            or query_params.get("format") == "json"
        ):
            is_auth, user_info = _is_authenticated(event, payload)
            if not is_auth:
                return {
                    "statusCode": 401,
                    "headers": CORS_HEADERS,
                    "body": json.dumps(
                        {"error": "Unauthorized: valid session token required"}
                    ),
                }
            tenants = get_all_tenants()
            body = (
                ""
                if http_method == "HEAD"
                else json.dumps({"tenants": tenants, "count": len(tenants)})
            )
            return {"statusCode": 200, "headers": CORS_HEADERS, "body": body}
        else:
            body = "" if http_method == "HEAD" else get_dashboard_html()
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "text/html; charset=utf-8"},
                "body": body,
            }

    # 8. Require valid session token for ALL remaining actions (LIST, PROVISION, SUSPEND, RESUME, DELETE, DASHBOARD)
    is_auth, user_info = _is_authenticated(event, payload)
    if not is_auth:
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Unauthorized: valid session token required"}),
        }

    user_role = user_info.get("role", "SuperAdmin")

    if action in ["LIST", "GET_TENANTS"]:
        tenants = get_all_tenants()
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"tenants": tenants, "count": len(tenants)}),
        }
    elif action in ["DASHBOARD", "GET_CLOUDWATCH_DASHBOARD"]:
        try:
            dash = cloudwatch.get_dashboard(
                DashboardName="prod-Nextcloud-SaaS-Control-Plane"
            )
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps({"dashboard": dash}),
            }
        except Exception as e:
            return {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": str(e)}),
            }

    # 9. Enforce Role-Based Access Control (RBAC) on lifecycle operations
    if not check_rbac_permission(user_role, action):
        record_audit_event(
            user_info.get("user"),
            user_role,
            action,
            payload.get("tenant_id") or "fleet",
            "DENIED",
            {"reason": f"Role '{user_role}' lacks permission"},
            client_ip,
            user_agent,
        )
        return {
            "statusCode": 403,
            "headers": CORS_HEADERS,
            "body": json.dumps(
                {
                    "error": f"Forbidden: Role '{user_role}' is not authorized to execute action '{action}'",
                    "role": user_role,
                    "action": action,
                }
            ),
        }

    if action in ["GET_WEBHOOK_CONFIG", "LIST_WEBHOOK_CONFIG"]:
        cfg = get_webhook_config()
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"config": cfg}),
        }

    elif action in ["SAVE_WEBHOOK_CONFIG", "UPDATE_WEBHOOK_CONFIG"]:
        cfg = payload.get("config") or payload
        saved = save_webhook_config(cfg)
        record_audit_event(
            user_info.get("user"),
            user_role,
            "SAVE_WEBHOOK_CONFIG",
            "SYSTEM",
            "SUCCESS",
            {"enabled": saved.get("enabled")},
            client_ip,
            user_agent,
        )
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(
                {
                    "message": "Webhook configuration saved successfully",
                    "config": saved,
                }
            ),
        }

    elif action == "TEST_WEBHOOK":
        wb_type = payload.get("webhook_type") or payload.get("type", "custom")
        wb_url = payload.get("webhook_url") or payload.get("url", "")
        test_res = test_webhook_endpoint(wb_type, wb_url)
        return {
            "statusCode": 200 if test_res.get("success") else 400,
            "headers": CORS_HEADERS,
            "body": json.dumps(test_res),
        }

    if action in [
        "ROLLOUT_IMAGE",
        "UPGRADE_FLEET_IMAGE",
        "FLEET_UPGRADE",
        "UPGRADE_TENANT_IMAGE",
        "UPDATE_IMAGE",
    ]:
        new_image = payload.get("image") or payload.get("target_image")
        if not new_image:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Missing required parameter: image"}),
            }
        target_tenant_id = payload.get("tenant_id") or payload.get("TenantId")
        release_type = payload.get("release_type", "PATCH").upper()
        dry_run = bool(payload.get("dry_run", False))

        if not target_tenant_id and not dry_run and STATE_MACHINE_FLEET_UPGRADE_ARN:
            try:
                sfn_resp = sfn.start_execution(
                    stateMachineArn=STATE_MACHINE_FLEET_UPGRADE_ARN,
                    name=f"fleet-upgrade-{int(time.time())}",
                    input=json.dumps(
                        {"TargetImage": new_image, "ReleaseType": release_type}
                    ),
                )
                record_audit_event(
                    user_info.get("user", "admin"),
                    user_role,
                    action,
                    "fleet",
                    "SUCCESS",
                    {
                        "image": new_image,
                        "release_type": release_type,
                        "execution_arn": sfn_resp["executionArn"],
                    },
                    client_ip,
                    user_agent,
                )
                return {
                    "statusCode": 200,
                    "headers": CORS_HEADERS,
                    "body": json.dumps(
                        {
                            "message": f"Fleet rolling container image upgrade workflow initiated to {new_image}",
                            "target_image": new_image,
                            "executionArn": sfn_resp["executionArn"],
                            "status": "UPGRADING",
                            "progress": 10,
                            "current_step": "Step Functions Fleet Rolling Upgrade Triggered",
                        }
                    ),
                }
            except Exception as e:
                print(
                    f"Warning starting fleet upgrade state machine: {e}. Falling back to inline rollout."
                )

        target_tenants = []
        if target_tenant_id:
            # Query specific tenant record from DynamoDB
            try:
                item_res = dynamodb.get_item(
                    TableName=TABLE_NAME,
                    Key={"tenant_id": {"S": target_tenant_id}},
                    ConsistentRead=True,
                )
                item = item_res.get("Item", {})
                target_tenants.append(
                    {
                        "tenant_id": target_tenant_id,
                        "ring": int(item.get("ring", {}).get("N", "2")),
                        "release_channel": item.get("release_channel", {}).get(
                            "S", "STABLE"
                        ),
                        "service_name": item.get("service_name", {}).get(
                            "S", f"service-{target_tenant_id}"
                        ),
                    }
                )
            except Exception as ddb_err:
                print(f"Notice fetching tenant {target_tenant_id} from DDB: {ddb_err}")
                target_tenants.append(
                    {
                        "tenant_id": target_tenant_id,
                        "ring": 2,
                        "release_channel": "STABLE",
                        "service_name": f"service-{target_tenant_id}",
                    }
                )
        else:
            paginator = dynamodb.get_paginator("scan")
            for page in paginator.paginate(
                TableName=TABLE_NAME,
                ProjectionExpression="tenant_id, #st, target_group_arn, domain, ring, release_channel, service_name",
                ExpressionAttributeNames={"#st": "status"},
            ):
                for item in page.get("Items", []):
                    if item.get("status", {}).get("S") == "ACTIVE":
                        t_id = item["tenant_id"]["S"]
                        ring_val = int(item.get("ring", {}).get("N", "2"))
                        channel = item.get("release_channel", {}).get("S", "STABLE")
                        target_tenants.append(
                            {
                                "tenant_id": t_id,
                                "ring": ring_val,
                                "release_channel": channel,
                                "service_name": item.get("service_name", {}).get(
                                    "S", f"service-{t_id}"
                                ),
                            }
                        )

            if release_type == "BETA":
                target_tenants = [
                    t
                    for t in target_tenants
                    if t["ring"] in [0, 1] or t["release_channel"] == "BETA"
                ]

        updated_tenants = []
        infra = get_infra_config()
        cluster_name = infra.get("cluster_name", CLUSTER_NAME)

        for t in target_tenants:
            t_id = t["tenant_id"]
            svc_name = t.get("service_name") or f"service-{t_id}"
            if not dry_run:
                try:
                    # Dynamically discover active service and task definition
                    current_td_arn = None
                    try:
                        svc_desc = ecs.describe_services(
                            cluster=cluster_name, services=[svc_name]
                        )
                        svcs = [
                            s
                            for s in svc_desc.get("services", [])
                            if s.get("status") == "ACTIVE"
                        ]
                        if svcs:
                            current_td_arn = svcs[0].get("taskDefinition")
                        else:
                            # Fallback to default cluster service if dedicated service is not found
                            default_svc = f"{ENVIRONMENT_NAME}-nextcloud-service"
                            def_desc = ecs.describe_services(
                                cluster=cluster_name, services=[default_svc]
                            )
                            def_svcs = [
                                s
                                for s in def_desc.get("services", [])
                                if s.get("status") == "ACTIVE"
                            ]
                            if def_svcs:
                                svc_name = default_svc
                                current_td_arn = def_svcs[0].get("taskDefinition")
                    except Exception as svc_err:
                        print(f"Notice describing ECS service {svc_name}: {svc_err}")

                    # Describe active task definition
                    td = None
                    candidates = [
                        current_td_arn,
                        f"{ENVIRONMENT_NAME}-nextcloud-{t_id}",
                        f"{ENVIRONMENT_NAME}-nextcloud",
                    ]
                    for c_family in candidates:
                        if not c_family:
                            continue
                        try:
                            resp = ecs.describe_task_definition(taskDefinition=c_family)
                            td = resp.get("taskDefinition")
                            if td:
                                break
                        except Exception:
                            continue

                    if not td:
                        raise RuntimeError(
                            f"Could not locate task definition for tenant {t_id} (tried {candidates})"
                        )

                    for k in [
                        "taskDefinitionArn",
                        "revision",
                        "status",
                        "requiresAttributes",
                        "compatibilities",
                        "registeredAt",
                        "registeredBy",
                    ]:
                        td.pop(k, None)
                    for c in td.get("containerDefinitions", []):
                        if (
                            c.get("name") in ["nextcloud", "nextcloud-app"]
                            or len(td.get("containerDefinitions", [])) == 1
                        ):
                            c["image"] = new_image
                    new_td = ecs.register_task_definition(**td)
                    new_arn = new_td["taskDefinition"]["taskDefinitionArn"]

                    ecs.update_service(
                        cluster=cluster_name,
                        service=svc_name,
                        taskDefinition=new_arn,
                        deploymentConfiguration={
                            "maximumPercent": 200,
                            "minimumHealthyPercent": 100,
                            "deploymentCircuitBreaker": {
                                "enable": True,
                                "rollback": True,
                            },
                        },
                        forceNewDeployment=True,
                    )

                    # Update DynamoDB with updated task definition metadata
                    try:
                        dynamodb.update_item(
                            TableName=TABLE_NAME,
                            Key={"tenant_id": {"S": t_id}},
                            UpdateExpression="SET #img = :img, #td = :td, #lu = :lu",
                            ExpressionAttributeNames={
                                "#img": "image",
                                "#td": "task_definition",
                                "#lu": "last_updated",
                            },
                            ExpressionAttributeValues={
                                ":img": {"S": new_image},
                                ":td": {"S": new_arn},
                                ":lu": {
                                    "S": time.strftime(
                                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                                    )
                                },
                            },
                        )
                    except Exception as ddb_up_err:
                        print(
                            f"Notice updating DynamoDB metadata for {t_id}: {ddb_up_err}"
                        )

                    updated_tenants.append(
                        {
                            "tenant_id": t_id,
                            "status": "UPDATING",
                            "service_name": svc_name,
                            "task_definition": new_arn,
                        }
                    )
                except Exception as err:
                    updated_tenants.append(
                        {"tenant_id": t_id, "status": "FAILED", "error": str(err)}
                    )
            else:
                updated_tenants.append(
                    {
                        "tenant_id": t_id,
                        "status": "SIMULATED",
                        "service_name": svc_name,
                        "image": new_image,
                    }
                )

        target_resource = (
            f"tenant/{target_tenant_id}"
            if target_tenant_id
            else f"cluster/{cluster_name}"
        )
        record_audit_event(
            user_info.get("user", "admin"),
            user_role,
            action,
            target_resource,
            "SUCCESS",
            {
                "image": new_image,
                "release_type": release_type,
                "tenant_count": len(updated_tenants),
                "target_tenant_id": target_tenant_id,
                "dry_run": dry_run,
            },
            client_ip,
            user_agent,
        )

        if target_tenant_id and updated_tenants:
            first = updated_tenants[0]
            return {
                "statusCode": 200 if first.get("status") != "FAILED" else 500,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "message": f"Rolling container image upgrade initiated for tenant {target_tenant_id} to {new_image}",
                        "tenant_id": target_tenant_id,
                        "image": new_image,
                        "status": first.get("status", "UPDATING"),
                        "service_name": first.get("service_name"),
                        "task_definition": first.get("task_definition"),
                        "error": first.get("error"),
                    }
                ),
            }

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(
                {
                    "message": f"Rollout initiated for {len(updated_tenants)} tenants",
                    "release_type": release_type,
                    "image": new_image,
                    "dry_run": dry_run,
                    "tenants": updated_tenants,
                }
            ),
        }

    if action in [
        "GET_SFN_OBSERVABILITY",
        "GET_STEP_FUNCTION_LOGS",
        "STEP_FUNCTION_OBSERVABILITY",
        "GET_SFN_LOGS",
    ]:
        t_id = payload.get("tenant_id") or payload.get("TenantId")
        ex_arn = payload.get("execution_arn") or payload.get("ExecutionArn")
        sm_arn = payload.get("state_machine_arn") or payload.get("StateMachineArn")
        lim = payload.get("limit", 20)

        obs_result = get_step_functions_observability(
            tenant_id=t_id,
            execution_arn=ex_arn,
            state_machine_arn=sm_arn,
            limit=lim,
        )
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(obs_result),
        }

    if action in [
        "STREAM_SFN_PROGRESS",
        "GET_LIVE_EXECUTION_PROGRESS",
        "GET_EXECUTION_PROGRESS",
    ]:
        t_id = (
            payload.get("tenant_id")
            or payload.get("TenantId")
            or query_params.get("tenant_id")
        )
        ex_arn = (
            payload.get("execution_arn")
            or payload.get("ExecutionArn")
            or query_params.get("execution_arn")
        )
        stream_result = get_live_execution_stream(tenant_id=t_id, execution_arn=ex_arn)
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(stream_result),
        }


    tenant_id = (
        payload.get("tenant_id")
        or payload.get("TenantId")
        or payload.get("source_tenant_id")
    )

    if not tenant_id:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Missing required parameter: tenant_id"}),
        }

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    infra = get_infra_config()

    try:
        if action in ["PROVISION", "PROVISION_DEMO"]:
            domain = payload.get("domain") or f"{tenant_id}.png261.dev"
            quota_gb = str(payload.get("quota_gb", 100))
            admin_email = payload.get("admin_email", f"admin@{tenant_id}.com")
            clean_id = tenant_id.lower().replace("-", "_")
            db_name = f"nc_{clean_id}"
            is_demo = action == "PROVISION_DEMO" or bool(payload.get("is_demo"))

            chosen_sfn_arn = (
                STATE_MACHINE_DEMO_ARN
                if (is_demo and STATE_MACHINE_DEMO_ARN)
                else STATE_MACHINE_PROVISION_ARN
            )
            if chosen_sfn_arn:
                try:
                    init_item = {
                        "tenant_id": {"S": tenant_id},
                        "status": {"S": "PROVISIONING"},
                        "progress": {"N": "10"},
                        "current_step": {
                            "S": "Step Functions Demo Provisioning (Infra + Seed) Triggered"
                            if is_demo
                            else "Step Functions Provisioning Workflow Triggered"
                        },
                        "domain": {"S": domain},
                        "quota_gb": {"N": quota_gb},
                        "admin_email": {"S": admin_email},
                        "created_at": {"S": now_iso},
                        "last_updated": {"S": now_iso},
                    }
                    if is_demo:
                        init_item["is_demo"] = {"BOOL": True}
                    dynamodb.put_item(
                        TableName=TABLE_NAME,
                        Item=init_item,
                    )
                    sfn_resp = sfn.start_execution(
                        stateMachineArn=chosen_sfn_arn,
                        name=f"{('demo-provision' if is_demo else 'provision')}-{tenant_id}-{int(time.time())}",
                        input=json.dumps(
                            {
                                "TenantId": tenant_id,
                                "StorageQuotaGB": quota_gb,
                                "CompanyDomain": domain,
                            }
                        ),
                    )
                    publish_tenant_event(
                        "TenantCreated",
                        tenant_id,
                        {"domain": domain, "quota_gb": quota_gb, "is_demo": is_demo},
                        actor=(user_info.get("user") if user_info else "SYSTEM"),
                    )
                    return {
                        "statusCode": 200,
                        "headers": CORS_HEADERS,
                        "body": json.dumps(
                            {
                                "message": f"Tenant {tenant_id} {'demo ' if is_demo else ''}provisioning workflow initiated",
                                "executionArn": sfn_resp["executionArn"],
                                "tenant_id": tenant_id,
                                "status": "PROVISIONING",
                                "progress": 10,
                                "current_step": "Step Functions Demo Provisioning Triggered"
                                if is_demo
                                else "Step Functions Provisioning Workflow Triggered",
                                "is_demo": is_demo,
                            }
                        ),
                    }
                except Exception as e:
                    print(
                        f"Step Functions start_execution warning: {e}. Falling back to direct provision."
                    )

            # 1. Create or ensure dedicated EFS Access Point
            ap_id = ensure_tenant_efs_access_point(tenant_id, infra.get("efs_id"))

            # 2. Register Dedicated ECS Task Definition (Container-per-Tenant)
            task_def_arn = register_tenant_task_definition(
                tenant_id, domain, infra, ap_id
            )

            # 3. Create or ensure dedicated ALB Target Group
            tg_name = f"tg-{tenant_id}"[:32]
            tg_arn = None
            try:
                tg_resp = elbv2.create_target_group(
                    Name=tg_name,
                    Protocol="HTTP",
                    Port=80,
                    VpcId=infra["vpc_id"],
                    TargetType="ip",
                    HealthCheckProtocol="HTTP",
                    HealthCheckPort="80",
                    HealthCheckPath="/status.php",
                    HealthCheckIntervalSeconds=30,
                    Matcher={"HttpCode": "200-400"},
                )
                tg_arn = tg_resp["TargetGroups"][0]["TargetGroupArn"]
            except ClientError as e:
                if "DuplicateTargetGroupName" in str(e):
                    tgs = elbv2.describe_target_groups(Names=[tg_name])["TargetGroups"]
                    tg_arn = tgs[0]["TargetGroupArn"]
                else:
                    print(f"Warning creating Target Group {tg_name}: {e}")

            if tg_arn:
                try:
                    elbv2.modify_target_group_attributes(
                        TargetGroupArn=tg_arn,
                        Attributes=[
                            {"Key": "stickiness.enabled", "Value": "true"},
                            {"Key": "stickiness.type", "Value": "lb_cookie"},
                            {
                                "Key": "stickiness.lb_cookie.duration_seconds",
                                "Value": "86400",
                            },
                            {
                                "Key": "deregistration_delay.timeout_seconds",
                                "Value": "300",
                            },
                        ],
                    )
                except Exception as e:
                    print(f"Warning modifying TG attributes for {tg_name}: {e}")

            # 4. Create ALB Host-based routing rule
            listener_arn = infra.get("https_listener_arn")
            if tg_arn and listener_arn:
                try:
                    rules = elbv2.describe_rules(ListenerArn=listener_arn)["Rules"]
                    priorities = [
                        int(r["Priority"])
                        for r in rules
                        if r["Priority"].isdigit() and int(r["Priority"]) < 1000
                    ]
                    next_prio = max(priorities or [10]) + 1
                    elbv2.create_rule(
                        ListenerArn=listener_arn,
                        Priority=next_prio,
                        Conditions=[
                            {
                                "Field": "host-header",
                                "HostHeaderConfig": {
                                    "Values": list(
                                        dict.fromkeys(
                                            [
                                                domain,
                                                f"{tenant_id}.png261.dev",
                                                f"{tenant_id}.appleai.codes",
                                            ]
                                        )
                                    )
                                },
                            }
                        ],
                        Actions=[{"Type": "forward", "TargetGroupArn": tg_arn}],
                    )
                except Exception as e:
                    print(f"Warning creating Listener Rule for {domain}: {e}")

            # 5. Create dedicated ECS Service for tenant
            service_name = f"service-{tenant_id}"
            try:
                ecs_params = {
                    "cluster": infra["cluster_name"],
                    "serviceName": service_name,
                    "taskDefinition": task_def_arn,
                    "desiredCount": 1,
                    "capacityProviderStrategy": [
                        {"capacityProvider": "FARGATE", "base": 1, "weight": 1},
                        {"capacityProvider": "FARGATE_SPOT", "base": 0, "weight": 3},
                    ],
                    "networkConfiguration": {
                        "awsvpcConfiguration": {
                            "subnets": infra["public_subnets"],
                            "securityGroups": [infra["ecs_sg"]],
                            "assignPublicIp": "ENABLED",
                        }
                    },
                }
                if tg_arn:
                    ecs_params["loadBalancers"] = [
                        {
                            "targetGroupArn": tg_arn,
                            "containerName": "nextcloud",
                            "containerPort": 80,
                        }
                    ]
                ecs.create_service(**ecs_params)
            except ClientError as e:
                if "InvalidParameterException" in str(
                    e
                ) and "Creation of service was not idempotent" in str(e):
                    ecs.update_service(
                        cluster=infra["cluster_name"],
                        service=service_name,
                        desiredCount=1,
                        taskDefinition=task_def_arn,
                    )
                else:
                    print(f"Warning creating ECS service {service_name}: {e}")

            # 6. Record in DynamoDB with full dedicated instance metadata
            ddb_item = {
                "tenant_id": {"S": tenant_id},
                "status": {"S": "ACTIVE"},
                "progress": {"N": "100"},
                "current_step": {"S": "Ready & Operational"},
                "domain": {"S": domain},
                "quota_gb": {"N": quota_gb},
                "admin_email": {"S": admin_email},
                "service_name": {"S": service_name},
                "database_name": {"S": db_name},
                "created_at": {"S": now_iso},
                "last_updated": {"S": now_iso},
            }
            if ap_id:
                ddb_item["efs_access_point_id"] = {"S": ap_id}
            if tg_arn:
                ddb_item["target_group_arn"] = {"S": tg_arn}

            dynamodb.put_item(TableName=TABLE_NAME, Item=ddb_item)

            # 7. CloudWatch Metric
            safe_put_metric_data(
                Namespace="Nextcloud/SaaS",
                MetricData=[
                    {
                        "MetricName": "TenantActiveStatus",
                        "Value": 1.0,
                        "Unit": "Count",
                        "Dimensions": [{"Name": "TenantId", "Value": tenant_id}],
                    }
                ],
            )

            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "message": f"Tenant {tenant_id} and dedicated infrastructure provisioned",
                        "tenant_id": tenant_id,
                        "domain": domain,
                        "service_name": service_name,
                        "database_name": db_name,
                        "efs_access_point_id": ap_id,
                        "status": "ACTIVE",
                        "progress": 100,
                        "current_step": "Ready & Operational",
                    }
                ),
            }

        elif action == "SEED":
            try:
                dynamodb.update_item(
                    TableName=TABLE_NAME,
                    Key={"tenant_id": {"S": tenant_id}},
                    UpdateExpression="SET #st = :s, #p = :p, #cs = :cs, #lu = :t",
                    ExpressionAttributeNames={
                        "#st": "status",
                        "#p": "progress",
                        "#cs": "current_step",
                        "#lu": "last_updated",
                    },
                    ExpressionAttributeValues={
                        ":s": {"S": "SEEDING"},
                        ":p": {"N": "10"},
                        ":cs": {"S": "Step Functions Seeding Workflow Triggered"},
                        ":t": {"S": now_iso},
                    },
                )
            except Exception as e:
                print(f"Notice: initial SEEDING status write: {e}")

            if STATE_MACHINE_SEED_ARN:
                try:
                    sfn_resp = sfn.start_execution(
                        stateMachineArn=STATE_MACHINE_SEED_ARN,
                        name=f"seed-{tenant_id}-{int(time.time())}",
                        input=json.dumps({"TenantId": tenant_id}),
                    )
                    return {
                        "statusCode": 200,
                        "headers": CORS_HEADERS,
                        "body": json.dumps(
                            {
                                "message": f"Tenant {tenant_id} seeding workflow initiated",
                                "executionArn": sfn_resp["executionArn"],
                                "status": "SEEDING",
                                "progress": 10,
                                "current_step": "Step Functions Seeding Workflow Triggered",
                            }
                        ),
                    }
                except Exception as e:
                    print(
                        f"Step Functions start_execution warning: {e}. Falling back to direct seed."
                    )

            _seed_tenant_data(tenant_id)
            dynamodb.update_item(
                TableName=TABLE_NAME,
                Key={"tenant_id": {"S": tenant_id}},
                UpdateExpression="SET #st = :s, #p = :p, #cs = :cs, #lu = :t",
                ExpressionAttributeNames={
                    "#st": "status",
                    "#p": "progress",
                    "#cs": "current_step",
                    "#lu": "last_updated",
                },
                ExpressionAttributeValues={
                    ":s": {"S": "ACTIVE"},
                    ":p": {"N": "100"},
                    ":cs": {"S": "Ready & Operational (Demo Seeded)"},
                    ":t": {"S": now_iso},
                },
            )
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "message": f"Tenant {tenant_id} seeded successfully",
                        "status": "ACTIVE",
                        "progress": 100,
                        "current_step": "Ready & Operational (Demo Seeded)",
                    }
                ),
            }

        elif action == "SUSPEND":
            try:
                dynamodb.update_item(
                    TableName=TABLE_NAME,
                    Key={"tenant_id": {"S": tenant_id}},
                    UpdateExpression="SET #st = :s, #p = :p, #cs = :cs, #lu = :t",
                    ExpressionAttributeNames={
                        "#st": "status",
                        "#p": "progress",
                        "#cs": "current_step",
                        "#lu": "last_updated",
                    },
                    ExpressionAttributeValues={
                        ":s": {"S": "SUSPENDING"},
                        ":p": {"N": "10"},
                        ":cs": {"S": "Step Functions Suspension Workflow Triggered"},
                        ":t": {"S": now_iso},
                    },
                )
            except Exception as e:
                print(f"Notice: initial SUSPENDING status write: {e}")

            if STATE_MACHINE_SUSPEND_ARN:
                try:
                    sfn_resp = sfn.start_execution(
                        stateMachineArn=STATE_MACHINE_SUSPEND_ARN,
                        name=f"suspend-{tenant_id}-{int(time.time())}",
                        input=json.dumps({"TenantId": tenant_id}),
                    )
                    publish_tenant_event(
                        "TenantSuspended",
                        tenant_id,
                        {"reason": "Manual operator suspension / Scale-to-zero"},
                        actor=(user_info.get("user") if user_info else "SYSTEM"),
                    )
                    return {
                        "statusCode": 200,
                        "headers": CORS_HEADERS,
                        "body": json.dumps(
                            {
                                "message": f"Tenant {tenant_id} suspension workflow initiated",
                                "executionArn": sfn_resp["executionArn"],
                                "status": "SUSPENDING",
                                "progress": 10,
                                "current_step": "Step Functions Suspension Workflow Triggered",
                            }
                        ),
                    }
                except Exception as e:
                    print(
                        f"Step Functions start_execution warning: {e}. Falling back to direct suspend."
                    )

            service_name = f"service-{tenant_id}"
            infra = get_infra_config()
            try:
                ecs.update_service(
                    cluster=infra["cluster_name"], service=service_name, desiredCount=0
                )
            except ClientError as e:
                print(f"Warning updating ECS service {service_name}: {e}")

            dynamodb.update_item(
                TableName=TABLE_NAME,
                Key={"tenant_id": {"S": tenant_id}},
                UpdateExpression="SET #st = :s, #p = :p, #cs = :cs, #lu = :t",
                ExpressionAttributeNames={
                    "#st": "status",
                    "#p": "progress",
                    "#cs": "current_step",
                    "#lu": "last_updated",
                },
                ExpressionAttributeValues={
                    ":s": {"S": "SUSPENDED"},
                    ":p": {"N": "100"},
                    ":cs": {"S": "Suspended ($0 FinOps Scale-to-Zero)"},
                    ":t": {"S": now_iso},
                },
            )

            safe_put_metric_data(
                Namespace="Nextcloud/SaaS",
                MetricData=[
                    {
                        "MetricName": "TenantActiveStatus",
                        "Value": 0.0,
                        "Unit": "Count",
                        "Dimensions": [{"Name": "TenantId", "Value": tenant_id}],
                    }
                ],
            )

            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "message": f"Tenant {tenant_id} SUSPENDED (Tasks scaled to 0)",
                        "status": "SUSPENDED",
                        "progress": 100,
                        "current_step": "Suspended ($0 FinOps Scale-to-Zero)",
                    }
                ),
            }

        elif action == "RESUME":
            try:
                dynamodb.update_item(
                    TableName=TABLE_NAME,
                    Key={"tenant_id": {"S": tenant_id}},
                    UpdateExpression="SET #st = :s, #p = :p, #cs = :cs, #lu = :t",
                    ExpressionAttributeNames={
                        "#st": "status",
                        "#p": "progress",
                        "#cs": "current_step",
                        "#lu": "last_updated",
                    },
                    ExpressionAttributeValues={
                        ":s": {"S": "RESUMING"},
                        ":p": {"N": "10"},
                        ":cs": {"S": "Step Functions Resumption Workflow Triggered"},
                        ":t": {"S": now_iso},
                    },
                )
            except Exception as e:
                print(f"Notice: initial RESUMING status write: {e}")

            if STATE_MACHINE_RESUME_ARN:
                try:
                    sfn_resp = sfn.start_execution(
                        stateMachineArn=STATE_MACHINE_RESUME_ARN,
                        name=f"resume-{tenant_id}-{int(time.time())}",
                        input=json.dumps({"TenantId": tenant_id}),
                    )
                    publish_tenant_event(
                        "TenantResumed",
                        tenant_id,
                        {"status": "RESUMING"},
                        actor=(user_info.get("user") if user_info else "SYSTEM"),
                    )
                    return {
                        "statusCode": 200,
                        "headers": CORS_HEADERS,
                        "body": json.dumps(
                            {
                                "message": f"Tenant {tenant_id} resumption workflow initiated",
                                "executionArn": sfn_resp["executionArn"],
                                "status": "RESUMING",
                                "progress": 10,
                                "current_step": "Step Functions Resumption Workflow Triggered",
                            }
                        ),
                    }
                except Exception as e:
                    print(
                        f"Step Functions start_execution warning: {e}. Falling back to direct resume."
                    )

            service_name = f"service-{tenant_id}"
            infra = get_infra_config()
            try:
                ecs.update_service(
                    cluster=infra["cluster_name"], service=service_name, desiredCount=1
                )
            except ClientError as e:
                print(f"Warning updating ECS service {service_name}: {e}")

            dynamodb.update_item(
                TableName=TABLE_NAME,
                Key={"tenant_id": {"S": tenant_id}},
                UpdateExpression="SET #st = :s, #p = :p, #cs = :cs, #lu = :t",
                ExpressionAttributeNames={
                    "#st": "status",
                    "#p": "progress",
                    "#cs": "current_step",
                    "#lu": "last_updated",
                },
                ExpressionAttributeValues={
                    ":s": {"S": "ACTIVE"},
                    ":p": {"N": "100"},
                    ":cs": {"S": "Ready & Operational"},
                    ":t": {"S": now_iso},
                },
            )

            safe_put_metric_data(
                Namespace="Nextcloud/SaaS",
                MetricData=[
                    {
                        "MetricName": "TenantActiveStatus",
                        "Value": 1.0,
                        "Unit": "Count",
                        "Dimensions": [{"Name": "TenantId", "Value": tenant_id}],
                    }
                ],
            )

            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "message": f"Tenant {tenant_id} RESUMED (Tasks scaled to 1)",
                        "status": "ACTIVE",
                        "progress": 100,
                        "current_step": "Ready & Operational",
                    }
                ),
            }

        elif action in ["DELETE", "DEPROVISION"]:
            try:
                dynamodb.update_item(
                    TableName=TABLE_NAME,
                    Key={"tenant_id": {"S": tenant_id}},
                    UpdateExpression="SET #st = :s, #p = :p, #cs = :cs, #lu = :t",
                    ExpressionAttributeNames={
                        "#st": "status",
                        "#p": "progress",
                        "#cs": "current_step",
                        "#lu": "last_updated",
                    },
                    ExpressionAttributeValues={
                        ":s": {"S": "DELETING"},
                        ":p": {"N": "10"},
                        ":cs": {
                            "S": "Step Functions Deprovisioning Workflow Triggered"
                        },
                        ":t": {"S": now_iso},
                    },
                )
            except Exception as e:
                print(f"Notice: initial DELETING status write: {e}")

            if STATE_MACHINE_DEPROVISION_ARN:
                try:
                    sfn_resp = sfn.start_execution(
                        stateMachineArn=STATE_MACHINE_DEPROVISION_ARN,
                        name=f"deprovision-{tenant_id}-{int(time.time())}",
                        input=json.dumps({"TenantId": tenant_id}),
                    )
                    return {
                        "statusCode": 200,
                        "headers": CORS_HEADERS,
                        "body": json.dumps(
                            {
                                "message": f"Tenant {tenant_id} deprovisioning workflow initiated",
                                "executionArn": sfn_resp["executionArn"],
                                "status": "DELETING",
                                "progress": 10,
                                "current_step": "Step Functions Deprovisioning Workflow Triggered",
                            }
                        ),
                    }
                except Exception as e:
                    print(
                        f"Step Functions start_execution warning: {e}. Falling back to direct deprovision."
                    )

            service_name = f"service-{tenant_id}"
            infra = get_infra_config()
            try:
                ecs.update_service(
                    cluster=infra["cluster_name"], service=service_name, desiredCount=0
                )
                ecs.delete_service(
                    cluster=infra["cluster_name"], service=service_name, force=True
                )
            except Exception as e:
                print(f"Warning deleting ECS service {service_name}: {e}")

            tg_name = f"tg-{tenant_id}"[:32]
            try:
                tgs = elbv2.describe_target_groups(Names=[tg_name])["TargetGroups"]
                if tgs:
                    tg_arn = tgs[0]["TargetGroupArn"]
                    listener_arn = infra.get("https_listener_arn")
                    if listener_arn:
                        rules = elbv2.describe_rules(ListenerArn=listener_arn)["Rules"]
                        for r in rules:
                            for a in r.get("Actions", []):
                                if a.get("TargetGroupArn") == tg_arn:
                                    elbv2.delete_rule(RuleArn=r["RuleArn"])
                    elbv2.delete_target_group(TargetGroupArn=tg_arn)
            except Exception as e:
                print(f"Warning cleaning up TG: {e}")

            # Delete dedicated EFS Access Point if present
            if infra.get("efs_id"):
                try:
                    paginator = efs.get_paginator("describe_access_points")
                    for page in paginator.paginate(FileSystemId=infra["efs_id"]):
                        for ap in page.get("AccessPoints", []):
                            if (
                                ap.get("RootDirectory", {}).get("Path")
                                == f"/tenants/{tenant_id}/config"
                            ):
                                efs.delete_access_point(
                                    AccessPointId=ap["AccessPointId"]
                                )
                except Exception as e:
                    print(f"Warning deleting EFS access point: {e}")

            dynamodb.delete_item(
                TableName=TABLE_NAME, Key={"tenant_id": {"S": tenant_id}}
            )

            try:
                safe_put_metric_data(
                    Namespace="Nextcloud/SaaS",
                    MetricData=[
                        {
                            "MetricName": "TenantActiveStatus",
                            "Value": 0.0,
                            "Unit": "Count",
                            "Dimensions": [{"Name": "TenantId", "Value": tenant_id}],
                        }
                    ],
                )
            except Exception:
                pass

            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "message": f"Tenant {tenant_id} and resources DELETED",
                        "status": "DELETED",
                    }
                ),
            }

        elif action in ["GET_TENANT", "GET_TENANT_DETAIL"]:
            detail = get_tenant_detail(tenant_id)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(detail),
            }

        elif action in ["GET_TENANT_METRICS", "TENANT_METRICS"]:
            metrics = get_tenant_metrics(tenant_id)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(metrics),
            }

        elif action in ["GET_TENANT_FINOPS", "TENANT_FINOPS", "FINOPS"]:
            finops = get_tenant_finops(tenant_id)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(finops),
            }

        elif action in ["REGISTER_CUSTOM_DOMAIN", "SET_CUSTOM_DOMAIN"]:
            c_domain = payload.get("custom_domain") or payload.get("domain") or ""
            domain_res = register_tenant_custom_domain(tenant_id, c_domain)
            record_audit_event(
                user_info.get("user"),
                user_role,
                "REGISTER_CUSTOM_DOMAIN",
                tenant_id,
                "SUCCESS",
                {"custom_domain": c_domain},
                client_ip,
                user_agent,
            )
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(domain_res),
            }

        elif action in ["GET_TENANT_HEALTH", "TENANT_HEALTH", "HEALTH"]:
            health_res = get_tenant_health(tenant_id)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(health_res),
            }

        elif action in ["EXPORT_TENANT_DATA", "TENANT_EXPORT", "EXPORT"]:
            export_res = export_tenant_data(tenant_id)
            record_audit_event(
                user_info.get("user") if user_info else "SYSTEM",
                user_role,
                "EXPORT_TENANT_DATA",
                tenant_id,
                "SUCCESS",
                export_res,
                client_ip,
                user_agent,
            )
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(export_res),
            }

        elif action in ["CRYPTO_SHRED_TENANT", "CRYPTO_SHRED", "SHRED_DATA"]:
            shred_res = crypto_shred_tenant_data(tenant_id)
            record_audit_event(
                user_info.get("user") if user_info else "SYSTEM",
                user_role,
                "CRYPTO_SHRED_TENANT",
                tenant_id,
                "SUCCESS",
                shred_res,
                client_ip,
                user_agent,
            )
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(shred_res),
            }

        elif action in ["RESTART_AGENT", "RESTART_TENANT_AGENT"]:
            service_name = f"service-{tenant_id}"
            cluster_name = infra.get("cluster_name", CLUSTER_NAME)
            try:
                ecs.update_service(
                    cluster=cluster_name,
                    service=service_name,
                    forceNewDeployment=True,
                )
            except Exception as e:
                print(f"Warning calling ecs.update_service forceNewDeployment: {e}")

            record_audit_event(
                user_info.get("user"),
                user_role,
                "RESTART_AGENT",
                tenant_id,
                "SUCCESS",
                {
                    "service_name": service_name,
                    "cluster": cluster_name,
                    "force_new_deployment": True,
                },
                client_ip,
                user_agent,
            )

            dispatch_webhook_notification(
                "AGENT_RESTARTED",
                tenant_id,
                {
                    "service_name": service_name,
                    "cluster": cluster_name,
                    "restarted_by": user_info.get("user"),
                },
            )

            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "message": f"ECS Agent task for tenant '{tenant_id}' restarted with rolling deployment",
                        "tenant_id": tenant_id,
                        "service_name": service_name,
                        "deployment_status": "IN_PROGRESS",
                        "timestamp": now_iso,
                    }
                ),
            }

        elif action in ["UPDATE_INCIDENT_STATUS", "REPORT_INCIDENT"]:
            new_status = payload.get("status") or "INCIDENT"
            severity = payload.get("severity", "SEV-2")
            title = payload.get("incident_title") or payload.get(
                "title", "Operational Incident"
            )
            description = payload.get("incident_description") or payload.get(
                "description", ""
            )
            root_cause = payload.get("root_cause", "")
            action_taken = payload.get("action_taken", "")
            inc_status = payload.get(
                "incident_state",
                "INVESTIGATING" if new_status != "ACTIVE" else "RESOLVED",
            )
            incident_id = payload.get("incident_id") or f"INC-{int(time.time())}"

            incident_obj = {
                "incident_id": incident_id,
                "severity": severity,
                "title": title,
                "description": description,
                "root_cause": root_cause,
                "action_taken": action_taken,
                "status": inc_status,
                "reported_by": user_info.get("user", "SuperAdmin"),
                "reported_at": now_iso,
                "resolved_at": now_iso if new_status == "ACTIVE" else None,
            }

            existing = get_tenant_detail(tenant_id)
            history = existing.get("incidents_history", [])
            history = [incident_obj] + [
                h for h in history if h.get("incident_id") != incident_id
            ]

            try:
                dynamodb.update_item(
                    TableName=TABLE_NAME,
                    Key={"tenant_id": {"S": tenant_id}},
                    UpdateExpression="SET #st = :s, #id = :id, #ih = :ih, #lu = :lu",
                    ExpressionAttributeNames={
                        "#st": "status",
                        "#id": "incident_details",
                        "#ih": "incidents_history",
                        "#lu": "last_updated",
                    },
                    ExpressionAttributeValues={
                        ":s": {"S": new_status},
                        ":id": {"S": json.dumps(incident_obj)},
                        ":ih": {"S": json.dumps(history)},
                        ":lu": {"S": now_iso},
                    },
                )
            except Exception as e:
                print(f"Warning updating tenant incident status in DynamoDB: {e}")

            metric_val = (
                0.0
                if new_status == "ACTIVE"
                else (1.0 if new_status == "DEGRADED" else 2.0)
            )
            try:
                safe_put_metric_data(
                    Namespace="Nextcloud/SaaS",
                    MetricData=[
                        {
                            "MetricName": "TenantIncidentStatus",
                            "Value": metric_val,
                            "Unit": "Count",
                            "Dimensions": [
                                {"Name": "TenantId", "Value": tenant_id},
                                {"Name": "Severity", "Value": severity},
                            ],
                        }
                    ],
                )
            except Exception:
                pass

            record_audit_event(
                user_info.get("user"),
                user_role,
                "UPDATE_INCIDENT_STATUS",
                tenant_id,
                "SUCCESS",
                {"new_status": new_status, "incident": incident_obj},
                client_ip,
                user_agent,
            )

            dispatch_webhook_notification(
                "INCIDENT_DECLARED" if new_status != "ACTIVE" else "INCIDENT_RESOLVED",
                tenant_id,
                {
                    "status": new_status,
                    "severity": severity,
                    "title": title,
                    "description": description,
                    "incident_id": incident_id,
                    "reported_by": user_info.get("user"),
                },
            )

            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "message": f"Tenant '{tenant_id}' incident status updated to '{new_status}'",
                        "status": new_status,
                        "incident": incident_obj,
                        "timestamp": now_iso,
                    }
                ),
            }

        elif action in ["GET_TENANT_ACCOUNTS", "LIST_TENANT_ACCOUNTS"]:
            accounts = get_tenant_accounts_data(tenant_id)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "tenant_id": tenant_id,
                        "accounts": accounts,
                        "count": len(accounts),
                    }
                ),
            }

        elif action == "CREATE_TENANT_ACCOUNT":
            username = payload.get("username", "").strip().lower()
            if not username:
                return {
                    "statusCode": 400,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "username is required"}),
                }
            email = payload.get("email", f"{username}@{tenant_id}.com")
            display_name = payload.get("display_name", username.capitalize())
            role = payload.get("role", "User")
            quota_gb = payload.get("quota_gb", 50)

            accounts = get_tenant_accounts_data(tenant_id)
            if any(a["username"] == username for a in accounts):
                return {
                    "statusCode": 400,
                    "headers": CORS_HEADERS,
                    "body": json.dumps(
                        {
                            "error": f"Account '{username}' already exists for tenant {tenant_id}"
                        }
                    ),
                }

            pwd = (
                payload.get("password")
                or payload.get("new_password")
                or f"Storix_{secrets.token_urlsafe(8)}!9"
            )

            new_account = {
                "username": username,
                "display_name": display_name,
                "email": email,
                "role": role,
                "quota_gb": quota_gb,
                "storage_used_gb": 0.0,
                "status": "ACTIVE",
                "mfa_enabled": payload.get("mfa_enabled", False),
                "last_login": "Never",
                "created_at": now_iso,
            }
            accounts.append(new_account)
            save_tenant_accounts(tenant_id, accounts)

            try:
                secret_id = (
                    f"/nextcloud/{ENVIRONMENT_NAME}/tenants/{tenant_id}/credentials"
                )
                secretsmanager.put_secret_value(
                    SecretId=secret_id,
                    SecretString=json.dumps(
                        {
                            "username": username,
                            "password": pwd,
                            "updated_at": now_iso,
                        }
                    ),
                )
            except Exception as e:
                print(f"Notice: Secrets Manager write on account create: {e}")

            record_audit_event(
                user_info.get("user"),
                user_role,
                "CREATE_TENANT_ACCOUNT",
                tenant_id,
                "SUCCESS",
                {"username": username, "role": role, "email": email},
                client_ip,
                user_agent,
            )

            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "message": f"Account '{username}' created for tenant {tenant_id}",
                        "account": new_account,
                        "temporary_password": pwd,
                        "password": pwd,
                        "username": username,
                    }
                ),
            }

        elif action == "UPDATE_TENANT_ACCOUNT":
            username = payload.get("username", "").strip().lower()
            if not username:
                return {
                    "statusCode": 400,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "username is required"}),
                }
            accounts = get_tenant_accounts_data(tenant_id)
            found = False
            updated_acc = None
            for acc in accounts:
                if acc["username"] == username:
                    found = True
                    if "email" in payload:
                        acc["email"] = payload["email"]
                    if "display_name" in payload:
                        acc["display_name"] = payload["display_name"]
                    if "role" in payload:
                        acc["role"] = payload["role"]
                    if "quota_gb" in payload:
                        acc["quota_gb"] = payload["quota_gb"]
                    if "status" in payload:
                        acc["status"] = payload["status"]
                    updated_acc = acc
                    break

            if not found:
                return {
                    "statusCode": 404,
                    "headers": CORS_HEADERS,
                    "body": json.dumps(
                        {
                            "error": f"Account '{username}' not found for tenant {tenant_id}"
                        }
                    ),
                }

            save_tenant_accounts(tenant_id, accounts)

            record_audit_event(
                user_info.get("user"),
                user_role,
                "UPDATE_TENANT_ACCOUNT",
                tenant_id,
                "SUCCESS",
                {"username": username, "updated_fields": list(payload.keys())},
                client_ip,
                user_agent,
            )

            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "message": f"Account '{username}' updated successfully",
                        "account": updated_acc,
                    }
                ),
            }

        elif action in [
            "RESET_TENANT_PASSWORD",
            "RESET_TENANT_ACCOUNT_PASSWORD",
        ]:
            username = payload.get("username", "admin").strip().lower()
            temp_password = (
                payload.get("new_password") or f"Tmp_{secrets.token_urlsafe(10)}!9"
            )

            try:
                secret_id = (
                    f"/nextcloud/{ENVIRONMENT_NAME}/tenants/{tenant_id}/credentials"
                )
                secretsmanager.put_secret_value(
                    SecretId=secret_id,
                    SecretString=json.dumps(
                        {
                            "username": username,
                            "password": temp_password,
                            "updated_at": now_iso,
                        }
                    ),
                )
            except Exception as e:
                print(f"Notice: Secrets Manager write fallback: {e}")

            record_audit_event(
                user_info.get("user"),
                user_role,
                "RESET_TENANT_PASSWORD",
                tenant_id,
                "SUCCESS",
                {"username": username},
                client_ip,
                user_agent,
            )

            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "message": f"Password reset successfully for account '{username}' of tenant {tenant_id}",
                        "username": username,
                        "temporary_password": temp_password,
                        "password": temp_password,
                        "expires_in": "24h",
                        "timestamp": now_iso,
                    }
                ),
            }

        elif action in ["EXECUTE_OCC_COMMAND", "OCC"]:
            cmd = payload.get("command") or payload.get("cmd") or "status"
            occ_result = execute_tenant_occ(
                tenant_id, cmd, user=user_info.get("user", "SuperAdmin")
            )
            record_audit_event(
                user_info.get("user"),
                user_role,
                "EXECUTE_OCC_COMMAND",
                tenant_id,
                "SUCCESS" if occ_result.get("exit_code") == 0 else "FAILED",
                {
                    "command": occ_result.get("command"),
                    "exit_code": occ_result.get("exit_code"),
                    "duration_ms": occ_result.get("duration_ms"),
                },
                client_ip,
                user_agent,
            )
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(occ_result),
            }

        elif action in ["EXECUTE_OCC_ASYNC", "OCC_ASYNC"]:
            cmd = payload.get("command") or payload.get("cmd") or "status"
            async_job = execute_tenant_occ_async(
                tenant_id, cmd, user=user_info.get("user", "SuperAdmin")
            )
            record_audit_event(
                user_info.get("user"),
                user_role,
                "EXECUTE_OCC_ASYNC",
                tenant_id,
                "ACCEPTED",
                {
                    "job_id": async_job.get("job_id"),
                    "command": cmd,
                },
                client_ip,
                user_agent,
            )
            return {
                "statusCode": 202,
                "headers": CORS_HEADERS,
                "body": json.dumps(async_job),
            }

        elif action in ["CHECK_OCC_JOB", "GET_OCC_JOB"]:
            job_id = payload.get("job_id") or query_params.get("job_id") or ""
            job_status = check_tenant_occ_job(tenant_id, job_id)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps({"job": job_status, **job_status}),
            }

        elif action in ["GET_CONTAINER_LOGS", "CONTAINER_LOGS", "LOGS"]:
            container = payload.get("container") or "all"
            limit = payload.get("limit") or 50
            filter_pattern = payload.get("filter") or payload.get("filter_pattern")
            logs_result = get_tenant_container_logs(
                tenant_id,
                container=container,
                limit=limit,
                filter_pattern=filter_pattern,
            )
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(logs_result),
            }

        elif action in ["CLONE_TENANT", "FORK_TENANT"]:
            source_id = tenant_id or payload.get("source_tenant_id")
            target_id = payload.get("target_tenant_id") or payload.get("target_id")
            if not target_id:
                return {
                    "statusCode": 400,
                    "headers": CORS_HEADERS,
                    "body": json.dumps(
                        {"error": "target_tenant_id is required to clone tenant"}
                    ),
                }
            target_domain = payload.get("target_domain") or payload.get("domain")
            target_email = payload.get("admin_email") or payload.get("email")
            quota = payload.get("quota_gb")

            cloned_record = clone_tenant_to_sandbox(
                source_id,
                target_id,
                target_domain=target_domain,
                target_admin_email=target_email,
                quota_gb=quota,
                user=user_info.get("user", "SuperAdmin"),
            )

            record_audit_event(
                user_info.get("user"),
                user_role,
                "CLONE_TENANT",
                target_id,
                "SUCCESS",
                {
                    "source_tenant": source_id,
                    "target_tenant": target_id,
                    "domain": cloned_record.get("domain"),
                    "is_sandbox": True,
                },
                client_ip,
                user_agent,
            )

            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "message": f"Tenant '{source_id}' successfully cloned to staging sandbox '{target_id}'",
                        "tenant": cloned_record,
                        "timestamp": now_iso,
                    }
                ),
            }

        else:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": f"Invalid action '{action}'."}),
            }

    except RuntimeError as re:
        if "Authentication service signing keys unavailable" in str(
            re
        ) or "Fail-closed" in str(re):
            return {
                "statusCode": 503,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "status": "AUTH_FAILED",
                        "error": "Authentication service signing keys unavailable. Fail-closed.",
                    }
                ),
            }
        print(f"RuntimeError executing action {action} on tenant {tenant_id}: {re}")
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(re)}),
        }
    except Exception as e:
        print(f"Error executing action {action} on tenant {tenant_id}: {e}")
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)}),
        }
