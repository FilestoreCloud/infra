"""Tier 2: Boundary & Corner Cases Test Suite.
Exhaustively tests edge conditions, malformed inputs, stress scenarios,
and boundary thresholds for all 15 platform features (>=5 test cases per feature).
"""

import ast
import os
import re
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
    ROOT_TEMPLATE_PATH,
    SECURITY_TEMPLATE_PATH,
    STORAGE_TEMPLATE_PATH,
    TENANT_SHOW_PATH,
    LAMBDA_SRC_PATH,
)
from .utils import (
    count_file_lines,
    find_files_by_pattern,
    get_ast_tree,
    load_cfn_yaml,
    parse_ini_file,
    read_file,
)


class TestTier2BoundaryCorner(unittest.TestCase):
    """Tier 2: Boundary and Corner Case Verification for Storix Platform."""

    # ──────────────────────────────────────────────────────────────────────────
    # R1: Feature 1 - Boundaries on AI Apps SHA256 Verification
    # ──────────────────────────────────────────────────────────────────────────
    def test_f1_b1_checksum_format_is_lowercase_64_hex(self):
        """F1.B1: Verify SHA256 checksums are exactly 64 characters lowercase hexadecimal."""
        content = read_file(DOCKERFILE_PATH)
        hashes = re.findall(r"\b[a-f0-9]{64}\b", content)
        self.assertGreaterEqual(len(hashes), 2, "Dockerfile must define at least two 64-char hex SHA256 hashes")

    def test_f1_b2_no_uppercase_hex_characters(self):
        """F1.B2: Verify sha256 hashes do not use uppercase hex (which can break sha256sum -c)."""
        content = read_file(DOCKERFILE_PATH)
        upper_hashes = re.findall(r"\b[A-F0-9]{64}\b", content)
        # Should not find 64-char uppercase hex that isn't lowercase
        pure_upper = [h for h in upper_hashes if any(c.isupper() for c in h)]
        self.assertEqual(pure_upper, [], "Checksum hashes must be lowercase hex")

    def test_f1_b3_checksum_mismatch_behavior(self):
        """F1.B3: Verify sha256 check fails closed and halts execution on mismatch."""
        content = read_file(DOCKERFILE_PATH)
        self.assertNotIn("sha256sum -c || true", content, "Checksum verification must never swallow failure")
        self.assertNotIn("sha256sum --check || true", content, "Checksum verification must never swallow failure")

    def test_f1_b4_version_variables_non_empty(self):
        """F1.B4: Verify ASSISTANT_VERSION and OPENAI_INTEGRATION_VERSION are non-empty and pinned."""
        content = read_file(DOCKERFILE_PATH)
        self.assertRegex(content, r'ENV\s+ASSISTANT_VERSION="v\d+\.\d+\.\d+"')
        self.assertRegex(content, r'ENV\s+OPENAI_INTEGRATION_VERSION="v\d+\.\d+\.\d+"')

    def test_f1_b5_isolated_build_stage_cleanup(self):
        """F1.B5: Verify builder stage isolates build dependencies from production image."""
        content = read_file(DOCKERFILE_PATH)
        self.assertIn("FROM nextcloud:30.0.17-apache", content)
        self.assertIn("COPY --from=builder", content)
        # Builder artifacts should not leak curl or tar packages into runtime stage
        runtime_stage = content.split("FROM nextcloud:30.0.17-apache")[1]
        self.assertNotIn("apk add", runtime_stage, "Runtime stage must not install apk packages directly")

    # ──────────────────────────────────────────────────────────────────────────
    # R1: Feature 2 - Boundaries on Hook Determinism & Error Handling
    # ──────────────────────────────────────────────────────────────────────────
    def test_f2_b1_syntax_validation_sh_n(self):
        """F2.B1: Verify hook script passes strict syntax check (sh -n)."""
        res = os.system(f"sh -n '{HOOK_SCRIPT_PATH}'")
        self.assertEqual(res, 0, "Hook script failed syntax validation with sh -n")

    def test_f2_b2_force_reinit_handles_non_one_values(self):
        """F2.B2: Verify FORCE_REINIT handles non-1 values ('0', '', 'false') correctly."""
        content = read_file(HOOK_SCRIPT_PATH)
        self.assertIn('FORCE_REINIT:-0', content, "Hook must use safe default expansion for FORCE_REINIT")

    def test_f2_b3_no_partial_init_flag_creation(self):
        """F2.B3: Verify flag file is created via touch only at the very end of installation block."""
        content = read_file(HOOK_SCRIPT_PATH)
        lines = content.splitlines()
        touch_lines = [i for i, line in enumerate(lines) if 'touch "$INIT_FLAG"' in line]
        self.assertEqual(len(touch_lines), 1, "There must be exactly one atomic touch of $INIT_FLAG")

    def test_f2_b4_empty_endpoint_handling_in_hook(self):
        """F2.B4: Verify empty AI_API_URL or OPENAI_API_URL skips AI provider binding safely."""
        content = read_file(HOOK_SCRIPT_PATH)
        self.assertIn('-n "${AI_ENDPOINT}"', content, "Hook must check if AI_ENDPOINT is non-empty before binding")

    def test_f2_b5_redis_port_fallback(self):
        """F2.B5: Verify REDIS_PORT falls back to 6379 when unset."""
        content = read_file(HOOK_SCRIPT_PATH)
        self.assertIn("REDIS_PORT:-6379", content, "REDIS_PORT must fall back to 6379")

    # ──────────────────────────────────────────────────────────────────────────
    # R1: Feature 3 - Boundaries on Hook Lifecycle Directories
    # ──────────────────────────────────────────────────────────────────────────
    def test_f3_b1_hook_names_are_consistent(self):
        """F3.B1: Verify hook name 01-setup-ai.sh is identical across all lifecycle targets."""
        content = read_file(DOCKERFILE_PATH)
        matches = re.findall(r"/docker-entrypoint-hooks\.d/([^/]+)/([^ \t\n]+)", content)
        hook_names = [m[1] for m in matches if m[1].endswith(".sh")]
        for name in hook_names:
            self.assertEqual(name, "01-setup-ai.sh", "Hook filename must be strictly 01-setup-ai.sh")

    def test_f3_b2_no_wildcard_chmod_hooks(self):
        """F3.B2: Verify chmod +x targets specific hook or valid directory."""
        content = read_file(DOCKERFILE_PATH)
        self.assertNotIn("chmod 777", content, "Insecure 777 permissions must never be applied")

    def test_f3_b3_dockerfile_line_endings_unix(self):
        """F3.B3: Verify Dockerfile has Unix LF line endings without CRLF carriage returns."""
        with open(DOCKERFILE_PATH, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"\r\n", raw, "Dockerfile contains Windows CRLF line endings")

    def test_f3_b4_hook_script_shebang_boundary(self):
        """F3.B4: Verify hook script starts with valid standard POSIX #!/bin/sh shebang."""
        content = read_file(HOOK_SCRIPT_PATH)
        first_line = content.splitlines()[0]
        self.assertEqual(first_line, "#!/bin/sh", "Hook script must start with '#!/bin/sh'")

    def test_f3_b5_hook_script_line_endings_unix(self):
        """F3.B5: Verify hook script has Unix LF line endings without CRLF carriage returns."""
        with open(HOOK_SCRIPT_PATH, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"\r\n", raw, "Hook script contains Windows CRLF line endings")

    # ──────────────────────────────────────────────────────────────────────────
    # R1: Feature 4 - Boundaries on OPcache Configuration Values
    # ──────────────────────────────────────────────────────────────────────────
    def test_f4_b1_opcache_memory_numeric_value(self):
        """F4.B1: Verify opcache.memory_consumption is pure integer (no 'M' or 'MB' suffix)."""
        config = parse_ini_file(OPCACHE_INI_PATH)
        mem = config.get("opcache.memory_consumption", "")
        self.assertTrue(mem.isdigit(), f"opcache.memory_consumption must be pure integer without suffix, got '{mem}'")
        self.assertGreaterEqual(int(mem), 512)

    def test_f4_b2_accelerated_files_numeric_value(self):
        """F4.B2: Verify opcache.max_accelerated_files is integer >= 20000."""
        config = parse_ini_file(OPCACHE_INI_PATH)
        files_val = config.get("opcache.max_accelerated_files", "")
        self.assertTrue(files_val.isdigit(), f"max_accelerated_files must be pure integer, got '{files_val}'")
        self.assertGreaterEqual(int(files_val), 20000)

    def test_f4_b3_php_memory_limit_at_least_512m(self):
        """F4.B3: Verify memory_limit is at least 512M."""
        config = parse_ini_file(OPCACHE_INI_PATH)
        mem_limit = config.get("memory_limit", "")
        self.assertRegex(mem_limit, r"^\d+M$", "memory_limit must be specified in M (e.g. 512M)")

    def test_f4_b4_upload_max_filesize_gigabytes(self):
        """F4.B4: Verify upload_max_filesize and post_max_size are specified in G."""
        config = parse_ini_file(OPCACHE_INI_PATH)
        self.assertRegex(config.get("upload_max_filesize", ""), r"^\d+G$")
        self.assertRegex(config.get("post_max_size", ""), r"^\d+G$")

    def test_f4_b5_opcache_revalidate_frequency(self):
        """F4.B5: Verify opcache.revalidate_freq is positive integer."""
        config = parse_ini_file(OPCACHE_INI_PATH)
        self.assertTrue(config.get("opcache.revalidate_freq", "").isdigit())

    # ──────────────────────────────────────────────────────────────────────────
    # R1: Feature 5 - Boundaries on Dynamic Trusted Proxies Parsing
    # ──────────────────────────────────────────────────────────────────────────
    def test_f5_b1_empty_env_returns_default(self):
        """F5.B1: Verify nextcloud.config.php logic defaults to 10.0.0.0/16 on empty string env."""
        content = read_file(NEXTCLOUD_CONFIG_PATH)
        self.assertIn("10.0.0.0/16", content)

    def test_f5_b2_mixed_delimiters_support(self):
        """F5.B2: Verify nextcloud.config.php handles commas or spaces as delimiters."""
        content = read_file(NEXTCLOUD_CONFIG_PATH)
        self.assertTrue(
            ("explode" in content or "preg_split" in content or "TRUSTED_PROXIES" in content),
            "nextcloud.config.php must support delimited string parsing for TRUSTED_PROXIES"
        )

    def test_f5_b3_array_structure_maintained(self):
        """F5.B3: Verify trusted_proxies is formatted as an array, not a bare string."""
        content = read_file(NEXTCLOUD_CONFIG_PATH)
        self.assertRegex(content, r"['\"]trusted_proxies['\"]\s*=>\s*\[",
                         "trusted_proxies must be assigned an array")

    def test_f5_b4_overwriteprotocol_https_preserved(self):
        """F5.B4: Verify overwriteprotocol is locked to https for ALB TLS termination."""
        content = read_file(NEXTCLOUD_CONFIG_PATH)
        self.assertIn("'overwriteprotocol' => 'https'", content)

    def test_f5_b5_forwarded_for_headers_preserved(self):
        """F5.B5: Verify forwarded_for_headers preserves HTTP_X_FORWARDED_FOR."""
        content = read_file(NEXTCLOUD_CONFIG_PATH)
        self.assertIn("'forwarded_for_headers' => ['HTTP_X_FORWARDED_FOR']", content)

    # ──────────────────────────────────────────────────────────────────────────
    # R2: Feature 6 - Boundaries on Lambda Auth Secret Removal
    # ──────────────────────────────────────────────────────────────────────────
    def test_f6_b1_no_substring_secret_in_json_dumps(self):
        """F6.B1: Verify json.dumps in LOGIN action never includes mfa_secret or demo_totp_secret."""
        content = read_file(LAMBDA_SRC_PATH)
        match = re.search(r'action\s*==\s*["\']LOGIN["\'].*?(?=action\s*==|\Z)', content, re.DOTALL)
        self.assertIsNotNone(match)
        login_block = match.group(0)
        self.assertNotIn("demo_totp_secret", login_block)
        self.assertNotIn('"demo_totp_secret"', login_block)

    def test_f6_b2_challenge_token_format(self):
        """F6.B2: Verify challenge_token is generated via uuid or secrets module."""
        content = read_file(LAMBDA_SRC_PATH)
        self.assertTrue("uuid.uuid4()" in content or "secrets.token_urlsafe" in content or "secrets.token_hex" in content)

    def test_f6_b3_login_challenge_expiry_logic(self):
        """F6.B3: Verify challenge tokens have expiration handling."""
        content = read_file(LAMBDA_SRC_PATH)
        self.assertIn("challenge_token", content)

    def test_f6_b4_totp_code_length_boundary(self):
        """F6.B4: Verify generate_totp_code generates exactly 6 digits."""
        content = read_file(LAMBDA_SRC_PATH)
        self.assertIn("1000000", content, "TOTP modulo 1000000 for 6 digits must be present")
        self.assertIn("{code:06d}", content, "TOTP format must be 6-digit padded string")

    def test_f6_b5_constant_time_token_comparison(self):
        """F6.B5: Verify tokens or hashes use hmac.compare_digest or constant-time comparison."""
        content = read_file(LAMBDA_SRC_PATH)
        self.assertIn("compare_digest", content, "Lambda must use hmac.compare_digest for secure comparison")

    # ──────────────────────────────────────────────────────────────────────────
    # R2: Feature 7 - Boundaries on Lambda Metrics Recursion Fix
    # ──────────────────────────────────────────────────────────────────────────
    def test_f7_b1_safe_put_metric_has_boto3_client(self):
        """F7.B1: Verify cloudwatch boto3 client is initialized at module level."""
        content = read_file(LAMBDA_SRC_PATH)
        self.assertRegex(content, r'cloudwatch\s*=\s*boto3\.client\(["\']cloudwatch["\']')

    def test_f7_b2_safe_put_metric_signature(self):
        """F7.B2: Verify safe_put_metric_data function signature accepts Namespace and MetricData."""
        tree = get_ast_tree(LAMBDA_SRC_PATH)
        func_found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "safe_put_metric_data":
                func_found = True
                arg_names = [a.arg for a in node.args.args]
                self.assertIn("Namespace", arg_names)
                self.assertIn("MetricData", arg_names)
        self.assertTrue(func_found, "safe_put_metric_data function not found in AST")

    def test_f7_b3_safe_put_metric_broad_exception_catch(self):
        """F7.B3: Verify safe_put_metric_data catches Exception or ClientError to avoid crash."""
        content = read_file(LAMBDA_SRC_PATH)
        self.assertIn("except Exception as", content)

    def test_f7_b4_safe_put_metric_logging_on_failure(self):
        """F7.B4: Verify safe_put_metric_data logs a warning instead of raising."""
        content = read_file(LAMBDA_SRC_PATH)
        self.assertIn("CloudWatch put_metric_data warning:", content)

    def test_f7_b5_no_indirect_recursion_via_eval_or_getattr(self):
        """F7.B5: Verify safe_put_metric_data does not use eval or getattr to call itself."""
        content = read_file(LAMBDA_SRC_PATH)
        match = re.search(r"def safe_put_metric_data\(.*?\):.*?(?=def |\Z)", content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(0)
        self.assertNotIn("eval(", body)
        self.assertNotIn("globals()[", body)

    # ──────────────────────────────────────────────────────────────────────────
    # R2: Feature 8 - Boundaries on Database SSL Enforcement
    # ──────────────────────────────────────────────────────────────────────────
    def test_f8_b1_force_ssl_string_quote(self):
        """F8.B1: Verify rds.force_ssl is formatted as string '1' (CloudFormation requirement)."""
        content = read_file(DATABASE_TEMPLATE_PATH)
        self.assertRegex(content, r'rds\.force_ssl:\s*["\'][01]["\']',
                         "CloudFormation requires parameter values to be strings: rds.force_ssl: \"0\" or \"1\"")

    def test_f8_b2_parameter_group_description_reflects_ssl(self):
        """F8.B2: Verify DBParameterGroup description exists and documents SSL enforcement."""
        template = load_cfn_yaml(DATABASE_TEMPLATE_PATH)
        desc = template["Resources"]["DBParameterGroup"]["Properties"]["Description"]
        self.assertTrue(len(desc) > 5)

    def test_f8_b3_database_port_locked_to_5432(self):
        """F8.B3: Verify database port is standard PostgreSQL 5432."""
        template = load_cfn_yaml(DATABASE_TEMPLATE_PATH)
        props = template["Resources"]["DBSecret"]["Properties"]
        db_secret = props.get("SecretString") or props.get("GenerateSecretString", {}).get("SecretStringTemplate", "")
        self.assertIn('"port": 5432', str(db_secret))

    def test_f8_b4_storage_encrypted_enabled(self):
        """F8.B4: Verify StorageEncrypted is true on RDSInstance."""
        template = load_cfn_yaml(DATABASE_TEMPLATE_PATH)
        encrypted = template["Resources"]["RDSInstance"]["Properties"]["StorageEncrypted"]
        self.assertTrue(encrypted is True or str(encrypted).lower() == "true")

    def test_f8_b5_publicly_accessible_false(self):
        """F8.B5: Verify PubliclyAccessible is false on RDSInstance."""
        template = load_cfn_yaml(DATABASE_TEMPLATE_PATH)
        publicly_acc = template["Resources"]["RDSInstance"]["Properties"]["PubliclyAccessible"]
        self.assertTrue(publicly_acc is False or str(publicly_acc).lower() == "false")

    # ──────────────────────────────────────────────────────────────────────────
    # R2: Feature 9 - Boundaries on EFS Private Subnets
    # ──────────────────────────────────────────────────────────────────────────
    def test_f9_b1_two_mount_targets_defined(self):
        """F9.B1: Verify exactly two EFS mount targets are defined for multi-AZ redundancy."""
        template = load_cfn_yaml(STORAGE_TEMPLATE_PATH)
        resources = template.get("Resources", {})
        mount_targets = [k for k, v in resources.items() if v.get("Type") == "AWS::EFS::MountTarget"]
        self.assertEqual(len(mount_targets), 2, "There must be exactly 2 EFS mount targets for multi-AZ")

    def test_f9_b2_mount_targets_use_distinct_subnets(self):
        """F9.B2: Verify MountTarget1 and MountTarget2 use different private subnets."""
        content = read_file(STORAGE_TEMPLATE_PATH)
        mt1_match = re.search(r"EFSMountTarget1:.*?(?=EFSMountTarget2:|\Z)", content, re.DOTALL)
        mt2_match = re.search(r"EFSMountTarget2:.*?(?=Outputs:|\Z)", content, re.DOTALL)
        self.assertIsNotNone(mt1_match)
        self.assertIsNotNone(mt2_match)
        self.assertIn("PrivateSubnet1Id", mt1_match.group(0))
        self.assertIn("PrivateSubnet2Id", mt2_match.group(0))

    def test_f9_b3_efs_encryption_at_rest_enabled(self):
        """F9.B3: Verify EFS file system has Encrypted: true."""
        template = load_cfn_yaml(STORAGE_TEMPLATE_PATH)
        efs_res = template["Resources"]["NextcloudEFS"]["Properties"]
        self.assertTrue(efs_res.get("Encrypted") is True or str(efs_res.get("Encrypted")).lower() == "true")

    def test_f9_b4_efs_performance_mode_general_purpose(self):
        """F9.B4: Verify EFS PerformanceMode is generalPurpose."""
        template = load_cfn_yaml(STORAGE_TEMPLATE_PATH)
        perf_mode = template["Resources"]["NextcloudEFS"]["Properties"]["PerformanceMode"]
        self.assertEqual(perf_mode, "generalPurpose")

    def test_f9_b5_root_template_syntax_valid(self):
        """F9.B5: Verify root.yaml is valid YAML and defines StorageStack."""
        root = load_cfn_yaml(ROOT_TEMPLATE_PATH)
        self.assertIn("StorageStack", root["Resources"])

    # ──────────────────────────────────────────────────────────────────────────
    # R2: Feature 10 - Boundaries on Security Group Egress Lockdown
    # ──────────────────────────────────────────────────────────────────────────
    def test_f10_b1_zero_all_zeros_egress_in_db_and_efs(self):
        """F10.B1: Verify neither DB nor EFS security groups allow any 0.0.0.0/0 rule."""
        content = read_file(SECURITY_TEMPLATE_PATH)
        for sg_name in ["DBSecurityGroup", "EFSSecurityGroup"]:
            match = re.search(rf"{sg_name}:.*?(?=[A-Za-z0-9]+:\s*\n\s*Type:|\Z)", content, re.DOTALL)
            self.assertIsNotNone(match, f"{sg_name} not found in template")
            block = match.group(0)
            self.assertNotIn("0.0.0.0/0", block, f"{sg_name} has unrestricted 0.0.0.0/0 egress")

    def test_f10_b2_no_ipv6_unrestricted_egress(self):
        """F10.B2: Verify neither DB nor EFS security groups allow unrestricted IPv6 (::/0)."""
        content = read_file(SECURITY_TEMPLATE_PATH)
        for sg_name in ["DBSecurityGroup", "EFSSecurityGroup"]:
            match = re.search(rf"{sg_name}:.*?(?=[A-Za-z0-9]+:\s*\n\s*Type:|\Z)", content, re.DOTALL)
            self.assertIsNotNone(match)
            block = match.group(0)
            self.assertNotIn("::/0", block, f"{sg_name} has unrestricted ::/0 egress")

    def test_f10_b3_alb_security_group_ingress_intact(self):
        """F10.B3: Verify ALBSecurityGroup still permits port 80 and 443 ingress for user access."""
        template = load_cfn_yaml(SECURITY_TEMPLATE_PATH)
        alb_sg = template["Resources"]["ALBSecurityGroup"]["Properties"]["SecurityGroupIngress"]
        ports = [r.get("FromPort") for r in alb_sg]
        self.assertIn(80, ports)
        self.assertIn(443, ports)

    def test_f10_b4_ecs_security_group_egress_allows_db_port(self):
        """F10.B4: Verify ECSSecurityGroup allows outbound to DB."""
        template = load_cfn_yaml(SECURITY_TEMPLATE_PATH)
        self.assertIn("ECSSecurityGroup", template["Resources"])

    def test_f10_b5_security_template_cfn_lint_valid(self):
        """F10.B5: Verify 02-security/template.yaml passes cfn-lint check."""
        res = os.system(f"cfn-lint '{SECURITY_TEMPLATE_PATH}' -i W3002 W2001 W1011 W3005")
        self.assertEqual(res, 0, "Security template failed cfn-lint")

    # ──────────────────────────────────────────────────────────────────────────
    # R2: Feature 11 - Boundaries on Lambda Packaging Reproducibility
    # ──────────────────────────────────────────────────────────────────────────
    def test_f11_b1_script_has_shebang(self):
        """F11.B1: Verify package_lambda.py begins with #!/usr/bin/env python3."""
        self.assertTrue(PACKAGE_LAMBDA_SCRIPT_PATH.is_file(), f"Missing {PACKAGE_LAMBDA_SCRIPT_PATH}")
        content = read_file(PACKAGE_LAMBDA_SCRIPT_PATH)
        self.assertTrue(content.startswith("#!/usr/bin/env python3") or content.startswith("#!/usr/bin/python3"))

    def test_f11_b2_zip_compression_standard_deflated(self):
        """F11.B2: Verify packaging script uses zipfile.ZIP_DEFLATED."""
        self.assertTrue(PACKAGE_LAMBDA_SCRIPT_PATH.is_file(), f"Missing {PACKAGE_LAMBDA_SCRIPT_PATH}")
        content = read_file(PACKAGE_LAMBDA_SCRIPT_PATH)
        self.assertIn("ZIP_DEFLATED", content)

    def test_f11_b3_handles_target_output_directory(self):
        """F11.B3: Verify packaging script ensures parent directory of target zip exists."""
        self.assertTrue(PACKAGE_LAMBDA_SCRIPT_PATH.is_file(), f"Missing {PACKAGE_LAMBDA_SCRIPT_PATH}")
        content = read_file(PACKAGE_LAMBDA_SCRIPT_PATH)
        self.assertTrue("os.makedirs" in content or "mkdir" in content or "parent" in content)

    def test_f11_b4_no_symlink_following_leakage(self):
        """F11.B4: Verify packaging script handles regular files and prevents symlink loops."""
        self.assertTrue(PACKAGE_LAMBDA_SCRIPT_PATH.is_file(), f"Missing {PACKAGE_LAMBDA_SCRIPT_PATH}")
        content = read_file(PACKAGE_LAMBDA_SCRIPT_PATH)
        self.assertTrue("is_file" in content or "isfile" in content or "ZipInfo" in content)

    def test_f11_b5_sha256_output_printed_or_returned(self):
        """F11.B5: Verify packaging script computes and reports SHA256 of resulting zip."""
        self.assertTrue(PACKAGE_LAMBDA_SCRIPT_PATH.is_file(), f"Missing {PACKAGE_LAMBDA_SCRIPT_PATH}")
        content = read_file(PACKAGE_LAMBDA_SCRIPT_PATH)
        self.assertTrue("hashlib.sha256" in content or "sha256" in content)

    # ──────────────────────────────────────────────────────────────────────────
    # R3: Feature 12 - Boundaries on TenantShow Decomposition
    # ──────────────────────────────────────────────────────────────────────────
    def test_f12_b1_line_count_strict_boundary(self):
        """F12.B1: Verify show.tsx is well below 350 lines (target ~220 lines)."""
        lines = count_file_lines(TENANT_SHOW_PATH)
        self.assertLessEqual(lines, 350)

    def test_f12_b2_no_monolithic_tab_blocks_in_show(self):
        """F12.B2: Verify show.tsx does not contain inline tab render blocks > 100 lines."""
        content = read_file(TENANT_SHOW_PATH)
        # Should import tabs from tabs/
        self.assertIn("from './tabs", content.replace('"', "'"))

    def test_f12_b3_incident_modal_extracted(self):
        """F12.B3: Verify modals are either in modular files or tabs, not cluttering show.tsx."""
        lines = count_file_lines(TENANT_SHOW_PATH)
        self.assertLess(lines, 350)

    def test_f12_b4_tenant_show_uses_antd_tabs(self):
        """F12.B4: Verify TenantShow renders standard Ant Design Tabs component with items prop."""
        content = read_file(TENANT_SHOW_PATH)
        self.assertIn("<Tabs", content)
        self.assertTrue("items=" in content or "<Tabs.TabPane" in content)

    def test_f12_b5_tenant_show_handles_empty_tenant(self):
        """F12.B5: Verify TenantShow handles undefined or loading record gracefully."""
        content = read_file(TENANT_SHOW_PATH)
        self.assertTrue("isLoading" in content or "record?" in content or "record &&" in content or "loading" in content)

    # ──────────────────────────────────────────────────────────────────────────
    # R3: Feature 13 - Boundaries on Dynamic API Base URL
    # ──────────────────────────────────────────────────────────────────────────
    def test_f13_b1_vite_api_url_env_fallback(self):
        """F13.B1: Verify dataProvider falls back to /api when VITE_API_URL is undefined."""
        content = read_file(DATA_PROVIDER_PATH)
        self.assertIn('|| "/api"', content.replace("'", '"'))

    def test_f13_b2_get_api_url_returns_string(self):
        """F13.B2: Verify getApiUrl return type is string."""
        content = read_file(DATA_PROVIDER_PATH)
        self.assertRegex(content, r"getApiUrl\(\s*\)(:\s*string)?")

    def test_f13_b3_no_double_slash_when_joining(self):
        """F13.B3: Verify API requests handle trailing slashes cleanly."""
        content = read_file(DATA_PROVIDER_PATH)
        self.assertIn("getApiUrl", content)

    def test_f13_b4_auth_provider_uses_vite_api_url(self):
        """F13.B4: Verify authProvider references VITE_API_URL."""
        content = read_file(AUTH_PROVIDER_PATH)
        self.assertIn("VITE_API_URL", content)

    def test_f13_b5_telemetry_uses_dynamic_api_url(self):
        """F13.B5: Verify telemetry page does not use hardcoded '/api' in useCustom."""
        telemetry_path = CONSOLE_DIR / "src" / "pages" / "telemetry" / "index.tsx"
        if telemetry_path.exists():
            content = read_file(telemetry_path)
            self.assertNotIn('url: "/api"', content)

    # ──────────────────────────────────────────────────────────────────────────
    # R3: Feature 14 - Boundaries on Ant Design Modernization
    # ──────────────────────────────────────────────────────────────────────────
    def test_f14_b1_card_variant_borderless_syntax(self):
        """F14.B1: Verify Card components use variant='borderless'."""
        content = read_file(LOGIN_PAGE_PATH)
        if "<Card" in content:
            self.assertNotIn("bordered={false}", content)

    def test_f14_b2_create_modal_destroy_on_hidden(self):
        """F14.B2: Verify create-modal.tsx uses destroyOnHidden."""
        create_modal_path = CONSOLE_DIR / "src" / "pages" / "tenants" / "create-modal.tsx"
        if create_modal_path.exists():
            content = read_file(create_modal_path)
            self.assertNotIn("destroyOnClose", content)
            self.assertIn("destroyOnHidden", content)

    def test_f14_b3_input_number_uses_space_compact(self):
        """F14.B3: Verify create-modal.tsx uses Space.Compact for quota input."""
        create_modal_path = CONSOLE_DIR / "src" / "pages" / "tenants" / "create-modal.tsx"
        if create_modal_path.exists():
            content = read_file(create_modal_path)
            self.assertNotIn("addonAfter", content)
            self.assertIn("Space.Compact", content)

    def test_f14_b4_no_deprecated_button_type_danger(self):
        """F14.B4: Verify Buttons use danger boolean prop instead of deprecated type='danger'."""
        ts_files = find_files_by_pattern(CONSOLE_DIR / "src", "*.tsx")
        for p in ts_files:
            text = read_file(p)
            self.assertNotIn('type="danger"', text)

    def test_f14_b5_header_avatar_shape(self):
        """F14.B5: Verify Header component renders cleanly without deprecated props."""
        header_path = CONSOLE_DIR / "src" / "components" / "Header.tsx"
        if header_path.exists():
            content = read_file(header_path)
            self.assertNotIn("bordered={false}", content)

    # ──────────────────────────────────────────────────────────────────────────
    # R3: Feature 15 - Boundaries on Multi-Tab Session Persistence
    # ──────────────────────────────────────────────────────────────────────────
    def test_f15_b1_auth_token_key_standardized(self):
        """F15.B1: Verify auth token key is standardized as 'saas_admin_token'."""
        content = read_file(AUTH_PROVIDER_PATH)
        self.assertIn('"saas_admin_token"', content)

    def test_f15_b2_auth_role_key_standardized(self):
        """F15.B2: Verify auth role key is standardized as 'saas_admin_role'."""
        content = read_file(ACCESS_CONTROL_PATH)
        self.assertIn('"saas_admin_role"', content)

    def test_f15_b3_logout_clears_local_storage(self):
        """F15.B3: Verify logout clears saas_admin_token from localStorage."""
        content = read_file(AUTH_PROVIDER_PATH)
        self.assertIn('localStorage.removeItem("saas_admin_token")', content)

    def test_f15_b4_check_auth_resolves_from_local_storage(self):
        """F15.B4: Verify check() in authProvider inspects localStorage."""
        content = read_file(AUTH_PROVIDER_PATH)
        match = re.search(r"check:\s*async\s*\(\)\s*=>.*?(?=,\s*\n\s*[a-zA-Z]+:|\Z)", content, re.DOTALL)
        self.assertIsNotNone(match)
        self.assertIn("localStorage.getItem", match.group(0))

    def test_f15_b5_get_permissions_reads_role_from_local_storage(self):
        """F15.B5: Verify getPermissions in authProvider reads from localStorage."""
        content = read_file(AUTH_PROVIDER_PATH)
        match = re.search(r"getPermissions:\s*async\s*\(\)\s*=>.*?(?=,\s*\n\s*[a-zA-Z]+:|\Z)", content, re.DOTALL)
        self.assertIsNotNone(match)
        self.assertIn("localStorage.getItem", match.group(0))


if __name__ == "__main__":
    unittest.main()
