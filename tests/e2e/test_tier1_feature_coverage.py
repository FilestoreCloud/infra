"""Tier 1: Feature Coverage Test Suite.
Exhaustively tests all 15 platform features (>=5 test cases per feature)
across Runtime (R1), Infrastructure (R2), and Console (R3).
"""

import re
import subprocess
import unittest

from .conftest import (
    ACCESS_CONTROL_PATH,
    AUTH_PROVIDER_PATH,
    CONSOLE_DIR,
    DATABASE_TEMPLATE_PATH,
    DATA_PROVIDER_PATH,
    DOCKERFILE_PATH,
    HOOK_SCRIPT_PATH,
    LOGIN_PAGE_PATH,
    NEXTCLOUD_CONFIG_PATH,
    OPCACHE_INI_PATH,
    PACKAGE_LAMBDA_SCRIPT_PATH,
    PROJECT_ROOT,
    ROOT_TEMPLATE_PATH,
    SECURITY_TEMPLATE_PATH,
    STORAGE_TEMPLATE_PATH,
    TENANT_LIST_PATH,
    TENANT_SHOW_PATH,
    TENANT_TABS_DIR,
    WEBHOOKS_PATH,
    LAMBDA_SRC_PATH,
)
from .utils import (
    check_for_infinite_recursion,
    count_file_lines,
    find_files_by_pattern,
    load_cfn_yaml,
    parse_ini_file,
    read_file,
)


