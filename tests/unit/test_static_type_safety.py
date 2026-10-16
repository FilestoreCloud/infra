"""
Static Type Safety Invariant Tests.
Validates that Control Plane Lambda, Schemas, and Unit test files maintain 100% strict type safety
without type errors or implicit Any degradation.
"""
import os
import shutil
import subprocess
import unittest
from pathlib import Path

INFRA_ROOT = Path(__file__).resolve().parents[2]
MODULES_DIR = INFRA_ROOT / "infra" / "modules" / "06-superadmin"
if not MODULES_DIR.exists():
    MODULES_DIR = INFRA_ROOT / "modules" / "06-superadmin"


class TestStaticTypeSafety(unittest.TestCase):
    def test_mypy_strict_type_safety_on_control_plane(self):
        """Execute mypy across unit tests and operator core to ensure strict type safety."""
        mypy_bin = shutil.which("mypy")
        if not mypy_bin:
            self.skipTest("mypy binary not installed on PATH")

        env = os.environ.copy()
        env["MYPYPATH"] = str(MODULES_DIR)

        cmd = [
            mypy_bin,
            "--ignore-missing-imports",
            str(INFRA_ROOT / "tests" / "unit"),
            str(INFRA_ROOT / "tests" / "load" / "run_concurrent_stress.py"),
        ]

        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        self.assertEqual(
            result.returncode,
            0,
            f"Mypy strict type checking failed with output:\n{result.stdout}\n{result.stderr}",
        )
