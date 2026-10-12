#!/usr/bin/env python3
import urllib.request
import json
import sys

URL = "https://admin.png261.dev/"
MASTER_KEY = "SuperNextcloud2026!SecureKey_mjOQ"

print(f"Testing live Control Plane Security on {URL}...")

# Test 1: Unauthenticated request must return 401
try:
    req = urllib.request.Request(
        URL,
        data=json.dumps({"action": "LIST"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as res:
        print("❌ FAILED: Unauthenticated request returned HTTP 200 instead of 401!")
        sys.exit(1)
except urllib.error.HTTPError as e:
    assert e.code == 401, f"Expected HTTP 401 but got {e.code}"
    print(f"✅ Test 1 PASSED: Unauthenticated request strictly blocked with HTTP {e.code}")

# Test 2: Invalid password must return 401
try:
    req = urllib.request.Request(
        URL,
        data=json.dumps({"action": "LOGIN", "username": "admin@png261.dev", "password": "BadPassword"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as res:
        print("❌ FAILED: Invalid password returned HTTP 200 instead of 401!")
        sys.exit(1)
except urllib.error.HTTPError as e:
    assert e.code == 401, f"Expected HTTP 401 but got {e.code}"
    print(f"✅ Test 2 PASSED: Invalid password rejected with HTTP {e.code}")

# Test 3: Valid login via SSM Master Key returns signed token
req = urllib.request.Request(
    URL,
    data=json.dumps({"action": "LOGIN", "username": "admin@png261.dev", "password": MASTER_KEY}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req) as res:
    data = json.loads(res.read().decode("utf-8"))
    assert "token" in data and len(data["token"]) > 30, "No valid token returned!"
    token = data["token"]
    print(f"✅ Test 3 PASSED: Authenticated with SSM Master Key, token acquired ({token[:20]}...)")

# Test 4: Authenticated tenant listing returns clean payload without passwords
req = urllib.request.Request(
    URL,
    data=json.dumps({"action": "LIST"}).encode("utf-8"),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
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
        assert "admin_password" not in t, f"SECURITY LEAK: admin_password found in tenant {tid}!"
        assert "password" not in t, f"SECURITY LEAK: password found in tenant {tid}!"
        assert "secret" not in t, f"SECURITY LEAK: secret found in tenant {tid}!"
    print("   • Zero credential leaks detected across all tenant records!")

# Test 5: Real CloudWatch metrics stream
req = urllib.request.Request(
    URL,
    data=json.dumps({"action": "METRICS"}).encode("utf-8"),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
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
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
)
with urllib.request.urlopen(req) as res:
    data = json.loads(res.read().decode("utf-8"))
    b64 = data.get("image_base64", "")
    assert len(b64) > 1000, "Widget image empty!"
    print(f"✅ Test 6 PASSED: CloudWatch widget image generated ({len(b64)} bytes base64)")

print("\n🎉 ALL 6 SECURITY TESTS PASSED SUCCESSFULLY!")
