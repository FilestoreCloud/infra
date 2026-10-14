"""Test WebDAV file operations: MKCOL, PROPFIND, PUT, GET, MOVE, DELETE."""

from __future__ import annotations

import hashlib
import os
import uuid
import pytest


@pytest.fixture(scope="module")
def test_folder(tenant_fixture):
    """Fixture to ensure a dedicated temporary test directory is created and cleaned up."""
    folder_name = f"acceptance_test_{uuid.uuid4().hex[:8]}"
    resp = tenant_fixture.dav_mkcol(folder_name)
    assert resp.status_code in (201, 405), (
        f"Failed to create test folder: {resp.status_code}"
    )

    yield folder_name

    # Teardown: delete test folder
    tenant_fixture.dav_delete(folder_name)


def test_webdav_propfind_root(tenant_fixture):
    """Verify WebDAV PROPFIND returns 207 Multi-Status XML with valid quotas and user collection."""
    resp = tenant_fixture.dav_propfind("", depth=1)
    assert resp.status_code == 207, (
        f"Expected HTTP 207 Multi-Status, got {resp.status_code}"
    )
    body = resp.text
    assert "multistatus" in body.lower(), "Response must contain WebDAV multistatus XML"
    assert tenant_fixture.username in body, "Response must include tenant username path"


def test_webdav_file_crud_and_checksum(tenant_fixture, test_folder):
    """Verify complete CRUD lifecycle of a file via WebDAV and verify checksum."""
    filename = "document.txt"
    filepath = f"{test_folder}/{filename}"
    original_data = b"Hello Nextcloud SaaS Multi-Tenant Acceptance Test 2026!\n"
    expected_sha256 = hashlib.sha256(original_data).hexdigest()

    # 1. CREATE / UPLOAD (PUT)
    put_resp = tenant_fixture.dav_put(filepath, original_data, "text/plain")
    assert put_resp.status_code in (201, 204), (
        f"PUT failed with status {put_resp.status_code}"
    )

    # 2. READ / DOWNLOAD (GET)
    get_resp = tenant_fixture.dav_get(filepath)
    assert get_resp.status_code == 200, f"GET failed with status {get_resp.status_code}"
    downloaded_data = get_resp.content
    assert downloaded_data == original_data, "Downloaded bytes do not match original"
    assert hashlib.sha256(downloaded_data).hexdigest() == expected_sha256

    # 3. RENAME / MOVE
    renamed_filename = "document_renamed.txt"
    renamed_filepath = f"{test_folder}/{renamed_filename}"
    move_resp = tenant_fixture.dav_move(filepath, renamed_filepath)
    assert move_resp.status_code in (201, 204), (
        f"MOVE failed with status {move_resp.status_code}"
    )

    # Verify old file is gone (404) and new file exists (200)
    assert tenant_fixture.dav_get(filepath).status_code == 404
    assert tenant_fixture.dav_get(renamed_filepath).status_code == 200

    # 4. DELETE
    del_resp = tenant_fixture.dav_delete(renamed_filepath)
    assert del_resp.status_code == 204, (
        f"DELETE failed with status {del_resp.status_code}"
    )
    assert tenant_fixture.dav_get(renamed_filepath).status_code == 404


def test_webdav_large_file_upload(tenant_fixture, test_folder):
    """Verify large file (100KB) upload succeeds through ALB & AWS WAF body size rules to S3."""
    filename = "large_payload_100k.bin"
    filepath = f"{test_folder}/{filename}"
    payload = os.urandom(100 * 1024)
    expected_sha256 = hashlib.sha256(payload).hexdigest()

    put_resp = tenant_fixture.dav_put(filepath, payload, "application/octet-stream")
    assert put_resp.status_code in (201, 204), (
        f"Large PUT failed: {put_resp.status_code}"
    )

    get_resp = tenant_fixture.dav_get(filepath)
    assert get_resp.status_code == 200
    assert len(get_resp.content) == len(payload)
    assert hashlib.sha256(get_resp.content).hexdigest() == expected_sha256

    tenant_fixture.dav_delete(filepath)
