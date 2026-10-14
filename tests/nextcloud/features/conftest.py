"""Pytest fixtures and helper client for Nextcloud Feature Acceptance Tests."""

from __future__ import annotations

import json
import os
import socket
from typing import Any, Dict, Optional

import boto3
import pytest
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
AWS_PROFILE = os.environ.get("AWS_PROFILE")


def _get_tenant_credentials(tenant_id: str) -> tuple[str, str]:
    """Retrieve tenant admin credentials from environment or AWS Secrets Manager."""
    prefix = f"TENANT_{tenant_id.upper()}"
    username = os.environ.get(f"{prefix}_USER", "admin")
    password = os.environ.get(f"{prefix}_PASSWORD")

    if password:
        return username, password

    try:
        boto_kwargs: Dict[str, Any] = {"region_name": AWS_REGION}
        if AWS_PROFILE:
            boto_kwargs["profile_name"] = AWS_PROFILE
        session = boto3.Session(**boto_kwargs)
        sm = session.client("secretsmanager")
        secret_id = f"/nextcloud/prod/tenants/{tenant_id}/admin-credentials"
        sec_resp = sm.get_secret_value(SecretId=secret_id)
        creds = json.loads(sec_resp["SecretString"])
        return creds.get("username", "admin"), creds.get("password", "")
    except Exception as exc:
        pytest.skip(f"Live credentials unavailable for tenant '{tenant_id}': {exc}")


