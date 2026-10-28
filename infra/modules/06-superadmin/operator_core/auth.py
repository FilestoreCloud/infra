"""
Storix Control Plane — Authentication & Access Control Module
Handles JWT/HMAC tokens, PBKDF2 password verification, TOTP MFA, Cognito fallback, and RBAC.
"""

import base64
import datetime
import hashlib
import hmac
import json
import logging
import os
import secrets
import struct
import time
import uuid
from typing import Any, Dict, Optional, Tuple


from operator_core.common import (
    ADMIN_USERS_TABLE,
    AUDIT_LOGS_TABLE,
    ENVIRONMENT_NAME,
    dynamodb,
    secretsmanager,
    unmarshal_ddb_item,
)

logger = logging.getLogger(__name__)

# RBAC Permissions Matrix
RBAC_PERMISSIONS: Dict[str, list] = {
    "SUPER_ADMIN": ["*"],
    "OPERATOR": [
        "tenants:read",
        "tenants:write",
        "tenants:suspend",
        "tenants:resume",
        "tenants:clone",
        "tenants:provision",
        "occ:execute",
        "observability:read",
        "audit:read",
        "webhooks:read",
        "webhooks:write",
    ],
    "AUDITOR": [
        "tenants:read",
        "observability:read",
        "audit:read",
        "webhooks:read",
    ],
}


def check_rbac_permission(role: str, action: str) -> bool:
    """Verifies whether role possesses permission for action."""
    permissions = RBAC_PERMISSIONS.get(role, [])
    if "*" in permissions or action in permissions:
        return True
    return False


def generate_totp_secret() -> str:
    """Generates Base32-compatible secret for TOTP MFA."""
    return base64.b32encode(secrets.token_bytes(20)).decode("utf-8")


def generate_totp_code(secret: str, time_step: Optional[int] = None) -> str:
    """Generates standard RFC 6238 TOTP 6-digit code."""
    if time_step is None:
        time_step = int(time.time() // 30)
    try:
        key = base64.b32decode(secret, casefold=True)
    except Exception:
        key = secret.encode("utf-8")
    msg = struct.pack(">Q", time_step)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = (
        ((h[offset] & 0x7F) << 24)
        | ((h[offset + 1] & 0xFF) << 16)
        | ((h[offset + 2] & 0xFF) << 8)
        | (h[offset + 3] & 0xFF)
    )
    return f"{code % 1000000:06d}"


def verify_totp_code(secret: str, code: str, window: int = 1) -> bool:
    """Validates TOTP code against secret within drifting time window."""
    if not secret or not code:
        return False
    current_step = int(time.time() // 30)
    for offset in range(-window, window + 1):
        if generate_totp_code(secret, current_step + offset) == code.strip():
            return True
    return False


def get_totp_uri(username: str, secret: str, issuer: str = "NextcloudSaaS") -> str:
    """Builds otpauth URI for QR code generation."""
    return f"otpauth://totp/{issuer}:{username}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"


def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Hashes password with PBKDF2-HMAC-SHA256 (100,000 iterations)."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
    ).hex()
    return f"{salt}:{hashed}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifies password matches PBKDF2 stored hash or SHA256."""
    try:
        password = (password or "").strip()
        sep = ":" if ":" in stored_hash else ("$" if "$" in stored_hash else None)
        if sep:
            salt, expected_h = stored_hash.split(sep, 1)
            h = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
            )
            if hmac.compare_digest(h.hex(), expected_h) or hmac.compare_digest(f"{salt}{sep}{h.hex()}", stored_hash):
                return True
        if len(stored_hash) == 64:
            if hmac.compare_digest(hashlib.sha256(password.encode("utf-8")).hexdigest(), stored_hash):
                return True
    except Exception:
        pass
    return False


def get_user_account(username: str) -> Optional[Dict[str, Any]]:
    """Retrieves user record from DynamoDB or creates fallback SuperAdmin."""
    try:
        resp = dynamodb.get_item(
            TableName=ADMIN_USERS_TABLE,
            Key={"username": {"S": username}},
        )
        if "Item" in resp:
            return unmarshal_ddb_item(resp["Item"])
    except Exception as exc:
        logger.warning("Failed querying admin-users table: %s", exc)

    # Built-in Master Admin fallback from Secrets Manager or default
    if username == "admin":
        master_pwd = "StorixAdmin2026!Secure"
        master_email = "admin@storix.cloud"
        try:
            sec = secretsmanager.get_secret_value(SecretId=f"/nextcloud/{ENVIRONMENT_NAME}/secrets/admin-credentials")
            creds = json.loads(sec.get("SecretString", "{}"))
            if creds.get("password"):
                master_pwd = creds["password"]
            if creds.get("email"):
                master_email = creds["email"]
        except Exception:
            pass
        return {
            "username": "admin",
            "passwordHash": hash_password(master_pwd),
            "role": "SUPER_ADMIN",
            "email": master_email,
            "mfaEnabled": False,
        }
    return None


