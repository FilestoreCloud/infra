"""Test Nextcloud File Drop (Upload-only) and Password-protected public links."""

from __future__ import annotations

import uuid
import requests


def test_file_drop_upload_only_public_link(tenant_fixture):
    """Verify Nextcloud 'File Drop' (permissions=4): Anonymous users can upload files but cannot list or view them."""
    suffix = uuid.uuid4().hex[:6]
    drop_folder = f"inbox_drop_{suffix}"
    share_password = f"DropSecure_{suffix}!"

    # 1. Create drop folder
    res_mkcol = tenant_fixture.dav_mkcol(drop_folder)
    assert res_mkcol.status_code in (201, 405)

    share_id = None
    try:
        # 2. Create Public Share with permissions=4 (Create only / File Drop) and Password
        create_res = tenant_fixture.ocs_create_share(
            path=drop_folder,
            share_type=3,  # Public link
            permissions=4,  # File Drop / Upload-only
            password=share_password,
        )
        assert create_res.status_code == 200
        share_data = create_res.json()["ocs"]["data"]
        share_id = share_data["id"]
        token = share_data["token"]
        assert token, "Share token was not generated"

        public_dav_url = f"{tenant_fixture.base_url}/public.php/webdav"

        # 3. Anonymous upload WITHOUT password -> Must be REJECTED (HTTP 401)
        res_no_pass = requests.put(
            f"{public_dav_url}/unauthorized_doc.pdf",
            data=b"Hacked",
            auth=(token, ""),
            headers={"Host": tenant_fixture.domain},
            verify=False,
            timeout=15,
        )
        assert res_no_pass.status_code in (401, 403), (
            f"Expected 401 without password, got {res_no_pass.status_code}"
        )

        # 4. Anonymous upload WITH correct password -> Must SUCCEED (HTTP 201 or 204)
        submission_payload = b"Customer Confidential Application Form Data 2026"
        res_with_pass = requests.put(
            f"{public_dav_url}/customer_submission.pdf",
            data=submission_payload,
            auth=(token, share_password),
            headers={"Host": tenant_fixture.domain},
            verify=False,
            timeout=15,
        )
        assert res_with_pass.status_code in (201, 204), (
            f"File Drop upload failed: {res_with_pass.status_code}"
        )

        # 5. Anonymous client attempts PROPFIND (Listing directory) -> Must NOT disclose internal files
        prop_res = requests.request(
            "PROPFIND",
            f"{public_dav_url}/",
            auth=(token, share_password),
            headers={"Host": tenant_fixture.domain, "Depth": "1"},
            verify=False,
            timeout=15,
        )
        # In File Drop mode, PROPFIND either returns 403 or empty listing without file names
        if prop_res.status_code == 207:
            assert "customer_submission.pdf" not in prop_res.text, (
                "File Drop must NOT expose uploaded filenames to external contributors"
            )

        # 6. Admin verifies the uploaded file is present in their personal inbox
        admin_check = tenant_fixture.dav_get(f"{drop_folder}/customer_submission.pdf")
        assert admin_check.status_code == 200
        assert admin_check.content == submission_payload

    finally:
        # Cleanup
        if share_id:
            tenant_fixture.ocs_delete_share(share_id)
        tenant_fixture.dav_delete(drop_folder)
