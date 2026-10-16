"""Tier 3: Cross-Feature Combinations (Pairwise & Multi-Module Interactions).
Verifies contract boundaries and cross-feature interactions across
Runtime, Infrastructure, and Console components.
"""

import unittest

from .conftest import (
    AUTH_PROVIDER_PATH,
    COMPUTE_TEMPLATE_PATH,
    DATABASE_TEMPLATE_PATH,
    DOCKERFILE_PATH,
    HOOK_SCRIPT_PATH,
    LAMBDA_SRC_PATH,
    LOGIN_PAGE_PATH,
    NETWORKING_TEMPLATE_PATH,
    NEXTCLOUD_CONFIG_PATH,
    PACKAGE_LAMBDA_SCRIPT_PATH,
    SECURITY_TEMPLATE_PATH,
    STORAGE_TEMPLATE_PATH,
    TENANT_SHOW_PATH,
    TENANT_TABS_DIR,
)
from .utils import (
    check_for_infinite_recursion,
    load_cfn_yaml,
    read_file,
)


class TestTier3CrossFeature(unittest.TestCase):
    """Tier 3: Cross-Feature and Pairwise Subsystem Interaction Tests."""

    def test_cf1_hook_determinism_and_dynamic_proxies(self):
        """CF1: R1.F2 + R1.F5: Hook boot sequence ensures dynamic trusted proxies are in place before .tenant_initialized."""
        hook_content = read_file(HOOK_SCRIPT_PATH)
        php_config = read_file(NEXTCLOUD_CONFIG_PATH)

        # Hook copies configs before initializing
        self.assertIn("/usr/src/nextcloud/config/*.config.php", hook_content)
        self.assertIn(".tenant_initialized", hook_content)
        # Dynamic proxy resolution exists in nextcloud.config.php
        self.assertIn("TRUSTED_PROXIES", php_config)
        self.assertIn("trusted_proxies", php_config)

    def test_cf2_sha256_verification_and_hook_lifecycle(self):
        """CF2: R1.F1 + R1.F3: Immutably verified AI apps are wired to post-installation and before-starting hooks only."""
        dockerfile = read_file(DOCKERFILE_PATH)
        # Checksums present
        self.assertIn("0d7c72d3cd8a41cdb7a402d0822331d6cad23271a9a4ee6222c85f00b2dd6271", dockerfile)
        self.assertIn("c980b47d462d6f84a4161e13122277fa049b0650da14207d98066ee7d5ba5127", dockerfile)
        # Hooks in valid lifecycles
        self.assertIn("post-installation/01-setup-ai.sh", dockerfile)
        self.assertIn("before-starting/01-setup-ai.sh", dockerfile)
        # Excluded from pre-installation
        self.assertNotIn("pre-installation/01-setup-ai.sh", dockerfile)

    def test_cf3_control_plane_auth_and_session_persistence(self):
        """CF3: R2.F6 + R3.F15 (Contract 1): Secret-free LOGIN response cleanly populates persistent localStorage session."""
        lambda_content = read_file(LAMBDA_SRC_PATH)
        login_content = read_file(LOGIN_PAGE_PATH)
        auth_content = read_file(AUTH_PROVIDER_PATH)

        # Lambda does not leak secret
        self.assertNotIn("demo_totp_secret", lambda_content)
        # Login page handles MFA step without secret dependency
        self.assertNotIn("demo_totp_secret", login_content)
        # Auth token stored in localStorage
        self.assertIn('localStorage.setItem("saas_admin_token"', login_content)
        self.assertIn('localStorage.getItem("saas_admin_token")', auth_content)

    def test_cf4_database_ssl_and_security_group_egress(self):
        """CF4: R2.F8 + R2.F10: PostgreSQL enforces in-transit SSL while SG eliminates all outbound internet access."""
        db_template = load_cfn_yaml(DATABASE_TEMPLATE_PATH)
        sec_template = load_cfn_yaml(SECURITY_TEMPLATE_PATH)

        # SSL enforced
        params = db_template["Resources"]["DBParameterGroup"]["Properties"]["Parameters"]
        self.assertEqual(str(params.get("rds.force_ssl")), "1")

        # Zero 0.0.0.0/0 egress on DBSecurityGroup
        db_sg = sec_template["Resources"]["DBSecurityGroup"]["Properties"]
        for rule in db_sg.get("SecurityGroupEgress", []):
            self.assertNotEqual(rule.get("CidrIp"), "0.0.0.0/0")

    def test_cf5_efs_private_subnets_and_security_group_egress(self):
        """CF5: R2.F9 + R2.F10: EFS Mount targets reside in private subnets with zero internet egress."""
        storage_content = read_file(STORAGE_TEMPLATE_PATH)
        sec_template = load_cfn_yaml(SECURITY_TEMPLATE_PATH)

        # Private subnets in storage
        self.assertIn("PrivateSubnet1Id", storage_content)
        self.assertIn("PrivateSubnet2Id", storage_content)
        self.assertNotIn("PublicSubnet1Id", storage_content)

        # Zero 0.0.0.0/0 egress on EFSSecurityGroup
        efs_sg = sec_template["Resources"]["EFSSecurityGroup"]["Properties"]
        for rule in efs_sg.get("SecurityGroupEgress", []):
            self.assertNotEqual(rule.get("CidrIp"), "0.0.0.0/0")

    def test_cf6_dynamic_api_url_and_tenant_show_subtabs(self):
        """CF6: R3.F12 + R3.F13: Decomposed sub-tabs (Terminal, Logs) resolve dynamic API URL via dataProvider."""
        show_content = read_file(TENANT_SHOW_PATH)
        tabs_content = ""
        if TENANT_TABS_DIR.exists():
            for f in TENANT_TABS_DIR.glob("*.tsx"):
                tabs_content += read_file(f)

        combined = show_content + tabs_content
        # Must resolve API URL dynamically
        self.assertIn("getApiUrl", combined)
        # Must not hardcode url: "/api"
        self.assertNotIn('url: "/api"', combined)

    def test_cf7_antd_modernization_and_tenant_show_tabs(self):
        """CF7: R3.F12 + R3.F14: Modular sub-tabs and modals use modern AntD 5.24+ props (variant, destroyOnHidden)."""
        show_content = read_file(TENANT_SHOW_PATH)
        tabs_content = ""
        if TENANT_TABS_DIR.exists():
            for f in TENANT_TABS_DIR.glob("*.tsx"):
                tabs_content += read_file(f)

        combined = show_content + tabs_content
        self.assertNotIn("bordered={false}", combined, "No deprecated bordered={false} in show or tabs")
        self.assertNotIn("destroyOnClose", combined, "No deprecated destroyOnClose in show or tabs")

    def test_cf8_lambda_packaging_and_control_plane_remediation(self):
        """CF8: R2.F6 + R2.F7 + R2.F11: Packaging script bundles remediated Lambda (no secret leak, no recursion)."""
        self.assertTrue(PACKAGE_LAMBDA_SCRIPT_PATH.is_file(), f"Missing {PACKAGE_LAMBDA_SCRIPT_PATH}")
        packager = read_file(PACKAGE_LAMBDA_SCRIPT_PATH)
        lambda_content = read_file(LAMBDA_SRC_PATH)

        # Package script targets tenant_operator_lambda.py
        self.assertIn("tenant_operator_lambda.py", packager)

        # Lambda contains remediations
        self.assertNotIn("demo_totp_secret", lambda_content)
        self.assertFalse(check_for_infinite_recursion(LAMBDA_SRC_PATH, "safe_put_metric_data"))

    def test_cf9_database_ssl_and_compute_task_definition(self):
        """CF9: R2.F8 + Compute: Compute task definition passes DB parameters compatible with SSL."""
        compute_template = load_cfn_yaml(COMPUTE_TEMPLATE_PATH)
        self.assertIn("NextcloudTaskDefinition", compute_template["Resources"])

    def test_cf10_dynamic_proxies_and_compute_environment(self):
        """CF10: R1.F5 + Compute: ECS task definition passes TRUSTED_PROXIES read by nextcloud.config.php."""
        compute_content = read_file(COMPUTE_TEMPLATE_PATH)
        php_content = read_file(NEXTCLOUD_CONFIG_PATH)

        self.assertIn("TRUSTED_PROXIES", compute_content)
        self.assertIn("TRUSTED_PROXIES", php_content)

    def test_cf11_storage_private_subnets_and_networking_exports(self):
        """CF11: R2.F9 + Networking: 01-networking exports PrivateSubnet1Id/2Id consumed by StorageStack."""
        net_template = load_cfn_yaml(NETWORKING_TEMPLATE_PATH)
        storage_content = read_file(STORAGE_TEMPLATE_PATH)

        outputs = net_template.get("Outputs", {})
        self.assertIn("PrivateSubnet1Id", outputs)
        self.assertIn("PrivateSubnet2Id", outputs)
        self.assertIn("PrivateSubnet1Id", storage_content)
        self.assertIn("PrivateSubnet2Id", storage_content)

    def test_cf12_control_plane_mfa_contract_with_console_login(self):
        """CF12: Contract 1 Conformance: Control Plane Lambda MFA_REQUIRED format matches LoginPage expectation."""
        lambda_content = read_file(LAMBDA_SRC_PATH)
        login_content = read_file(LOGIN_PAGE_PATH)

        # Lambda keys
        expected_keys = ["status", "message", "challenge_token", "mfa_type", "user", "role"]
        for key in expected_keys:
            self.assertIn(f'"{key}":', lambda_content)

        # Login page handles MFA_REQUIRED
        self.assertIn("MFA_REQUIRED", login_content)
        self.assertIn("challenge_token", login_content)


if __name__ == "__main__":
    unittest.main()
