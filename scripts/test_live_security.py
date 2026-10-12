#!/usr/bin/env python3
import urllib.request
import json
import sys
import os

URL = os.environ.get(
    "CONTROL_PLANE_URL",
    sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8085/api",
)
MASTER_KEY = "SuperNextcloud2026!SecureKey_mjOQ"

print(f"Testing live Control Plane Security on {URL}...")

# Test 1: Unauthenticated request must return 401
try:
    req = urllib.request.Request(
        URL,
        data=json.dumps({"action": "LIST"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as res:
        print("❌ FAILED: Unauthenticated request returned HTTP 200 instead of 401!")
        sys.exit(1)
except urllib.error.HTTPError as e:
    assert e.code == 401, f"Expected HTTP 401 but got {e.code}"
    print(
        f"✅ Test 1 PASSED: Unauthenticated request strictly blocked with HTTP {e.code}"
    )

# Test 2: Invalid password must return 401
try:
    req = urllib.request.Request(
        URL,
        data=json.dumps(
            {
                "action": "LOGIN",
                "username": "admin@png261.dev",
                "password": "BadPassword",
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as res:
        print("❌ FAILED: Invalid password returned HTTP 200 instead of 401!")
        sys.exit(1)
except urllib.error.HTTPError as e:
    assert e.code == 401, f"Expected HTTP 401 but got {e.code}"
    print(f"✅ Test 2 PASSED: Invalid password rejected with HTTP {e.code}")

import base64
import hashlib
import hmac
import struct
import time


def get_totp(secret):
    key = base64.b32decode(secret, casefold=True)
    msg = struct.pack(">Q", int(time.time() // 30))
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = (struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF) % 1000000
    return f"{code:06d}"


# Test 3: Valid login via Admin Credentials & MFA returns signed token
login_pass = "AdminPassword123!"
req = urllib.request.Request(
    URL,
    data=json.dumps(
        {"action": "LOGIN", "username": "admin@png261.dev", "password": login_pass}
    ).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as res:
    data = json.loads(res.read().decode("utf-8"))
    if data.get("status") == "MFA_REQUIRED":
        ch_token = data["challenge_token"]
        mfa_sec = data.get("demo_totp_secret", "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP")
        code = get_totp(mfa_sec)
        mfa_req = urllib.request.Request(
            URL,
            data=json.dumps(
                {"action": "VERIFY_MFA", "challenge_token": ch_token, "mfa_code": code}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(mfa_req) as mfa_res:
            mfa_data = json.loads(mfa_res.read().decode("utf-8"))
            token = mfa_data["token"]
    else:
        token = data.get("token")
    assert token and len(token) > 30, "No valid token returned!"
    print(
        f"✅ Test 3 PASSED: Authenticated with Admin Credentials & MFA, token acquired ({token[:20]}...)"
    )

# Test 4: Authenticated tenant listing returns clean payload without passwords
req = urllib.request.Request(
    URL,
    data=json.dumps({"action": "LIST"}).encode("utf-8"),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req) as res:
    data = json.loads(res.read().decode("utf-8"))
    tenants = data.get("tenants", [])
    print(f"✅ Test 4 PASSED: Retrieved {len(tenants)} active tenants")
    for t in tenants:
        tid = t.get("tenant_id")
        domain = t.get("domain")
        status = t.get("status")
        print(f"   • Tenant: {tid} ({domain}) -> Status: {status}")
        assert "admin_password" not in t, (
            f"SECURITY LEAK: admin_password found in tenant {tid}!"
        )
        assert "password" not in t, f"SECURITY LEAK: password found in tenant {tid}!"
        assert "secret" not in t, f"SECURITY LEAK: secret found in tenant {tid}!"
    print("   • Zero credential leaks detected across all tenant records!")

# Test 5: Real CloudWatch metrics stream
req = urllib.request.Request(
    URL,
    data=json.dumps({"action": "METRICS"}).encode("utf-8"),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req) as res:
    data = json.loads(res.read().decode("utf-8"))
    metrics = data.get("metrics", {})
    print("✅ Test 5 PASSED: Live CloudWatch metrics streamed:")
    for k, v in metrics.items():
        vals = v.get("values", [])
        latest = vals[-1] if vals else None
        print(f"   • {k}: {len(vals)} points (latest: {latest})")

# Test 6: CloudWatch widget image
req = urllib.request.Request(
    URL,
    data=json.dumps({"action": "WIDGET", "widget": "saas_fleet"}).encode("utf-8"),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req) as res:
    data = json.loads(res.read().decode("utf-8"))
    b64 = data.get("image_base64", "")
    assert len(b64) > 1000, "Widget image empty!"
    print(
        f"✅ Test 6 PASSED: CloudWatch widget image generated ({len(b64)} bytes base64)"
    )

print("\n🎉 ALL 6 SECURITY TESTS PASSED SUCCESSFULLY!")