def _check_connectivity(host: str, port: int = 443, timeout: float = 3.0) -> bool:
    """Check if host is reachable via TCP."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class NextcloudClient:
    """Client implementing standard Nextcloud WebDAV and OCS REST APIs."""

    def __init__(
        self,
        base_url: str,
        domain: str,
        username: str,
        password: str,
        verify_ssl: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.domain = domain
        self.username = username
        self.password = password
        self.dav_files_base = f"{self.base_url}/remote.php/dav/files/{username}"
        self.dav_trash_base = f"{self.base_url}/remote.php/dav/trash-bin/{username}"
        self.ocs_v1_base = f"{self.base_url}/ocs/v1.php"
        self.ocs_v2_base = f"{self.base_url}/ocs/v2.php"

        self.session = requests.Session()
        self.session.verify = verify_ssl
        self.session.auth = (username, password)

        # Standard Nextcloud headers
        self.session.headers.update(
            {
                "Host": self.domain,
                "OCS-APIRequest": "true",
                "Accept": "application/json",
                "User-Agent": "Nextcloud-SaaS-Acceptance-Tester/1.0",
            }
        )

        # Configure retries
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get_status(self) -> requests.Response:
        """Call Nextcloud public status endpoint."""
        url = f"{self.base_url}/status.php"
        return self.session.get(url, timeout=10)

    def get_capabilities(self) -> requests.Response:
        """Fetch server and app capabilities via OCS API."""
        url = f"{self.ocs_v1_base}/cloud/capabilities?format=json"
        return self.session.get(url, timeout=15)

    # --- WebDAV Operations ---

    def dav_propfind(self, path: str = "", depth: int = 1) -> requests.Response:
        """Execute WebDAV PROPFIND directory query."""
        clean_path = path.strip("/")
        url = (
            f"{self.dav_files_base}/{clean_path}"
            if clean_path
            else f"{self.dav_files_base}/"
        )
        headers = {"Depth": str(depth)}
        return self.session.request("PROPFIND", url, headers=headers, timeout=15)

    def dav_mkcol(self, path: str) -> requests.Response:
        """Create collection (folder) via WebDAV MKCOL."""
        url = f"{self.dav_files_base}/{path.strip('/')}"
        return self.session.request("MKCOL", url, timeout=15)

    def dav_put(
        self, path: str, content: bytes, content_type: str = "application/octet-stream"
    ) -> requests.Response:
        """Upload file via WebDAV PUT."""
        url = f"{self.dav_files_base}/{path.strip('/')}"
        headers = {"Content-Type": content_type}
        return self.session.put(url, data=content, headers=headers, timeout=30)

    def dav_get(self, path: str) -> requests.Response:
        """Download file via WebDAV GET."""
        url = f"{self.dav_files_base}/{path.strip('/')}"
        return self.session.get(url, timeout=20)

    def dav_move(
        self, src_path: str, dst_path: str, overwrite: bool = True
    ) -> requests.Response:
        """Move or rename file via WebDAV MOVE."""
        url = f"{self.dav_files_base}/{src_path.strip('/')}"
        destination = f"{self.dav_files_base}/{dst_path.strip('/')}"
        headers = {
            "Destination": destination,
            "Overwrite": "T" if overwrite else "F",
        }
        return self.session.request("MOVE", url, headers=headers, timeout=15)

    def dav_delete(self, path: str) -> requests.Response:
        """Delete file or directory via WebDAV DELETE."""
        url = f"{self.dav_files_base}/{path.strip('/')}"
        return self.session.delete(url, timeout=15)

    # --- OCS Sharing Operations ---

    def ocs_create_share(
        self,
        path: str,
        share_type: int = 3,  # 3 = Public Link
        permissions: int = 1,  # 1 = Read only
        password: Optional[str] = None,
        expire_date: Optional[str] = None,
    ) -> requests.Response:
        """Create a share link or internal share via OCS Share API."""
        url = f"{self.ocs_v2_base}/apps/files_sharing/api/v1/shares"
        data = {
            "path": f"/{path.strip('/')}",
            "shareType": share_type,
            "permissions": permissions,
        }
        if password:
            data["password"] = password
        if expire_date:
            data["expireDate"] = expire_date
        return self.session.post(url, data=data, timeout=15)

    def ocs_get_share(self, share_id: str | int) -> requests.Response:
        """Get details of a specific share."""
        url = f"{self.ocs_v2_base}/apps/files_sharing/api/v1/shares/{share_id}"
        return self.session.get(url, timeout=15)

    def ocs_delete_share(self, share_id: str | int) -> requests.Response:
        """Revoke a share."""
        url = f"{self.ocs_v2_base}/apps/files_sharing/api/v1/shares/{share_id}"
        return self.session.delete(url, timeout=15)

    def ocs_update_share(
        self,
        share_id: str | int,
        permissions: Optional[int] = None,
        password: Optional[str] = None,
        expire_date: Optional[str] = None,
    ) -> requests.Response:
        """Update existing share permissions or credentials."""
        url = f"{self.ocs_v2_base}/apps/files_sharing/api/v1/shares/{share_id}"
        data: Dict[str, Any] = {}
        if permissions is not None:
            data["permissions"] = permissions
        if password is not None:
            data["password"] = password
        if expire_date is not None:
            data["expireDate"] = expire_date
        return self.session.put(url, data=data, timeout=15)

    def ocs_create_internal_share(
        self,
        path: str,
        share_with: str,
        share_type: int = 0,  # 0 = User, 1 = Group
        permissions: int = 31,  # 31 = Read, Update, Create, Delete, Share
    ) -> requests.Response:
        """Share a file or folder with an internal tenant user or group."""
        url = f"{self.ocs_v2_base}/apps/files_sharing/api/v1/shares"
        data = {
            "path": f"/{path.strip('/')}",
            "shareType": share_type,
            "shareWith": share_with,
            "permissions": permissions,
        }
        return self.session.post(url, data=data, timeout=15)

    def dav_lock(self, path: str, timeout: int = 300) -> requests.Response:
        """Lock file via WebDAV LOCK (RFC 4918)."""
        url = f"{self.dav_files_base}/{path.strip('/')}"
        headers = {
            "Timeout": f"Second-{timeout}",
            "Content-Type": "application/xml; charset=utf-8",
        }
        body = (
            '<?xml version="1.0" encoding="utf-8" ?>\n'
            '<D:lockinfo xmlns:D="DAV:">\n'
            "  <D:lockscope><D:exclusive/></D:lockscope>\n"
            "  <D:locktype><D:write/></D:locktype>\n"
            f"  <D:owner><D:href>{self.username}</D:href></D:owner>\n"
            "</D:lockinfo>"
        )
        return self.session.request("LOCK", url, headers=headers, data=body, timeout=15)

    def dav_unlock(self, path: str, lock_token: str) -> requests.Response:
        """Unlock file via WebDAV UNLOCK (RFC 4918)."""
        url = f"{self.dav_files_base}/{path.strip('/')}"
        headers = {"Lock-Token": f"<{lock_token}>"}
        return self.session.request("UNLOCK", url, headers=headers, timeout=15)

    def dav_trashbin_list(self) -> requests.Response:
        """List files in WebDAV trashbin."""
        url = f"{self.dav_trash_base}/"
        headers = {"Depth": "1"}
        return self.session.request("PROPFIND", url, headers=headers, timeout=15)

    def dav_trashbin_delete(self, trash_id: str) -> requests.Response:
        """Permanently delete file from trashbin."""
        url = f"{self.dav_trash_base}/{trash_id.strip('/')}"
        return self.session.delete(url, timeout=15)

    def create_sub_client(self, username: str, password: str) -> NextcloudClient:
        """Instantiate an authenticated client for a secondary tenant user."""
        return NextcloudClient(
            base_url=self.base_url,
            domain=self.domain,
            username=username,
            password=password,
            verify_ssl=self.session.verify,
        )

    # --- OCS User Provisioning Operations ---

    def ocs_create_user(
        self, new_username: str, new_password: str, email: str = "", quota: str = ""
    ) -> requests.Response:
        """Provision a new user via OCS User Provisioning API."""
        url = f"{self.ocs_v1_base}/cloud/users"
        data = {
            "userid": new_username,
            "password": new_password,
            "email": email or f"{new_username}@example.com",
        }
        if quota:
            data["quota"] = quota
        return self.session.post(url, data=data, timeout=15)

    def ocs_get_user(self, target_username: str) -> requests.Response:
        """Retrieve details of a user."""
        url = f"{self.ocs_v1_base}/cloud/users/{target_username}"
        return self.session.get(url, timeout=15)

    def ocs_delete_user(self, target_username: str) -> requests.Response:
        """Delete user account."""
        url = f"{self.ocs_v1_base}/cloud/users/{target_username}"
        return self.session.delete(url, timeout=15)


@pytest.fixture(scope="session")
def tenant_fixture(request) -> NextcloudClient:
    """Fixture providing an authenticated Nextcloud client configured for the tenant."""
    tenant_id = os.environ.get("TENANT_ID", "acme")
    domain = os.environ.get(
        f"TENANT_{tenant_id.upper()}_DOMAIN", f"{tenant_id}.png261.dev"
    )

    username, password = _get_tenant_credentials(tenant_id)

    # Check for direct ALB routing from SSM parameter if domain is not directly routed
    boto_kwargs: Dict[str, Any] = {"region_name": AWS_REGION}
    if AWS_PROFILE:
        boto_kwargs["profile_name"] = AWS_PROFILE

    connect_host = domain
    try:
        session = boto3.Session(**boto_kwargs)
        ssm = session.client("ssm")
        alb_dns = ssm.get_parameter(Name="/nextcloud/prod/infra/alb-dns")["Parameter"][
            "Value"
        ]
        # If domain doesn't resolve/connect, fall back to ALB DNS
        if not _check_connectivity(domain, 443):
            connect_host = alb_dns
    except Exception:
        pass

    if not _check_connectivity(connect_host, 443):
        pytest.skip(
            f"Tenant live endpoint '{connect_host}' (Domain: {domain}) is unreachable via port 443."
        )

    base_url = f"https://{connect_host}"
    return NextcloudClient(
        base_url=base_url,
        domain=domain,
        username=username,
        password=password,
        verify_ssl=False,
    )
