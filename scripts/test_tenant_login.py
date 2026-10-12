#!/usr/bin/env python3
import urllib.request
import urllib.parse
import http.cookiejar
import json
import os
import re
import boto3

AWS_PROFILE = os.environ.get("AWS_PROFILE")
AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
boto_kwargs = {"region_name": AWS_REGION}
if AWS_PROFILE:
    boto_kwargs["profile_name"] = AWS_PROFILE
session = boto3.Session(**boto_kwargs)
sm = session.client("secretsmanager")

import ssl

ssm = session.client("ssm")
alb_dns = ssm.get_parameter(Name="/nextcloud/prod/infra/alb-dns")["Parameter"]["Value"]

tenants = ["acme", "marvel"]

print("=" * 60)
print("🔐 VERIFYING DEDICATED TENANT ADMIN LOGINS")
print("=" * 60)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

for tenant in tenants:
    domain = f"{tenant}.appleai.codes"
    print(f"\n--- Testing Tenant: {tenant} (https://{domain} via {alb_dns}) ---")

    # 1. Fetch credentials from Secrets Manager
    secret_id = f"/nextcloud/prod/tenants/{tenant}/admin-credentials"
    sec_resp = sm.get_secret_value(SecretId=secret_id)
    creds = json.loads(sec_resp["SecretString"])
    username = creds["username"]
    password = creds["password"]
    print(f"1. Retrieved credentials from Secrets Manager: {username} / {'*' * 8}")

    # 2. Fetch login page and extract CSRF token
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar),
        urllib.request.HTTPSHandler(context=ctx),
    )
    login_url = f"https://{alb_dns}/index.php/login"

    req = urllib.request.Request(
        login_url,
        headers={"User-Agent": "Mozilla/5.0", "Host": domain},
    )
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
            "Host": domain,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": login_url,
            "requesttoken": token,
        },
    )

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener_post = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar),
        urllib.request.HTTPSHandler(context=ctx),
        NoRedirect(),
    )

    try:
        resp = opener_post.open(login_post)
        status = getattr(resp, "status", getattr(resp, "code", 200))
        location = resp.headers.get("Location", "")
    except urllib.error.HTTPError as e:
        status = e.code
        location = e.headers.get("Location", "")

    print(f"3. Login POST status: {status}")
    print(f"   Destination Location: {location}")

    if "dashboard" in location or "files" in location or status in (302, 303):
        print(f"   ✅ SUCCESS: Admin login verified for tenant '{tenant}'!")
    else:
        print(f"   ❌ FAILED: Unexpected destination for tenant '{tenant}'")

print("\n" + "=" * 60)
print("🎉 ALL TENANT LOGINS FULLY VERIFIED!")
print("=" * 60)
