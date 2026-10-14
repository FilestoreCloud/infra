"""Test Nextcloud OCS Sharing API: Public link shares, permissions, anonymous downloads, and revocations."""

from __future__ import annotations

import uuid
import requests


def test_public_link_share_lifecycle(tenant_fixture):
    """Verify complete lifecycle of public link sharing: creation, anonymous download, revocation."""
    unique_suffix = uuid.uuid4().hex[:6]
    filename = f"share_test_{unique_suffix}.txt"
    content = f"Confidential shared file content {unique_suffix}".encode("utf-8")

    # 1. Upload file to be shared
    put_resp = tenant_fixture.dav_put(filename, content, "text/plain")
    assert put_resp.status_code in (201, 204), "Failed to upload file for sharing test"

    share_id = None
    try:
        # 2. Create Public Link Share (shareType=3, permissions=1 Read-only)
        create_resp = tenant_fixture.ocs_create_share(
            path=filename,
            share_type=3,
            permissions=1,
        )
        assert create_resp.status_code == 200, (
            f"Share creation failed: {create_resp.status_code}"
        )
        body = create_resp.json()
        assert body["ocs"]["meta"]["statuscode"] in (100, 200), (
            f"OCS error: {body['ocs']['meta']}"
        )

        share_data = body["ocs"]["data"]
        share_id = share_data["id"]
        share_token = share_data["token"]
        assert share_token, "No share token returned in OCS response"

        # 3. Anonymous Download Test (simulate external recipient without login)
        anon_url = f"{tenant_fixture.base_url}/public.php/webdav/{filename}"
        anon_resp = requests.get(
            anon_url,
            auth=(share_token, ""),
            headers={"Host": tenant_fixture.domain},
            verify=False,
            timeout=15,
        )
        assert anon_resp.status_code == 200, (
            f"Anonymous download failed with {anon_resp.status_code}"
        )
        assert anon_resp.content == content, (
            "Downloaded content does not match shared file"
        )

        # 4. Revoke Share
        del_share_resp = tenant_fixture.ocs_delete_share(share_id)
        assert del_share_resp.status_code == 200, (
            f"Share revocation failed: {del_share_resp.status_code}"
        )

        # 5. Verify Anonymous Download is now forbidden / not found
        post_revoke_resp = requests.get(
            anon_url,
            auth=(share_token, ""),
            headers={"Host": tenant_fixture.domain},
            verify=False,
            timeout=15,
        )
        assert post_revoke_resp.status_code in (401, 404), (
            f"Revoked link should not allow access, got HTTP {post_revoke_resp.status_code}"
        )

    finally:
        # Cleanup file
        tenant_fixture.dav_delete(filename)
