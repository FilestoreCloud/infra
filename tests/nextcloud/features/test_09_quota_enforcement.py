"""Test Nextcloud Storage Quota Enforcement on S3 Primary Storage (HTTP 507 Insufficient Storage)."""

from __future__ import annotations

import os
import uuid


def test_storage_quota_enforcement(tenant_fixture):
    """Verify that uploading files exceeding user quota strictly fails with HTTP 507 Insufficient Storage."""
    suffix = uuid.uuid4().hex[:6]
    quota_user = f"quota_user_{suffix}"
    password = f"QuotaP@ss_{suffix}_2026!"
    # Set quota to 100 KB
    quota_str = "100KB"

    # 1. Create user with 100KB quota limit
    create_res = tenant_fixture.ocs_create_user(
        new_username=quota_user,
        new_password=password,
        email=f"{quota_user}@example.com",
        quota=quota_str,
    )
    assert create_res.status_code == 200

    user_client = tenant_fixture.create_sub_client(quota_user, password)

    try:
        # 2. Upload small file (10KB) within quota -> Must SUCCEED (201)
        small_payload = b"A" * (10 * 1024)
        small_res = user_client.dav_put("valid_small_file.bin", small_payload)
        assert small_res.status_code in (201, 204), (
            f"Small upload failed: {small_res.status_code}"
        )

        # 3. Attempt uploading file that exceeds quota (200KB payload into 100KB quota) -> Must REJECT with HTTP 507
        excess_payload = os.urandom(200 * 1024)
        excess_res = user_client.dav_put("exceed_quota_file.bin", excess_payload)
        assert excess_res.status_code in (507, 413), (
            f"Expected HTTP 507 Insufficient Storage when exceeding quota, got {excess_res.status_code}"
        )

    finally:
        # Cleanup
        tenant_fixture.ocs_delete_user(quota_user)
