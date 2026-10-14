"""Test Nextcloud granular cross-user sharing permissions (Read-only, Create, Update, Delete)."""

from __future__ import annotations

import uuid


def test_cross_user_granular_permissions(tenant_fixture):
    """Verify Nextcloud internal sharing permission enforcement between Alice (owner) and Bob (recipient).

    Permissions Bitmask:
      1: Read
      2: Update
      4: Create
      8: Delete
      16: Share
    """
    suffix = uuid.uuid4().hex[:6]
    alice_name = f"alice_{suffix}"
    bob_name = f"bob_{suffix}"
    password = f"P@ss_{suffix}_2026!"

    # 1. Provision Alice and Bob
    res_a = tenant_fixture.ocs_create_user(
        alice_name, password, f"{alice_name}@example.com", "500MB"
    )
    res_b = tenant_fixture.ocs_create_user(
        bob_name, password, f"{bob_name}@example.com", "500MB"
    )
    assert res_a.status_code == 200 and res_b.status_code == 200

    alice_client = tenant_fixture.create_sub_client(alice_name, password)
    bob_client = tenant_fixture.create_sub_client(bob_name, password)

    folder_name = f"collab_project_{suffix}"
    share_id = None

    try:
        # 2. Alice creates a project folder
        res_mkcol = alice_client.dav_mkcol(folder_name)
        assert res_mkcol.status_code in (201, 405)

        # Alice uploads a seed file
        alice_client.dav_put(
            f"{folder_name}/readme.txt", b"Project Guidelines", "text/plain"
        )

        # 3. Alice shares folder with Bob with READ-ONLY permissions (permissions=1)
        res_share = alice_client.ocs_create_internal_share(
            path=folder_name,
            share_with=bob_name,
            share_type=0,  # User share
            permissions=1,  # Read-only
        )
        assert res_share.status_code == 200
        share_id = res_share.json()["ocs"]["data"]["id"]

        # 4. Bob should be able to READ the file in the shared folder
        # Shared folders appear in the recipient's root
        bob_get_res = bob_client.dav_get(f"{folder_name}/readme.txt")
        assert bob_get_res.status_code == 200
        assert bob_get_res.content == b"Project Guidelines"

        # 5. Bob tries to UPLOAD a file with Read-only permissions -> Must be FORBIDDEN (403)
        bob_forbidden_put = bob_client.dav_put(
            f"{folder_name}/bob_unauthorized.txt", b"Hack", "text/plain"
        )
        assert bob_forbidden_put.status_code in (403, 401), (
            f"Expected HTTP 403 Forbidden for Read-Only recipient, got {bob_forbidden_put.status_code}"
        )

        # 6. Alice upgrades Bob's permissions to Read + Update + Create (permissions=7 = 1+2+4)
        update_perm_res = alice_client.ocs_update_share(share_id, permissions=7)
        assert update_perm_res.status_code == 200

        # 7. Bob tries uploading again -> Must SUCCEED (201 or 204)
        bob_allowed_put = bob_client.dav_put(
            f"{folder_name}/bob_authorized.txt", b"Bob Contribution", "text/plain"
        )
        assert bob_allowed_put.status_code in (201, 204), (
            f"Expected HTTP 201 Created after permission upgrade, got {bob_allowed_put.status_code}"
        )

        # 8. Bob tries to DELETE Alice's seed file without DELETE permission (permissions=7 lacks 8)
        bob_forbidden_del = bob_client.dav_delete(f"{folder_name}/readme.txt")
        assert bob_forbidden_del.status_code in (403, 401), (
            f"Expected HTTP 403 Forbidden on DELETE without permission 8, got {bob_forbidden_del.status_code}"
        )

        # 9. Alice grants full permissions (permissions=31 = 1+2+4+8+16)
        alice_client.ocs_update_share(share_id, permissions=31)

        # Bob can now delete files
        bob_allowed_del = bob_client.dav_delete(f"{folder_name}/bob_authorized.txt")
        assert bob_allowed_del.status_code == 204

    finally:
        # Cleanup users
        tenant_fixture.ocs_delete_user(alice_name)
        tenant_fixture.ocs_delete_user(bob_name)
