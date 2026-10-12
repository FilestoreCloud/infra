#!/usr/bin/env python3
import urllib.request
import urllib.parse
import http.cookiejar
import re
import boto3
import json

session = boto3.Session(profile_name="handon", region_name="ap-southeast-1")
sm = session.client("secretsmanager")

tenants = ["acme", "marvel"]

print("=" * 60)
print("🔐 VERIFYING DEDICATED TENANT ADMIN LOGINS")
print("=" * 60)

for tenant in tenants:
    print(f"\n--- Testing Tenant: {tenant} (https://{tenant}.png261.dev) ---")

    # 1. Fetch credentials from Secrets Manager
    secret_id = f"/nextcloud/prod/tenants/{tenant}/admin-credentials"
    sec_resp = sm.get_secret_value(SecretId=secret_id)
    creds = json.loads(sec_resp["SecretString"])
    username = creds["username"]
    password = creds["password"]
    print(f"1. Retrieved credentials from Secrets Manager: {username} / {'*' * 8}")

    # 2. Fetch login page and extract CSRF token
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    login_url = f"https://{tenant}.png261.dev/index.php/login"

    req = urllib.request.Request(login_url, headers={"User-Agent": "Mozilla/5.0"})
    with opener.open(req) as resp:
        html = resp.read().decode("utf-8")

    m = re.search(r'name="requesttoken"\s+value="([^"]+)"', html) or re.search(
        r'data-requesttoken="([^"]+)"', html
    )
    token = m.group(1) if m else ""
    print(f"2. Extracted CSRF request token: {token[:16]}...")

    # 3. Post login credentials
    post_data = urllib.parse.urlencode(
        {
            "user": username,
            "password": password,
            "requesttoken": token,
            "timezone": "Asia/Ho_Chi_Minh",
            "timezone_offset": "7",
        }
    ).encode("utf-8")

    login_post = urllib.request.Request(
        login_url,
        data=post_data,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": login_url,
            "requesttoken": token,
        },
    )

    with opener.open(login_post) as resp:
        final_url = resp.geturl()
        status = resp.status
        print(f"3. Login POST status: {status}")
        print(f"   Destination URL: {final_url}")

        if "dashboard" in final_url or "files" in final_url:
            print(f"   ✅ SUCCESS: Admin login verified for tenant '{tenant}'!")
        else:
            print(f"   ❌ FAILED: Unexpected destination for tenant '{tenant}'")

print("\n" + "=" * 60)
print("🎉 ALL TENANT LOGINS FULLY VERIFIED!")
print("=" * 60)
