"""
CloudFormation Security & Policy Compliance Invariant Tests.
Validates that CloudFormation templates comply with CIS AWS Foundations benchmarks
and Prisma Cloud / Checkov security rules.
"""
import shutil
import subprocess
import unittest
from pathlib import Path

INFRA_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = INFRA_ROOT / "infra" / "modules"
if not TEMPLATES_DIR.exists():
    TEMPLATES_DIR = INFRA_ROOT / "modules"


class TestCloudFormationSecurityCheckov(unittest.TestCase):
    def test_networking_template_passes_checkov_security_rules(self):
        """Ensure 01-networking template passes all AWS Security Group and SSM Parameter security policies."""
        checkov_bin = shutil.which("checkov")
        if not checkov_bin:
            self.skipTest("checkov binary not installed on PATH")

        template_path = TEMPLATES_DIR / "01-networking" / "template.yaml"
        self.assertTrue(template_path.exists(), f"Networking template not found at {template_path}")

        cmd = [
            checkov_bin,
            "-f",
            str(template_path),
            "--framework",
            "cloudformation",
            "--output",
            "json",
            "--quiet",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        # Checkov returns code 0 when all checks pass
        self.assertEqual(
            result.returncode,
            0,
            f"Checkov detected security policy violations in {template_path}:\n{result.stdout}",
        )
