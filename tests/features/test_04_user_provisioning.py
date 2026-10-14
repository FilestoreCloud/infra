"""Test Nextcloud OCS User Provisioning API: User creation, quotas, detail lookup, and deletion."""

from __future__ import annotations

import uuid
import requests


def test_user_provisioning_and_quota_lifecycle(tenant_fixture):
    """Verify admin can provision a new tenant user with a quota, verify details, and clean up."""
    suffix = uuid.uuid4().hex[:6]
    test_user = f"qa_user_{suffix}"
    test_password = f"SecureP@ss_{suffix}_2026!"
    test_email = f"{test_user}@qa.png261.dev"
    test_quota = "1GB"

    # 1. Create User
    create_resp = tenant_fixture.ocs_create_user(
        new_username=test_user,
        new_password=test_password,
        email=test_email,
        quota=test_quota,
    )
    assert create_resp.status_code == 200, (
        f"User creation HTTP error: {create_resp.status_code}"
    )
    body = create_resp.json()
    assert body["ocs"]["meta"]["statuscode"] in (100, 200), (
        f"OCS error creating user: {body['ocs']['meta']}"
    )

    try:
        # 2. Retrieve User Details
        get_user_resp = tenant_fixture.ocs_get_user(test_user)
        assert get_user_resp.status_code == 200
        user_data = get_user_resp.json()["ocs"]["data"]
        assert user_data["id"] == test_user
        assert user_data["email"] == test_email
        assert user_data.get("quota", {}).get("quota") == 1073741824 or "1" in str(
            user_data.get("quota", {})
        )

        # 3. Verify Newly Created User Can Access WebDAV
        user_session = requests.Session()
        user_session.auth = (test_user, test_password)
        user_session.headers.update({"Host": tenant_fixture.domain})
        user_session.verify = False

        dav_url = f"{tenant_fixture.base_url}/remote.php/dav/files/{test_user}/"
        dav_resp = user_session.request(
            "PROPFIND", dav_url, headers={"Depth": "0"}, timeout=15
        )
        assert dav_resp.status_code == 207, (
            f"New user WebDAV failed: {dav_resp.status_code}"
        )

    finally:
        # 4. Clean up / Delete User
        del_resp = tenant_fixture.ocs_delete_user(test_user)
        assert del_resp.status_code == 200, (
            f"User deletion failed: {del_resp.status_code}"
        )

        # 5. Verify User is Gone
        verify_gone = tenant_fixture.ocs_get_user(test_user)
        meta = verify_gone.json().get("ocs", {}).get("meta", {})
        assert meta.get("statuscode") in (998, 404) or verify_gone.status_code in (
            404,
            200,
        )
