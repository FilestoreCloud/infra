import os
import json
import base64
import urllib.request
import urllib.error
import pytest
import boto3

AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
AWS_PROFILE = os.environ.get("AWS_PROFILE")


ENV = os.environ.get("ENV", "dev")


def get_tenant_credentials(tenant_id: str):
    """Fetch tenant admin credentials from Secrets Manager or environment."""
    username = (
        os.environ.get(f"TENANT_{tenant_id.upper()}_USER")
        or os.environ.get("NEXTCLOUD_USER")
    )
    password = (
        os.environ.get(f"TENANT_{tenant_id.upper()}_PASSWORD")
        or os.environ.get("NEXTCLOUD_PASSWORD")
        or os.environ.get("ADMIN_PASSWORD")
    )

    if not password:
        try:
            boto_kwargs = {"region_name": AWS_REGION}
            if AWS_PROFILE:
                boto_kwargs["profile_name"] = AWS_PROFILE
            session = boto3.Session(**boto_kwargs)
            sm = session.client("secretsmanager")
            sec_resp = sm.get_secret_value(
                SecretId=f"/nextcloud/{ENV}/tenants/{tenant_id}/admin-credentials"
            )
            creds = json.loads(sec_resp["SecretString"])
            username = username or creds.get("username")
            password = creds.get("password")
        except Exception as e:
            pytest.skip(f"Could not retrieve credentials for {tenant_id}: {e}")

    if not username or not password:
        pytest.skip(f"Incomplete credentials for {tenant_id}")

    return username, password


import ssl

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE


@pytest.fixture
def tenant_fixture(request):
    tenant_id = os.environ.get("TENANT_ID")
    if not tenant_id:
        pytest.skip("TENANT_ID environment variable not provided")

    domain = (
        os.environ.get("TENANT_DOMAIN")
        or os.environ.get(f"TENANT_{tenant_id.upper()}_DOMAIN")
    )
    boto_kwargs = {"region_name": AWS_REGION}
    if AWS_PROFILE:
        boto_kwargs["profile_name"] = AWS_PROFILE
    session = boto3.Session(**boto_kwargs)
    ssm = session.client("ssm")

    if not domain:
        try:
            domain = ssm.get_parameter(Name=f"/nextcloud/{ENV}/tenants/{tenant_id}/domain")["Parameter"]["Value"]
        except Exception:
            domain = ""

    username, password = get_tenant_credentials(tenant_id)
    auth_header = (
        "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
    )

    try:
        alb_dns = ssm.get_parameter(Name=f"/nextcloud/{ENV}/infra/alb-dns")["Parameter"][
            "Value"
        ]
        connect_host = alb_dns
    except Exception:
        connect_host = domain

    return {
        "tenant_id": tenant_id,
        "domain": domain,
        "username": username,
        "auth_header": auth_header,
        "base_dav_url": f"https://{connect_host}/remote.php/dav/files/{username}",
    }


def test_tenant_propfind_directory_listing(tenant_fixture):
    """Verify WebDAV PROPFIND returns 207 Multi-Status without WAF XSS_BODY block."""
    dav_url = f"{tenant_fixture['base_dav_url']}/"
    headers = {
        "Authorization": tenant_fixture["auth_header"],
        "Host": tenant_fixture["domain"],
        "Depth": "1",
    }
    req = urllib.request.Request(dav_url, headers=headers, method="PROPFIND")
    with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
        assert resp.status == 207, f"Expected 207 Multi-Status, got {resp.status}"
        xml_data = resp.read().decode("utf-8")
        assert "multistatus" in xml_data.lower()
        assert tenant_fixture["username"] in xml_data


def test_tenant_upload_small_and_large_files(tenant_fixture):
    """Verify WebDAV PUT succeeds for small files and files > 8KB (WAF size limit exclusion)."""
    base_url = tenant_fixture["base_dav_url"]

    # 1. Test 50KB payload (exceeds default 8KB WAF SizeRestrictions_BODY)
    test_file_name = "test_pytest_large_50k.bin"
    file_url = f"{base_url}/{test_file_name}"
    payload = b"X" * (50 * 1024)

    req_put = urllib.request.Request(
        file_url,
        data=payload,
        headers={
            "Authorization": tenant_fixture["auth_header"],
            "Host": tenant_fixture["domain"],
            "Content-Type": "application/octet-stream",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req_put, context=ssl_ctx, timeout=20) as resp:
        assert resp.status in (201, 204), f"PUT 50KB failed with status {resp.status}"

    # 2. Verify file content via GET
    req_get = urllib.request.Request(
        file_url,
        headers={
            "Authorization": tenant_fixture["auth_header"],
            "Host": tenant_fixture["domain"],
        },
        method="GET",
    )
    with urllib.request.urlopen(req_get, context=ssl_ctx, timeout=15) as resp:
        assert resp.status == 200
        downloaded = resp.read()
        assert len(downloaded) == len(payload)
        assert downloaded == payload

    # 3. Clean up
    req_del = urllib.request.Request(
        file_url,
        headers={
            "Authorization": tenant_fixture["auth_header"],
            "Host": tenant_fixture["domain"],
        },
        method="DELETE",
    )
    with urllib.request.urlopen(req_del, context=ssl_ctx, timeout=15) as resp:
        assert resp.status in (204, 200)


def test_tenant_upload_code_and_sql_content(tenant_fixture):
    """Verify WebDAV PUT succeeds with SQL/script payloads without WAF SQLi_BODY or XSS_BODY block."""
    base_url = tenant_fixture["base_dav_url"]
    test_file_name = "test_pytest_code_snippet.txt"
    file_url = f"{base_url}/{test_file_name}"

    payload = (
        b"SELECT id, username, email FROM oc_users WHERE id = 'admin';\n"
        b"<script type='text/javascript'>console.log('test')</script>\n"
        b"https://example.com/api/v1/resource\n"
    )

    req_put = urllib.request.Request(
        file_url,
        data=payload,
        headers={
            "Authorization": tenant_fixture["auth_header"],
            "Host": tenant_fixture["domain"],
            "Content-Type": "text/plain",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req_put, context=ssl_ctx, timeout=20) as resp:
        assert resp.status in (201, 204), (
            f"PUT code file failed with status {resp.status}"
        )

    # Verify and cleanup
    req_del = urllib.request.Request(
        file_url,
        headers={
            "Authorization": tenant_fixture["auth_header"],
            "Host": tenant_fixture["domain"],
        },
        method="DELETE",
    )
    with urllib.request.urlopen(req_del, context=ssl_ctx, timeout=15) as resp:
        assert resp.status in (204, 200)
