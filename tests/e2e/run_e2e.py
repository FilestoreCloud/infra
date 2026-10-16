#!/usr/bin/env python3
"""Storix Platform Unified E2E Test Runner CLI.

Executes 4-tier opaque-box E2E tests across Runtime (R1), Infrastructure (R2),
and Console (R3). Tracks test results and catalogs implementation defects.

Usage:
    python3 tests/e2e/run_e2e.py
    python3 tests/e2e/run_e2e.py --tier 1
    python3 tests/e2e/run_e2e.py --tier 2
    python3 tests/e2e/run_e2e.py --tier 3
    python3 tests/e2e/run_e2e.py --tier 4
    python3 tests/e2e/run_e2e.py --json
    python3 tests/e2e/run_e2e.py -v
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

# Ensure paths are in sys.path
E2E_DIR = Path(__file__).resolve().parent
INFRA_DIR = E2E_DIR.parent.parent
PROJECT_ROOT = INFRA_DIR.parent

for p in [str(E2E_DIR), str(INFRA_DIR), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Color codes
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
RED = "\033[0;31m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner():
    print(f"{BLUE}======================================================================{RESET}")
    print(f"{BOLD}{BLUE}       Storix Multi-Tenant Platform — Unified E2E Test Suite          {RESET}")
    print(f"{BLUE}======================================================================{RESET}")


class StructuredTestResult(unittest.TextTestResult):
    """Custom TestResult that captures test outcomes for reporting."""

    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.test_records: List[Dict[str, Any]] = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.test_records.append({
            "name": test._testMethodName,
            "class": test.__class__.__name__,
            "status": "PASS",
            "message": "",
        })

    def addFailure(self, test, err):
        super().addFailure(test, err)
        msg = self._exc_info_to_string(err, test)
        self.test_records.append({
            "name": test._testMethodName,
            "class": test.__class__.__name__,
            "status": "FAIL",
            "message": msg,
        })

    def addError(self, test, err):
        super().addError(test, err)
        msg = self._exc_info_to_string(err, test)
        self.test_records.append({
            "name": test._testMethodName,
            "class": test.__class__.__name__,
            "status": "ERROR",
            "message": msg,
        })

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.test_records.append({
            "name": test._testMethodName,
            "class": test.__class__.__name__,
            "status": "SKIP",
            "message": reason,
        })


def get_tier_modules(tier: str | int) -> List[str]:
    tier_base = [
        "test_tier1_feature_coverage",
        "test_tier2_boundary_corner",
        "test_tier3_cross_feature",
        "test_tier4_scenarios",
    ]
    prefix = "infra.tests.e2e"
    try:
        __import__(f"{prefix}.{tier_base[0]}")
    except (ImportError, ModuleNotFoundError):
        prefix = "tests.e2e"

    tier_map = {
        "1": [f"{prefix}.test_tier1_feature_coverage"],
        "2": [f"{prefix}.test_tier2_boundary_corner"],
        "3": [f"{prefix}.test_tier3_cross_feature"],
        "4": [f"{prefix}.test_tier4_scenarios"],
        "all": [f"{prefix}.{m}" for m in tier_base],
    }
    return tier_map.get(str(tier).lower(), tier_map["all"])


def run_tests(tier: str = "all", verbose: bool = False, pattern: Optional[str] = None) -> Tuple[StructuredTestResult, float]:
    modules = get_tier_modules(tier)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for mod_name in modules:
        try:
            mod = __import__(mod_name, fromlist=["*"])
            suite.addTests(loader.loadTestsFromModule(mod))
        except Exception as exc:
            print(f"{RED}Error loading {mod_name}: {exc}{RESET}", file=sys.stderr)

    if pattern:
        filtered_suite = unittest.TestSuite()
        for test in suite:
            if isinstance(test, unittest.TestSuite):
                for subtest in test:
                    if pattern in getattr(subtest, "id", lambda: "")():
                        filtered_suite.addTest(subtest)
            elif pattern in getattr(test, "id", lambda: "")():
                filtered_suite.addTest(test)
        suite = filtered_suite

    stream = io.StringIO() if not verbose else sys.stdout
    verbosity = 2 if verbose else 1
    runner = unittest.TextTestRunner(stream=stream, resultclass=StructuredTestResult, verbosity=verbosity)

    start_time = time.time()
    result = cast(StructuredTestResult, runner.run(suite))
    duration = time.time() - start_time

    return result, duration


def main():
    parser = argparse.ArgumentParser(description="Storix E2E Test Runner")
    parser.add_argument("--tier", default="all", choices=["1", "2", "3", "4", "all"], help="Test tier to run")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose test execution output")
    parser.add_argument("--json", action="store_true", help="Output summary in JSON format")
    parser.add_argument("--pattern", default=None, help="Pattern filter for test names")
    parser.add_argument("--allow-failures", action="store_true", help="Always exit 0 even if defects detected")

    args = parser.parse_args()

    if not args.json:
        print_banner()
        print(f"Executing Tier: {BOLD}{args.tier.upper()}{RESET} | Project Root: {PROJECT_ROOT}\n")

    result, duration = run_tests(tier=args.tier, verbose=args.verbose, pattern=args.pattern)

    records = result.test_records
    total = len(records)
    passed = sum(1 for r in records if r["status"] == "PASS")
    failed = sum(1 for r in records if r["status"] == "FAIL")
    errors = sum(1 for r in records if r["status"] == "ERROR")
    skipped = sum(1 for r in records if r["status"] == "SKIP")

    tier_breakdown: Dict[str, Dict[str, int]] = {}
    for r in records:
        cls_name = r["class"]
        tier_breakdown.setdefault(cls_name, {"total": 0, "pass": 0, "fail": 0, "error": 0})
        tier_breakdown[cls_name]["total"] += 1
        if r["status"] == "PASS":
            tier_breakdown[cls_name]["pass"] += 1
        elif r["status"] == "FAIL":
            tier_breakdown[cls_name]["fail"] += 1
        elif r["status"] == "ERROR":
            tier_breakdown[cls_name]["error"] += 1

    summary_data = {
        "tier": args.tier,
        "duration_seconds": round(duration, 3),
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "breakdown": tier_breakdown,
        "defects": [
            {
                "test": r["name"],
                "class": r["class"],
                "status": r["status"],
                "summary": r["message"].splitlines()[-1] if r["message"] else "",
            }
            for r in records if r["status"] in ("FAIL", "ERROR")
        ],
    }

    if args.json:
        print(json.dumps(summary_data, indent=2))
        sys.exit(0 if (failed == 0 and errors == 0) or args.allow_failures else 1)

    # Console Report
    print(f"{BOLD}Tier Execution Breakdown:{RESET}")
    for cls_name, counts in tier_breakdown.items():
        pass_pct = (counts["pass"] / counts["total"] * 100) if counts["total"] else 0.0
        status_color = GREEN if counts["fail"] + counts["error"] == 0 else YELLOW
        print(f"  • {cls_name:<30}: {counts['pass']:>3}/{counts['total']:<3} passed "
              f"({status_color}{pass_pct:5.1f}%{RESET})")

    print(f"\n{BOLD}Overall Results:{RESET}")
    print(f"  Total Tests : {total}")
    print(f"  Passed      : {GREEN}{passed}{RESET}")
    print(f"  Failed      : {RED}{failed}{RESET}")
    print(f"  Errors      : {RED}{errors}{RESET}")
    print(f"  Skipped     : {YELLOW}{skipped}{RESET}")
    print(f"  Duration    : {duration:.2f}s\n")

    if failed > 0 or errors > 0:
        print(f"{YELLOW}----------------------------------------------------------------------{RESET}")
        print(f"{BOLD}{YELLOW}Identified Implementation Defects ({failed + errors} items awaiting remediation):{RESET}")
        print(f"{YELLOW}----------------------------------------------------------------------{RESET}")
        for idx, defect in enumerate(summary_data["defects"], 1):
            print(f"  {idx:2d}. [{defect['class']}] {defect['test']}")
            if defect["summary"]:
                print(f"      {RED}↳ {defect['summary']}{RESET}")
        print()

    if failed == 0 and errors == 0:
        print(f"{GREEN}======================================================================{RESET}")
        print(f"{BOLD}{GREEN}🎉 All {total} E2E tests PASSED! Acceptance criteria verified.{RESET}")
        print(f"{GREEN}======================================================================{RESET}")
        sys.exit(0)
    else:
        print(f"{YELLOW}======================================================================{RESET}")
        print(f"{BOLD}{YELLOW}ℹ E2E Test Suite established. {failed + errors} defects tracked for remediation.{RESET}")
        print(f"{YELLOW}======================================================================{RESET}")
        if args.allow_failures:
            sys.exit(0)
        sys.exit(1)


if __name__ == "__main__":
    main()