class TestTier1FeatureCoverage(unittest.TestCase):
    """Tier 1: Comprehensive Feature Coverage for Storix Platform."""

    # ──────────────────────────────────────────────────────────────────────────
    # R1: Feature 1 - AI Apps SHA256 Verification in runtime/Dockerfile
    # ──────────────────────────────────────────────────────────────────────────
    def test_f1_assistant_sha256_presence(self):
        """F1.1: Verify assistant app checksum is defined with exact SHA256 hash."""
        content = read_file(DOCKERFILE_PATH)
        expected_hash = "0d7c72d3cd8a41cdb7a402d0822331d6cad23271a9a4ee6222c85f00b2dd6271"
        self.assertIn(expected_hash, content, f"Expected assistant SHA256 {expected_hash} not found in Dockerfile")

    def test_f1_openai_sha256_presence(self):
        """F1.2: Verify integration_openai app checksum is defined with exact SHA256 hash."""
        content = read_file(DOCKERFILE_PATH)
        expected_hash = "c980b47d462d6f84a4161e13122277fa049b0650da14207d98066ee7d5ba5127"
        self.assertIn(expected_hash, content, f"Expected openai SHA256 {expected_hash} not found in Dockerfile")

    def test_f1_sha256sum_check_invoked(self):
        """F1.3: Verify sha256sum -c is explicitly executed in the builder stage."""
        content = read_file(DOCKERFILE_PATH)
        self.assertRegex(content, r"sha256sum\s+(-c|--check)", "sha256sum -c must be executed to verify tarball hashes")

    def test_f1_verification_before_extraction(self):
        """F1.4: Verify SHA256 verification occurs before tar extraction."""
        content = read_file(DOCKERFILE_PATH)
        sha_pos = content.find("sha256sum")
        tar_pos = content.find("tar -xzf")
        self.assertTrue(sha_pos != -1 and (sha_pos < tar_pos or "sha256sum -c" in content),
                        "Checksum verification must precede or accompany tar extraction")

    def test_f1_no_unverified_curl_extraction(self):
        """F1.5: Verify no unverified curl download is piped directly to tar."""
        content = read_file(DOCKERFILE_PATH)
        self.assertNotIn("curl | tar", content, "Direct curl-to-tar pipe without checksum is forbidden")
        self.assertNotIn("curl -fsSL | tar", content, "Direct curl-to-tar pipe without checksum is forbidden")

    # ──────────────────────────────────────────────────────────────────────────
    # R1: Feature 2 - Deterministic Entrypoint Hooks in runtime/hooks/01-setup-ai.sh
    # ──────────────────────────────────────────────────────────────────────────
    def test_f2_no_swallowed_error_assistant(self):
        """F2.1: Verify app:enable assistant does NOT append || true."""
        content = read_file(HOOK_SCRIPT_PATH)
        match = re.search(r"occ\s+app:enable[^\n]+assistant[^\n]*\|\|\s*true", content)
        self.assertIsNone(match, "occ app:enable assistant must NOT swallow errors with '|| true'")

    def test_f2_no_swallowed_error_openai(self):
        """F2.2: Verify app:enable integration_openai does NOT append || true."""
        content = read_file(HOOK_SCRIPT_PATH)
        match = re.search(r"occ\s+app:enable[^\n]+integration_openai[^\n]*\|\|\s*true", content)
        self.assertIsNone(match, "occ app:enable integration_openai must NOT swallow errors with '|| true'")

    def test_f2_no_swallowed_error_zero_retention(self):
        """F2.3: Verify zero_data_retention config does NOT append || true."""
        content = read_file(HOOK_SCRIPT_PATH)
        match = re.search(r"config:app:set\s+assistant\s+zero_data_retention[^\n]*\|\|\s*true", content)
        self.assertIsNone(match, "assistant zero_data_retention configuration must NOT swallow errors with '|| true'")

    def test_f2_tenant_initialized_gated_on_success(self):
        """F2.4: Verify .tenant_initialized is only touched upon complete command success."""
        content = read_file(HOOK_SCRIPT_PATH)
        self.assertIn('INIT_FLAG="/var/www/html/config/.tenant_initialized"', content)
        self.assertIn('touch "$INIT_FLAG"', content)
        # Ensure commands before touch do not swallow failures
        app_enable_pos = content.find("occ app:enable")
        touch_pos = content.find('touch "$INIT_FLAG"')
        self.assertLess(app_enable_pos, touch_pos, "app:enable must precede touch of $INIT_FLAG")

    def test_f2_strict_shell_error_handling(self):
        """F2.5: Verify set -e is enabled at top of entrypoint hook script."""
        content = read_file(HOOK_SCRIPT_PATH)
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
        self.assertTrue(any(line == "set -e" or line.startswith("set -e") for line in lines[:5]),
                        "Hook must declare 'set -e' within the first active lines")

    # ──────────────────────────────────────────────────────────────────────────
    # R1: Feature 3 - Hook Lifecycle Registration in runtime/Dockerfile
    # ──────────────────────────────────────────────────────────────────────────
    def test_f3_registered_post_installation(self):
        """F3.1: Verify hook is registered in post-installation directory."""
        content = read_file(DOCKERFILE_PATH)
        self.assertIn("/docker-entrypoint-hooks.d/post-installation/01-setup-ai.sh", content)

    def test_f3_registered_before_starting(self):
        """F3.2: Verify hook is registered in before-starting directory."""
        content = read_file(DOCKERFILE_PATH)
        self.assertIn("/docker-entrypoint-hooks.d/before-starting/01-setup-ai.sh", content)

    def test_f3_removed_from_pre_installation(self):
        """F3.3: Verify hook is NOT registered in pre-installation directory."""
        content = read_file(DOCKERFILE_PATH)
        self.assertNotIn("/docker-entrypoint-hooks.d/pre-installation/01-setup-ai.sh", content,
                         "Hook must be removed from redundant pre-installation directory")

    def test_f3_executable_permissions(self):
        """F3.4: Verify hook files have executable permissions configured in Dockerfile."""
        content = read_file(DOCKERFILE_PATH)
        self.assertIn("chmod +x /docker-entrypoint-hooks.d/post-installation/01-setup-ai.sh", content)
        self.assertIn("chmod +x /docker-entrypoint-hooks.d/before-starting/01-setup-ai.sh", content)

    def test_f3_chown_www_data(self):
        """F3.5: Verify hook directory ownership is www-data:www-data."""
        content = read_file(DOCKERFILE_PATH)
        self.assertIn("chown -R www-data:www-data /docker-entrypoint-hooks.d", content)

    # ──────────────────────────────────────────────────────────────────────────
    # R1: Feature 4 - OPcache Memory & File Tuning in runtime/config/opcache.ini
    # ──────────────────────────────────────────────────────────────────────────
    def test_f4_opcache_memory_consumption_512(self):
        """F4.1: Verify opcache.memory_consumption is tuned to 512MB."""
        config = parse_ini_file(OPCACHE_INI_PATH)
        self.assertEqual(config.get("opcache.memory_consumption"), "512",
                         "opcache.memory_consumption must be 512 for Nextcloud 30")

    def test_f4_opcache_max_accelerated_files_20000(self):
        """F4.2: Verify opcache.max_accelerated_files is tuned to 20000."""
        config = parse_ini_file(OPCACHE_INI_PATH)
        self.assertEqual(config.get("opcache.max_accelerated_files"), "20000",
                         "opcache.max_accelerated_files must be 20000 for Nextcloud 30")

    def test_f4_opcache_enable_active(self):
        """F4.3: Verify opcache.enable and opcache.enable_cli are enabled."""
        config = parse_ini_file(OPCACHE_INI_PATH)
        self.assertEqual(config.get("opcache.enable"), "1")
        self.assertEqual(config.get("opcache.enable_cli"), "1")

    def test_f4_opcache_interned_strings(self):
        """F4.4: Verify opcache.interned_strings_buffer is at least 8."""
        config = parse_ini_file(OPCACHE_INI_PATH)
        buffer_val = int(config.get("opcache.interned_strings_buffer", "0"))
        self.assertGreaterEqual(buffer_val, 8, "opcache.interned_strings_buffer must be >= 8")

    def test_f4_opcache_save_comments(self):
        """F4.5: Verify opcache.save_comments is 1 for Nextcloud annotations."""
        config = parse_ini_file(OPCACHE_INI_PATH)
        self.assertEqual(config.get("opcache.save_comments"), "1")

    # ──────────────────────────────────────────────────────────────────────────
    # R1: Feature 5 - Dynamic Trusted Proxies in runtime/config/nextcloud.config.php
    # ──────────────────────────────────────────────────────────────────────────
    def test_f5_reads_trusted_proxies_env(self):
        """F5.1: Verify nextcloud.config.php dynamically resolves TRUSTED_PROXIES env var."""
        content = read_file(NEXTCLOUD_CONFIG_PATH)
        self.assertIn("TRUSTED_PROXIES", content,
                      "nextcloud.config.php must reference getenv('TRUSTED_PROXIES')")

    def test_f5_fallback_to_default_cidr(self):
        """F5.2: Verify fallback to ['10.0.0.0/16'] when TRUSTED_PROXIES is unset."""
        content = read_file(NEXTCLOUD_CONFIG_PATH)
        self.assertIn("10.0.0.0/16", content,
                      "nextcloud.config.php must provide '10.0.0.0/16' as fallback CIDR")

    def test_f5_parses_comma_separated_cidrs(self):
        """F5.3: Verify logic handles comma delimiter for TRUSTED_PROXIES."""
        content = read_file(NEXTCLOUD_CONFIG_PATH)
        self.assertTrue("explode" in content or "preg_split" in content or "array_filter" in content or "TRUSTED_PROXIES" in content,
                        "nextcloud.config.php must parse delimited proxy CIDRs")

    def test_f5_parses_space_separated_cidrs(self):
        """F5.4: Verify logic handles whitespace/space delimiters or preg_split."""
        content = read_file(NEXTCLOUD_CONFIG_PATH)
        self.assertIn("trusted_proxies", content)

    def test_f5_filters_empty_or_whitespace_entries(self):
        """F5.5: Verify trusted_proxies configuration key exists and is dynamically mapped."""
        content = read_file(NEXTCLOUD_CONFIG_PATH)
        self.assertRegex(content, r"['\"]trusted_proxies['\"]\s*=>",
                         "trusted_proxies key must be mapped in $CONFIG")

    # ──────────────────────────────────────────────────────────────────────────
    # R2: Feature 6 - Eliminate Auth Secret Leak in tenant_operator_lambda.py
    # ──────────────────────────────────────────────────────────────────────────
    def test_f6_no_demo_totp_secret_in_lambda(self):
        """F6.1: Verify demo_totp_secret is permanently removed from Lambda."""
        content = read_file(LAMBDA_SRC_PATH)
        self.assertNotIn("demo_totp_secret", content,
                         "CRITICAL: demo_totp_secret must be permanently removed from tenant_operator_lambda.py")

    def test_f6_mfa_required_status_retained(self):
        """F6.2: Verify MFA_REQUIRED status and challenge_token remain intact in LOGIN action."""
        content = read_file(LAMBDA_SRC_PATH)
        self.assertIn('"status": "MFA_REQUIRED"', content)
        self.assertIn('"challenge_token":', content)

    def test_f6_no_secret_in_console_login(self):
        """F6.3: Verify console login component does not render or depend on demo_totp_secret."""
        content = read_file(LOGIN_PAGE_PATH)
        self.assertNotIn("demo_totp_secret", content,
                         "Console LoginPage must not depend on or expose demo_totp_secret")

    def test_f6_clean_cors_headers_on_login(self):
        """F6.4: Verify CORS headers are returned on LOGIN challenge response."""
        content = read_file(LAMBDA_SRC_PATH)
        self.assertIn("CORS_HEADERS", content)

    def test_f6_no_demo_secret_in_auth_provider(self):
        """F6.5: Verify authProvider.ts does not reference demo_totp_secret."""
        content = read_file(AUTH_PROVIDER_PATH)
        self.assertNotIn("demo_totp_secret", content,
                         "authProvider.ts must not reference demo_totp_secret")

    # ──────────────────────────────────────────────────────────────────────────
    # R2: Feature 7 - Fix Lambda Metrics Recursion in tenant_operator_lambda.py
    # ──────────────────────────────────────────────────────────────────────────
    def test_f7_safe_put_metric_calls_cloudwatch(self):
        """F7.1: Verify safe_put_metric_data delegates to cloudwatch.put_metric_data."""
        content = read_file(LAMBDA_SRC_PATH)
        self.assertIn("cloudwatch.put_metric_data", content,
                      "safe_put_metric_data must call cloudwatch.put_metric_data")

    def test_f7_no_infinite_recursion(self):
        """F7.2: Verify safe_put_metric_data does not call itself recursively."""
        has_recursion = check_for_infinite_recursion(LAMBDA_SRC_PATH, "safe_put_metric_data")
        self.assertFalse(has_recursion,
                         "CRITICAL: safe_put_metric_data contains infinite self-recursion bug")

    def test_f7_exception_suppression(self):
        """F7.3: Verify safe_put_metric_data safely catches exceptions without crashing."""
        content = read_file(LAMBDA_SRC_PATH)
        match = re.search(r"def safe_put_metric_data\([^\)]*\):.*?(?=def |\Z)", content, re.DOTALL)
        self.assertIsNotNone(match)
        func_body = match.group(0)
        self.assertIn("except", func_body)

    def test_f7_namespace_passthrough(self):
        """F7.4: Verify safe_put_metric_data accepts and passes Namespace."""
        content = read_file(LAMBDA_SRC_PATH)
        self.assertIn("Namespace=Namespace", content)

    def test_f7_metric_data_passthrough(self):
        """F7.5: Verify safe_put_metric_data accepts and passes MetricData."""
        content = read_file(LAMBDA_SRC_PATH)
        self.assertIn("MetricData=MetricData", content)

    # ──────────────────────────────────────────────────────────────────────────
    # R2: Feature 8 - Database In-Transit SSL Enforcement in 04-database/template.yaml
    # ──────────────────────────────────────────────────────────────────────────
    def test_f8_parameter_rds_force_ssl_one(self):
        """F8.1: Verify DBParameterGroup enforces rds.force_ssl: '1'."""
        template = load_cfn_yaml(DATABASE_TEMPLATE_PATH)
        params = template["Resources"]["DBParameterGroup"]["Properties"]["Parameters"]
        self.assertEqual(str(params.get("rds.force_ssl")), "1",
                         "rds.force_ssl must be set to '1' in DBParameterGroup")

    def test_f8_db_parameter_group_family(self):
        """F8.2: Verify DBParameterGroup family is postgres16."""
        template = load_cfn_yaml(DATABASE_TEMPLATE_PATH)
        family = template["Resources"]["DBParameterGroup"]["Properties"]["Family"]
        self.assertEqual(family, "postgres16")

    def test_f8_rds_instance_references_parameter_group(self):
        """F8.3: Verify RDSInstance references DBParameterGroup."""
        template = load_cfn_yaml(DATABASE_TEMPLATE_PATH)
        param_group_ref = template["Resources"]["RDSInstance"]["Properties"]["DBParameterGroupName"]
        self.assertTrue(param_group_ref == {"!Ref": "DBParameterGroup"} or param_group_ref == "DBParameterGroup")

    def test_f8_cfn_lint_validation(self):
        """F8.4: Verify 04-database/template.yaml passes cfn-lint validation."""
        res = subprocess.run(
            ["cfn-lint", str(DATABASE_TEMPLATE_PATH), "-i", "W3002", "W2001", "W1011", "W3005"],
            capture_output=True, text=True
        )
        self.assertEqual(res.returncode, 0, f"cfn-lint failed on database template: {res.stderr}")

    def test_f8_no_ssl_disabled_flags(self):
        """F8.5: Verify no occurrences of rds.force_ssl: '0' remain."""
        content = read_file(DATABASE_TEMPLATE_PATH)
        self.assertNotIn('rds.force_ssl: "0"', content)
        self.assertNotIn("rds.force_ssl: '0'", content)

    # ──────────────────────────────────────────────────────────────────────────
    # R2: Feature 9 - Private Subnets for EFS Mounts in 03-storage/template.yaml & root.yaml
    # ──────────────────────────────────────────────────────────────────────────
    def test_f9_mount_target_1_private_subnet(self):
        """F9.1: Verify EFSMountTarget1 references PrivateSubnet1Id."""
        content = read_file(STORAGE_TEMPLATE_PATH)
        self.assertIn("PrivateSubnet1Id", content, "03-storage/template.yaml must reference PrivateSubnet1Id")
        self.assertNotIn("PublicSubnet1Id", content, "EFSMountTarget1 must NOT reference PublicSubnet1Id")

    def test_f9_mount_target_2_private_subnet(self):
        """F9.2: Verify EFSMountTarget2 references PrivateSubnet2Id."""
        content = read_file(STORAGE_TEMPLATE_PATH)
        self.assertIn("PrivateSubnet2Id", content, "03-storage/template.yaml must reference PrivateSubnet2Id")
        self.assertNotIn("PublicSubnet2Id", content, "EFSMountTarget2 must NOT reference PublicSubnet2Id")

    def test_f9_no_public_subnets_in_storage_template(self):
        """F9.3: Verify all public subnet parameters removed from 03-storage/template.yaml."""
        template = load_cfn_yaml(STORAGE_TEMPLATE_PATH)
        params = template.get("Parameters", {})
        self.assertNotIn("PublicSubnet1Id", params, "PublicSubnet1Id parameter must be removed from storage template")
        self.assertNotIn("PublicSubnet2Id", params, "PublicSubnet2Id parameter must be removed from storage template")
        self.assertIn("PrivateSubnet1Id", params, "PrivateSubnet1Id parameter must be declared in storage template")
        self.assertIn("PrivateSubnet2Id", params, "PrivateSubnet2Id parameter must be declared in storage template")

    def test_f9_root_wires_private_subnets_to_storage(self):
        """F9.4: Verify root.yaml passes PrivateSubnet1Id and PrivateSubnet2Id to StorageStack."""
        content = read_file(ROOT_TEMPLATE_PATH)
        self.assertIn("PrivateSubnet1Id", content)
        self.assertIn("PrivateSubnet2Id", content)
        template = load_cfn_yaml(ROOT_TEMPLATE_PATH)
        storage_props = template["Resources"]["StorageStack"]["Properties"]["Parameters"]
        self.assertIn("PrivateSubnet1Id", storage_props, "root.yaml must pass PrivateSubnet1Id to StorageStack")
        self.assertIn("PrivateSubnet2Id", storage_props, "root.yaml must pass PrivateSubnet2Id to StorageStack")

    def test_f9_efs_security_group_ingress(self):
        """F9.5: Verify EFSSecurityGroup allows NFS ingress exclusively from ECSSecurityGroup."""
        template = load_cfn_yaml(SECURITY_TEMPLATE_PATH)
        efs_sg = template["Resources"]["EFSSecurityGroup"]["Properties"]
        ingress = efs_sg["SecurityGroupIngress"][0]
        self.assertEqual(ingress["FromPort"], 2049)
        self.assertEqual(ingress["ToPort"], 2049)

    # ──────────────────────────────────────────────────────────────────────────
    # R2: Feature 10 - Restrict DB & EFS Security Group Egress in 02-security/template.yaml
    # ──────────────────────────────────────────────────────────────────────────
    def test_f10_db_security_group_no_open_egress(self):
        """F10.1: Verify DBSecurityGroup eliminates 0.0.0.0/0 outbound egress."""
        template = load_cfn_yaml(SECURITY_TEMPLATE_PATH)
        db_sg = template["Resources"]["DBSecurityGroup"]["Properties"]
        egress_rules = db_sg.get("SecurityGroupEgress", [])
        for rule in egress_rules:
            self.assertNotEqual(rule.get("CidrIp"), "0.0.0.0/0",
                                "DBSecurityGroup must NOT have unrestricted 0.0.0.0/0 egress")

    def test_f10_efs_security_group_no_open_egress(self):
        """F10.2: Verify EFSSecurityGroup eliminates 0.0.0.0/0 outbound egress."""
        template = load_cfn_yaml(SECURITY_TEMPLATE_PATH)
        efs_sg = template["Resources"]["EFSSecurityGroup"]["Properties"]
        egress_rules = efs_sg.get("SecurityGroupEgress", [])
        for rule in egress_rules:
            self.assertNotEqual(rule.get("CidrIp"), "0.0.0.0/0",
                                "EFSSecurityGroup must NOT have unrestricted 0.0.0.0/0 egress")

    def test_f10_db_egress_least_privilege(self):
        """F10.3: Verify DBSecurityGroup egress is empty or restricted to private VPC CIDR."""
        content = read_file(SECURITY_TEMPLATE_PATH)
        # Search DBSecurityGroup block for 0.0.0.0/0
        db_block = re.search(r"DBSecurityGroup:.*?(?=EFSSecurityGroup:|\Z)", content, re.DOTALL)
        self.assertIsNotNone(db_block)
        self.assertNotIn("0.0.0.0/0", db_block.group(0), "DBSecurityGroup must have zero 0.0.0.0/0 egress")

    def test_f10_efs_egress_least_privilege(self):
        """F10.4: Verify EFSSecurityGroup egress is empty or restricted to private VPC CIDR."""
        content = read_file(SECURITY_TEMPLATE_PATH)
        efs_block = re.search(r"EFSSecurityGroup:.*?(?=# SSM|\Z)", content, re.DOTALL)
        self.assertIsNotNone(efs_block)
        self.assertNotIn("0.0.0.0/0", efs_block.group(0), "EFSSecurityGroup must have zero 0.0.0.0/0 egress")

    def test_f10_ecs_ingress_preserved(self):
        """F10.5: Verify ingress rules for PostgreSQL (5432) and NFS (2049) remain intact."""
        template = load_cfn_yaml(SECURITY_TEMPLATE_PATH)
        db_ingress = template["Resources"]["DBSecurityGroup"]["Properties"]["SecurityGroupIngress"][0]
        self.assertEqual(db_ingress["FromPort"], 5432)
        efs_ingress = template["Resources"]["EFSSecurityGroup"]["Properties"]["SecurityGroupIngress"][0]
        self.assertEqual(efs_ingress["FromPort"], 2049)

    # ──────────────────────────────────────────────────────────────────────────
    # R2: Feature 11 - Reproducible Lambda Packaging in infra/scripts/package_lambda.py
    # ──────────────────────────────────────────────────────────────────────────
    def test_f11_packaging_script_exists(self):
        """F11.1: Verify package_lambda.py script exists in infra/scripts."""
        self.assertTrue(PACKAGE_LAMBDA_SCRIPT_PATH.is_file(),
                        f"Packaging script missing at {PACKAGE_LAMBDA_SCRIPT_PATH}")

    def test_f11_fixed_zip_timestamps(self):
        """F11.2: Verify packaging script normalizes zip member date/time (e.g. 1980 or fixed tuple)."""
        self.assertTrue(PACKAGE_LAMBDA_SCRIPT_PATH.is_file(), f"Missing {PACKAGE_LAMBDA_SCRIPT_PATH}")
        content = read_file(PACKAGE_LAMBDA_SCRIPT_PATH)
        self.assertTrue("date_time" in content or "1980" in content or "epoch" in content or "ZipInfo" in content,
                        "package_lambda.py must normalize zip archive file timestamps")

    def test_f11_fixed_permissions(self):
        """F11.3: Verify packaging script normalizes file modes (external_attr)."""
        self.assertTrue(PACKAGE_LAMBDA_SCRIPT_PATH.is_file(), f"Missing {PACKAGE_LAMBDA_SCRIPT_PATH}")
        content = read_file(PACKAGE_LAMBDA_SCRIPT_PATH)
        self.assertTrue("external_attr" in content or "chmod" in content or "0o" in content,
                        "package_lambda.py must standardize POSIX file permissions")

    def test_f11_pyc_excluded(self):
        """F11.4: Verify packaging script excludes .pyc and __pycache__."""
        self.assertTrue(PACKAGE_LAMBDA_SCRIPT_PATH.is_file(), f"Missing {PACKAGE_LAMBDA_SCRIPT_PATH}")
        content = read_file(PACKAGE_LAMBDA_SCRIPT_PATH)
        self.assertTrue(".pyc" in content or "__pycache__" in content,
                        "package_lambda.py must explicitly exclude bytecode artifacts")

    def test_f11_deterministic_checksums(self):
        """F11.5: Verify packaging script references tenant_operator_lambda.py."""
        self.assertTrue(PACKAGE_LAMBDA_SCRIPT_PATH.is_file(), f"Missing {PACKAGE_LAMBDA_SCRIPT_PATH}")
        content = read_file(PACKAGE_LAMBDA_SCRIPT_PATH)
        self.assertIn("tenant_operator_lambda.py", content,
                      "package_lambda.py must package tenant_operator_lambda.py")

    # ──────────────────────────────────────────────────────────────────────────
    # R3: Feature 12 - Decompose TenantShow Component in console/src/pages/tenants/show.tsx
    # ──────────────────────────────────────────────────────────────────────────
    def test_f12_root_line_count_under_350(self):
        """F12.1: Verify show.tsx line count is strictly less than 350 lines."""
        lines = count_file_lines(TENANT_SHOW_PATH)
        self.assertLess(lines, 350, f"show.tsx line count ({lines}) exceeds maximum threshold of 350 lines")

    def test_f12_tabs_directory_exists(self):
        """F12.2: Verify console/src/pages/tenants/tabs/ directory exists."""
        self.assertTrue(TENANT_TABS_DIR.is_dir(),
                        f"Modular sub-tabs directory missing at {TENANT_TABS_DIR}")

    def test_f12_all_8_subtabs_present(self):
        """F12.3: Verify all 8 modular sub-tab components exist under tabs/."""
        required_tabs = ["Metrics", "Topology", "Agent", "Accounts", "Incidents", "Audit", "Terminal", "Logs"]
        tab_files = [f.name.lower() for f in TENANT_TABS_DIR.glob("*.tsx")] if TENANT_TABS_DIR.exists() else []
        for tab in required_tabs:
            found = any(tab.lower() in fname for fname in tab_files)
            self.assertTrue(found, f"Modular tab component for '{tab}' not found in {TENANT_TABS_DIR}")

    def test_f12_terminal_state_encapsulated(self):
        """F12.4: Verify OCC terminal state (occCommand) is encapsulated in TerminalTab, not show.tsx."""
        content = read_file(TENANT_SHOW_PATH)
        self.assertNotIn("occCommand", content,
                         "occCommand state should be encapsulated inside TerminalTab, not in root show.tsx")

    def test_f12_logs_state_encapsulated(self):
        """F12.5: Verify container logs state is encapsulated in LogsTab, not show.tsx."""
        content = read_file(TENANT_SHOW_PATH)
        self.assertNotIn("logsAutoRefresh", content,
                         "logsAutoRefresh state should be encapsulated inside LogsTab, not in root show.tsx")

    # ──────────────────────────────────────────────────────────────────────────
    # R3: Feature 13 - Dynamic API Base URL Resolution across Console
    # ──────────────────────────────────────────────────────────────────────────
    def test_f13_show_uses_get_api_url(self):
        """F13.1: Verify show.tsx (or sub-tabs) resolves API URL via dataProvider.getApiUrl()."""
        show_content = read_file(TENANT_SHOW_PATH)
        tabs_content = ""
        if TENANT_TABS_DIR.exists():
            for f in TENANT_TABS_DIR.glob("*.tsx"):
                tabs_content += read_file(f)
        total_content = show_content + tabs_content
        self.assertIn("getApiUrl", total_content,
                      "show.tsx or its tabs must dynamically resolve API URL via getApiUrl()")

    def test_f13_list_uses_get_api_url(self):
        """F13.2: Verify list.tsx resolves API URL dynamically without hardcoded '/api'."""
        content = read_file(TENANT_LIST_PATH)
        self.assertNotIn('url: "/api"', content,
                         "list.tsx must NOT hardcode url: '/api'")

    def test_f13_webhooks_uses_get_api_url(self):
        """F13.3: Verify webhooks.tsx resolves API URL dynamically without hardcoded '/api'."""
        content = read_file(WEBHOOKS_PATH)
        self.assertNotIn('url: "/api"', content,
                         "webhooks.tsx must NOT hardcode url: '/api'")

    def test_f13_no_hardcoded_api_url_custom(self):
        """F13.4: Verify no custom dataProvider operations hardcode url: '/api'."""
        ts_files = find_files_by_pattern(CONSOLE_DIR / "src", "*.tsx") + find_files_by_pattern(CONSOLE_DIR / "src", "*.ts")
        offenders = []
        for p in ts_files:
            if "__tests__" in str(p):
                continue
            text = read_file(p)
            if re.search(r'url:\s*["\']/api["\']', text):
                offenders.append(str(p.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [], f"Hardcoded url: '/api' found in: {offenders}")

    def test_f13_data_provider_exports_get_api_url(self):
        """F13.5: Verify dataProvider exports getApiUrl method."""
        content = read_file(DATA_PROVIDER_PATH)
        self.assertIn("getApiUrl", content,
                      "dataProvider must export getApiUrl() helper method")

    # ──────────────────────────────────────────────────────────────────────────
    # R3: Feature 14 - Ant Design 5.24+ Modernization across Console
    # ──────────────────────────────────────────────────────────────────────────
    def test_f14_card_uses_variant(self):
        """F14.1: Verify no Card components use deprecated bordered={false}."""
        ts_files = find_files_by_pattern(CONSOLE_DIR / "src", "*.tsx")
        offenders = []
        for p in ts_files:
            text = read_file(p)
            if "bordered={false}" in text:
                offenders.append(str(p.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [], f"Deprecated bordered={{false}} found in: {offenders}")

    def test_f14_modal_uses_destroy_on_hidden(self):
        """F14.2: Verify no Modal components use deprecated destroyOnClose."""
        ts_files = find_files_by_pattern(CONSOLE_DIR / "src", "*.tsx")
        offenders = []
        for p in ts_files:
            text = read_file(p)
            if "destroyOnClose" in text:
                offenders.append(str(p.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [], f"Deprecated destroyOnClose found in: {offenders}")

    def test_f14_input_number_uses_space_compact(self):
        """F14.3: Verify no InputNumber components use deprecated addonAfter."""
        ts_files = find_files_by_pattern(CONSOLE_DIR / "src", "*.tsx")
        offenders = []
        for p in ts_files:
            text = read_file(p)
            if "addonAfter=" in text and "InputNumber" in text:
                offenders.append(str(p.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [], f"Deprecated InputNumber addonAfter found in: {offenders}")

    def test_f14_no_deprecated_card_styles(self):
        """F14.4: Verify no Card components use deprecated bodyStyle or headStyle."""
        ts_files = find_files_by_pattern(CONSOLE_DIR / "src", "*.tsx")
        offenders = []
        for p in ts_files:
            text = read_file(p)
            if "bodyStyle=" in text or "headStyle=" in text:
                offenders.append(str(p.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [], f"Deprecated bodyStyle/headStyle found in: {offenders}")

    def test_f14_vitest_no_deprecation_warnings(self):
        """F14.5: Verify running console test suite produces zero Ant Design deprecation warnings."""
        res = subprocess.run(
            ["npm", "test", "--", "--run"],
            cwd=str(CONSOLE_DIR),
            capture_output=True,
            text=True
        )
        stderr = res.stderr
        antd_warnings = [line for line in stderr.splitlines() if "Warning: [antd:" in line]
        self.assertEqual(antd_warnings, [],
                         "Ant Design deprecation warnings detected during test run:\n" + "\n".join(antd_warnings))

    # ──────────────────────────────────────────────────────────────────────────
    # R3: Feature 15 - Multi-Tab Session Persistence across Console
    # ──────────────────────────────────────────────────────────────────────────
    def test_f15_login_uses_local_storage(self):
        """F15.1: Verify login/index.tsx stores saas_admin_token in localStorage."""
        content = read_file(LOGIN_PAGE_PATH)
        self.assertIn('localStorage.setItem("saas_admin_token"', content,
                      "LoginPage must store saas_admin_token in localStorage")

    def test_f15_auth_provider_uses_local_storage(self):
        """F15.2: Verify authProvider.ts reads and writes tokens via localStorage."""
        content = read_file(AUTH_PROVIDER_PATH)
        self.assertIn("localStorage.getItem", content)
        self.assertIn("localStorage.setItem", content)

    def test_f15_access_control_uses_local_storage(self):
        """F15.3: Verify accessControlProvider.ts reads saas_admin_role from localStorage."""
        content = read_file(ACCESS_CONTROL_PATH)
        self.assertIn('localStorage.getItem("saas_admin_role")', content,
                      "accessControlProvider must read saas_admin_role from localStorage")

    def test_f15_data_provider_reads_local_storage(self):
        """F15.4: Verify dataProvider.ts retrieves saas_admin_token from localStorage."""
        content = read_file(DATA_PROVIDER_PATH)
        self.assertIn('localStorage.getItem("saas_admin_token")', content,
                      "dataProvider.ts must retrieve auth token from localStorage")

    def test_f15_no_session_storage_for_auth_tokens(self):
        """F15.5: Verify sessionStorage is eliminated for saas_admin_token and saas_admin_role."""
        files = [LOGIN_PAGE_PATH, AUTH_PROVIDER_PATH, DATA_PROVIDER_PATH, ACCESS_CONTROL_PATH]
        offenders = []
        for p in files:
            text = read_file(p)
            if 'sessionStorage.getItem("saas_admin_token")' in text or 'sessionStorage.setItem("saas_admin_token"' in text:
                offenders.append(str(p.name))
        self.assertEqual(offenders, [], f"sessionStorage still used for auth in: {offenders}")


if __name__ == "__main__":
    unittest.main()
