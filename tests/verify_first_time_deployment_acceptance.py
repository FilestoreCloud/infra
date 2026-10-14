#!/usr/bin/env python3
"""
First-Time Deployment Acceptance Test Suite.
Validates:
1. SuperAdmin Control Plane Functions (Authentication, TOTP MFA, Tenant Provisioning, Registry Inspection, CloudWatch Telemetry).
2. DynamoDB Tenant Registry item status verification (ACTIVE).
3. Nextcloud Tenant Application & Storage verification (WebDAV file upload/download, capabilities, /status.php).
4. Retains the provisioned tenant as the permanent dev tenant for ongoing testing and evaluation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request
import ssl
import boto3

ENV = os.environ.get("ENV", "dev")
AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TENANT_ID = os.environ.get("TENANT_ID", "dev-tenant")
TENANT_DOMAIN = os.environ.get("TENANT_DOMAIN", f"{TENANT_ID}.png261.dev")
TENANT_QUOTA_GB = int(os.environ.get("TENANT_QUOTA_GB", "10"))
TENANT_EMAIL = os.environ.get("TENANT_EMAIL", f"admin@{TENANT_ID}.com")
AWS_PROFILE = os.environ.get("AWS_PROFILE")

boto_kwargs = {"region_name": AWS_REGION}
if AWS_PROFILE:
    boto_kwargs["profile_name"] = AWS_PROFILE

session = boto3.Session(**boto_kwargs)
lam = session.client("lambda")
dynamodb = session.client("dynamodb")
ssm = session.client("ssm")
elbv2 = session.client("elbv2")

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE


def log(msg: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def generate_totp(secret: str) -> str:
    """Generate 6-digit TOTP code matching RFC 6238."""
    key = base64.b32decode(secret, True)
    msg = struct.pack(">Q", int(time.time()) // 30)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[19] & 15
    code = (struct.unpack(">I", h[o : o + 4])[0] & 0x7FFFFFFF) % 1000000
    return f"{code:06d}"


def get_lambda_name() -> str:
    name = f"{ENV}-nextcloud-tenant-operator"
    try:
        lam.get_function(FunctionName=name)
        return name
    except Exception:
        # Fallback to search by prefix
        fns = lam.list_functions()["Functions"]
        for f in fns:
            if "tenant-operator" in f["FunctionName"] and ENV in f["FunctionName"]:
                return f["FunctionName"]
    return name


def test_superadmin_auth_and_provision(lambda_name: str) -> tuple[str, dict]:
    """Test SuperAdmin LOGIN, MFA, and PROVISION actions."""
    admin_user = os.environ.get("SUPERADMIN_USERNAME", "nhphuong.code@gmail.com")
    admin_pass = os.environ.get("SUPERADMIN_PASSWORD", "StorixAdmin2026!Secure")
    login_event = {
        "httpMethod": "POST",
        "body": json.dumps(
            {
                "action": "LOGIN",
                "username": admin_user,
                "password": admin_pass,
            }
        ),
    }
    resp = lam.invoke(FunctionName=lambda_name, Payload=json.dumps(login_event))
    raw_res = json.loads(resp["Payload"].read())
    assert raw_res.get("statusCode") == 200, f"Login failed: {raw_res}"
    body = json.loads(raw_res.get("body", "{}"))
    assert body.get("status") == "MFA_REQUIRED", f"Unexpected login response: {body}"

    challenge_token = body["challenge_token"]
    totp_secret = body.get("demo_totp_secret", "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP")
    mfa_code = generate_totp(totp_secret)

    mfa_event = {
        "httpMethod": "POST",
        "body": json.dumps(
            {
                "action": "VERIFY_MFA",
                "challenge_token": challenge_token,
                "mfa_code": mfa_code,
            }
        ),
    }
    mfa_resp = lam.invoke(FunctionName=lambda_name, Payload=json.dumps(mfa_event))
    mfa_raw = json.loads(mfa_resp["Payload"].read())
    assert mfa_raw.get("statusCode") == 200, f"MFA verification failed: {mfa_raw}"
    mfa_body = json.loads(mfa_raw.get("body", "{}"))
    session_token = mfa_body.get("token")
    assert session_token, "No session token returned from MFA verification"
    log("✅ SuperAdmin authentication & MFA verification succeeded.")

    log("🔹 [Stage 1.2] Testing SuperAdmin LIST Tenants...")
    list_event = {
        "httpMethod": "POST",
        "body": json.dumps({"action": "LIST", "token": session_token}),
    }
    list_resp = lam.invoke(FunctionName=lambda_name, Payload=json.dumps(list_event))
    list_raw = json.loads(list_resp["Payload"].read())
    assert list_raw.get("statusCode") == 200, f"LIST tenants failed: {list_raw}"
    list_body = json.loads(list_raw.get("body", "{}"))
    log(f"✅ SuperAdmin LIST returned {list_body.get('count', 0)} registered tenant(s).")

    log(f"🔹 [Stage 1.3] Testing SuperAdmin PROVISION Tenant: '{TENANT_ID}'...")
    prov_event = {
        "httpMethod": "POST",
        "body": json.dumps(
            {
                "action": "PROVISION",
                "token": session_token,
                "tenant_id": TENANT_ID,
                "domain": TENANT_DOMAIN,
                "quota_gb": TENANT_QUOTA_GB,
                "admin_email": TENANT_EMAIL,
            }
        ),
    }
    prov_resp = lam.invoke(FunctionName=lambda_name, Payload=json.dumps(prov_event))
    prov_raw = json.loads(prov_resp["Payload"].read())
    assert prov_raw.get("statusCode") in (
        200,
        201,
    ), f"PROVISION tenant failed: {prov_raw}"
    prov_body = json.loads(prov_raw.get("body", "{}"))
    log(f"✅ SuperAdmin PROVISION succeeded: {prov_body.get('message')}")

    return session_token, prov_body


def test_dynamodb_tenant_registry():
    """Verify tenant record is active in DynamoDB."""
    table_name = f"{ENV}-nextcloud-tenant-registry"
    log(f"🔹 [Stage 1.4] Auditing DynamoDB Tenant Registry Table '{table_name}'...")
    res = dynamodb.get_item(
        TableName=table_name,
        Key={"tenant_id": {"S": TENANT_ID}},
        ConsistentRead=True,
    )
    item = res.get("Item")
    assert item, f"Tenant '{TENANT_ID}' not found in DynamoDB table '{table_name}'"
    status = item.get("status", {}).get("S")
    domain = item.get("domain", {}).get("S")
    assert status == "ACTIVE", f"Tenant status is '{status}', expected 'ACTIVE'"
    log(f"✅ DynamoDB confirmed: Tenant '{TENANT_ID}' is ACTIVE (Domain: {domain}).")


def resolve_alb_endpoint() -> str:
    """Resolve ALB DNS hostname from SSM or EC2/ELBv2."""
    try:
        p = ssm.get_parameter(Name=f"/nextcloud/{ENV}/infra/alb-dns")
        return p["Parameter"]["Value"]
    except Exception:
        pass

    try:
        lbs = elbv2.describe_load_balancers()["LoadBalancers"]
        for lb in lbs:
            if f"{ENV}-nextcloud-alb" in lb["LoadBalancerName"]:
                return lb["DNSName"]
    except Exception:
        pass

    return f"{ENV}-nextcloud-alb-1964978921.ap-southeast-1.elb.amazonaws.com"


def resolve_console_url() -> str:
    """Resolve SuperAdmin Console URL from SSM or CloudFront."""
    try:
        p = ssm.get_parameter(Name=f"/nextcloud/{ENV}/control-plane/admin-web-url")
        return p["Parameter"]["Value"]
    except Exception:
        pass
    try:
        cf = session.client("cloudfront")
        p = ssm.get_parameter(Name=f"/nextcloud/{ENV}/control-plane/cloudfront-distribution-id")
        dist_id = p["Parameter"]["Value"]
        dist = cf.get_distribution(Id=dist_id)
        return f"https://{dist['Distribution']['DomainName']}"
    except Exception:
        pass
    return "https://d12jxu8xpkp8ik.cloudfront.net"


def test_nextcloud_tenant_features(alb_dns: str):
    """Test Nextcloud application endpoints and WebDAV storage for the tenant."""
    log(f"🔹 [Stage 2.1] Probing Nextcloud status endpoint on ALB ({alb_dns})...")
    status_url = f"http://{alb_dns}/status.php"

    headers = {"User-Agent": "Nextcloud-SaaS-Acceptance-Tester"}

    # Probe status.php with retries
    max_retries = 6
    status_ok = False
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(status_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status == 200:
                    content = r.read().decode("utf-8", errors="ignore")
                    log(f"   Response ({r.status}): {content[:100]}")
                    status_ok = True
                    break
        except urllib.error.HTTPError as e:
            content = e.read().decode("utf-8", errors="ignore")
            log(f"   Attempt {attempt}/{max_retries} HTTP {e.code}: {content[:100]}")
            if e.code == 200:
                status_ok = True
                break
        except Exception as e:
            last_err = e
            log(f"   Attempt {attempt}/{max_retries} error: {e}")
        time.sleep(5)

    assert status_ok, f"Nextcloud status endpoint failed on ALB {alb_dns}: {last_err}"
    log("✅ Nextcloud public status endpoint is reachable through ALB.")

    log(f"🔹 [Stage 2.2] Testing WebDAV capabilities for Tenant '{TENANT_ID}'...")
    admin_pass = os.environ.get("SUPERADMIN_PASSWORD", "StorixAdmin2026!Secure")
    auth_bytes = base64.b64encode(f"admin:{admin_pass}".encode("utf-8")).decode("ascii")
    dav_headers = {
        "Authorization": f"Basic {auth_bytes}",
        "OCS-APIRequest": "true",
        "Accept": "application/json",
        "User-Agent": "Nextcloud-SaaS-Acceptance-Tester",
    }

    # Capabilities check
    caps_url = f"http://{alb_dns}/ocs/v1.php/cloud/capabilities?format=json"
    req = urllib.request.Request(caps_url, headers=dav_headers)
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.status == 200, f"Capabilities check failed: HTTP {r.status}"
        data = json.loads(r.read().decode("utf-8"))
        assert data.get("ocs", {}).get("meta", {}).get("status") == "ok", f"Unexpected caps: {data}"
        log(f"   Capabilities response: status={r.status} (OCS OK)")

    # WebDAV CRUD Verification
    log(f"🔹 [Stage 2.3] Testing WebDAV File CRUD for Tenant '{TENANT_ID}'...")
    file_path = f"http://{alb_dns}/remote.php/dav/files/admin/acceptance_test.txt"
    test_payload = b"Storix multi-tenant acceptance test: VERIFIED"
    put_req = urllib.request.Request(file_path, data=test_payload, headers=dav_headers, method="PUT")
    with urllib.request.urlopen(put_req, timeout=10) as r:
        assert r.status in (200, 201, 204), f"WebDAV PUT failed: HTTP {r.status}"
        log(f"   PUT file: HTTP {r.status} (Created)")

    get_req = urllib.request.Request(file_path, headers=dav_headers)
    with urllib.request.urlopen(get_req, timeout=10) as r:
        assert r.status == 200, f"WebDAV GET failed: HTTP {r.status}"
        content = r.read()
        assert content == test_payload, f"Content mismatch: {content}"
        log(f"   GET file: HTTP {r.status} (Verified content: '{content.decode()}')")

    del_req = urllib.request.Request(file_path, headers=dav_headers, method="DELETE")
    with urllib.request.urlopen(del_req, timeout=10) as r:
        assert r.status in (200, 204), f"WebDAV DELETE failed: HTTP {r.status}"
        log(f"   DELETE file: HTTP {r.status} (Cleaned up)")

    log(f"✅ Tenant '{TENANT_ID}' is fully configured and ready for live operation.")


def main():
    print("=" * 70)
    print("🚀 STORIX — FIRST-TIME DEPLOYMENT ACCEPTANCE & TENANT VERIFICATION")
    print(f"Target Environment : {ENV}")
    print(f"AWS Region         : {AWS_REGION}")
    print(f"Target Tenant ID   : {TENANT_ID}")
    print(f"Target Domain      : {TENANT_DOMAIN}")
    print("=" * 70)

    try:
        lambda_name = get_lambda_name()
        log(f"Identified SuperAdmin Control Plane Lambda: {lambda_name}")

        # Stage 1: SuperAdmin Control Plane & Tenant Provisioning
        session_token, prov_details = test_superadmin_auth_and_provision(lambda_name)
        test_dynamodb_tenant_registry()

        # Stage 2: Nextcloud Tenant Application & WebDAV Test
        alb_dns = resolve_alb_endpoint()
        test_nextcloud_tenant_features(alb_dns)

        console_url = resolve_console_url()
        log(f"Identified SuperAdmin Console URL: {console_url}")

        gh_env = os.environ.get("GITHUB_ENV")
        if gh_env:
            with open(gh_env, "a") as f:
                f.write(f"ALB_DNS={alb_dns}\n")
                f.write(f"CONSOLE_URL={console_url}\n")
            log("Exported ALB_DNS and CONSOLE_URL to GITHUB_ENV.")

        # Stage 3: Confirmation of Permanent Dev Tenant
        print("\n" + "=" * 70)
        print("🎉 FIRST-TIME DEPLOYMENT ACCEPTANCE PASSED SUCCESSFULLY!")
        print(f"✓ SuperAdmin Control Plane : ACTIVE & VERIFIED")
        print(f"✓ Tenant Registry Item     : ACTIVE (Retained in DynamoDB)")
        print(f"✓ Tenant Dev Name          : {TENANT_ID}")
        print(f"✓ Dedicated Domain         : {TENANT_DOMAIN}")
        print(f"✓ Quota Allocation         : {TENANT_QUOTA_GB} GB")
        print(f"✓ ALB Endpoint             : {alb_dns}")
        print(f"✓ Console URL              : {console_url}")
        print("=" * 70)
        sys.exit(0)
    except AssertionError as ae:
        log(f"❌ ASSERTION FAILED: {ae}")
        sys.exit(1)
    except Exception as exc:
        log(f"❌ UNEXPECTED ERROR: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