def record_audit_event(
    event_type: str,
    action: str,
    actor: str,
    resource_id: str = "",
    status: str = "SUCCESS",
    ip_address: str = "127.0.0.1",
    user_agent: str = "Unknown",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Persists immutable audit log entry to DynamoDB."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    log_id = f"aud-{uuid.uuid4().hex[:16]}"
    item = {
        "logId": {"S": log_id},
        "timestamp": {"S": now},
        "eventType": {"S": event_type},
        "action": {"S": action},
        "actor": {"S": actor},
        "resourceId": {"S": resource_id or "fleet"},
        "status": {"S": status},
        "ipAddress": {"S": ip_address},
        "userAgent": {"S": user_agent},
        "ttl": {"N": str(int(time.time() + (90 * 86400)))},  # 90 days retention
    }
    if metadata:
        item["metadata"] = {"S": json.dumps(metadata)}

    try:
        dynamodb.put_item(TableName=AUDIT_LOGS_TABLE, Item=item)
    except Exception as exc:
        logger.warning("Failed writing audit event to DynamoDB: %s", exc)


def get_audit_logs(limit: int = 50) -> list:
    """Scans and retrieves latest audit logs."""
    try:
        resp = dynamodb.scan(TableName=AUDIT_LOGS_TABLE, Limit=limit)
        items = [unmarshal_ddb_item(i) for i in resp.get("Items", [])]
        items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return items
    except Exception as exc:
        logger.error("Failed scanning audit logs: %s", exc)
        return []


def uuid_v4() -> str:
    """Generates clean UUID string."""
    import uuid
    return str(uuid.uuid4())


def get_sm_admin_credentials() -> Dict[str, Any]:
    """Retrieves admin credentials from Secrets Manager."""
    secret_name = f"/nextcloud/{ENVIRONMENT_NAME}/secrets/admin-credentials"
    try:
        resp = secretsmanager.get_secret_value(SecretId=secret_name)
        return json.loads(resp.get("SecretString", "{}"))
    except Exception:
        return {"username": "admin", "password": "StorixAdmin2026!Secure"}


def get_signing_key() -> bytes:
    """Retrieves HMAC signing key."""
    master = os.environ.get("SESSION_SECRET")
    if not master:
        creds = get_sm_admin_credentials()
        master = str(creds.get("password") or "StorixSessionDefaultKey2026!")
    return hashlib.sha256(master.encode("utf-8")).digest()


def create_session_token(username: str, role: Optional[str] = None, key: Optional[bytes] = None) -> str:
    """Issues HMAC-SHA256 authenticated session token."""
    if key is None:
        key = get_signing_key()
    if role is None:
        user = get_user_account(username)
        role = user.get("role", "SUPER_ADMIN") if user else "SUPER_ADMIN"

    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload_data = {
        "sub": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + (24 * 3600),  # 24 hours
        "iss": "StorixControlPlane",
    }
    payload = base64.urlsafe_b64encode(json.dumps(payload_data).encode()).decode().rstrip("=")
    signature = hmac.new(key, f"{header}.{payload}".encode(), hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{header}.{payload}.{sig}"


def verify_session_token(token: str, key: Optional[bytes] = None) -> Optional[Dict[str, Any]]:
    """Validates session token signature and expiration."""
    if not token or token.count(".") != 2:
        return None
    if key is None:
        key = get_signing_key()

    header, payload, sig = token.split(".")
    try:
        expected_sig = base64.urlsafe_b64encode(
            hmac.new(key, f"{header}.{payload}".encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        if not hmac.compare_digest(sig, expected_sig):
            return None

        # Pad base64 if needed
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode())
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception as exc:
        logger.debug("Token verification failure: %s", exc)
        return None


def extract_token(event: Dict[str, Any], payload: Dict[str, Any]) -> str:
    """Extracts bearer token from headers or body."""
    headers = event.get("headers", {})
    # ALB / API Gateway headers can be mixed case
    auth_header = (
        headers.get("authorization")
        or headers.get("Authorization")
        or headers.get("x-auth-token")
        or headers.get("X-Auth-Token")
        or ""
    )
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return auth_header or payload.get("token", "")


def is_authenticated(event: Dict[str, Any], payload: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Verifies caller session."""
    token = extract_token(event, payload)
    if not token:
        return False, None
    claims = verify_session_token(token)
    if not claims:
        return False, None
    return True, claims
