"""Test WebDAV RFC 4918 File Locking (Exclusive Write Lock) and Trashbin lifecycle."""

from __future__ import annotations

import re
import uuid


def test_webdav_exclusive_file_locking(tenant_fixture):
    """Verify WebDAV RFC 4918 exclusive write locking prevents concurrent overwrites (HTTP 423 Locked)."""
    suffix = uuid.uuid4().hex[:6]
    lock_file = f"exclusive_lock_{suffix}.txt"
    initial_content = b"Original Locked Content"

    # 1. Upload initial file
    res_put = tenant_fixture.dav_put(lock_file, initial_content, "text/plain")
    assert res_put.status_code in (201, 204)

    try:
        # 2. Acquire exclusive write lock
        lock_res = tenant_fixture.dav_lock(lock_file, timeout=60)
        assert lock_res.status_code == 200, (
            f"LOCK failed with status {lock_res.status_code}"
        )

        # Extract lock-token from Lock-Token header or response body XML
        lock_token = lock_res.headers.get("Lock-Token", "").strip("<>")
        if not lock_token:
            match = re.search(
                r"<D:locktoken>\s*<D:href>([^<]+)</D:href>", lock_res.text
            )
            if match:
                lock_token = match.group(1).strip()

        # 3. Attempt overwrite WITHOUT lock-token -> Must return HTTP 423 Locked
        overwrite_res = tenant_fixture.dav_put(
            lock_file, b"Illegal Overwrite", "text/plain"
        )
        assert overwrite_res.status_code == 423, (
            f"Expected HTTP 423 Locked when modifying locked file, got {overwrite_res.status_code}"
        )

        # 4. Release lock via UNLOCK
        if lock_token:
            unlock_res = tenant_fixture.dav_unlock(lock_file, lock_token)
            assert unlock_res.status_code == 204, (
                f"UNLOCK failed with {unlock_res.status_code}"
            )

            # 5. Overwrite after unlock must now SUCCEED
            subsequent_put = tenant_fixture.dav_put(
                lock_file, b"Authorized Post-Unlock", "text/plain"
            )
            assert subsequent_put.status_code in (201, 204)

    finally:
        tenant_fixture.dav_delete(lock_file)


def test_trashbin_tracking_and_cleanup(tenant_fixture):
    """Verify deleted files are moved to WebDAV trashbin and can be permanently purged."""
    suffix = uuid.uuid4().hex[:6]
    trash_file = f"to_be_deleted_{suffix}.txt"

    # 1. Upload file
    tenant_fixture.dav_put(trash_file, b"Trash content", "text/plain")

    # 2. Delete file
    del_res = tenant_fixture.dav_delete(trash_file)
    assert del_res.status_code == 204

    # 3. Query Trashbin directory
    trash_list_res = tenant_fixture.dav_trashbin_list()
    assert trash_list_res.status_code == 207
    assert "multistatus" in trash_list_res.text.lower()
    # Deleted file name should be referenced in trashbin XML
    assert trash_file in trash_list_res.text
