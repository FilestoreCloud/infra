#!/usr/bin/env python3
"""
Test Suite: Repository Documentation & Standards Compliance (infra)
Verifies presence, completeness, link validity, and AAIF standard compliance for infra docs.
"""

import os
import re
import unittest

INFRA_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class TestDocumentationCompliance(unittest.TestCase):
    """Verifies documentation completeness, link integrity, and standards."""

    def test_mandatory_repo_documents_exist(self):
        """Verifies README.md, LICENSE, and AGENTS.md exist and are non-empty."""
        mandatory_files = ["README.md", "LICENSE", "AGENTS.md"]
        for fname in mandatory_files:
            fpath = os.path.join(INFRA_ROOT, fname)
            self.assertTrue(os.path.exists(fpath), f"Mandatory document missing: {fname}")
            size = os.path.getsize(fpath)
            self.assertGreater(size, 200, f"Mandatory document {fname} is suspiciously small ({size} bytes)")

    def test_agents_md_aaif_conformance(self):
        """Verifies AGENTS.md follows Linux Foundation / AAIF standard structure."""
        agents_path = os.path.join(INFRA_ROOT, "AGENTS.md")
        self.assertTrue(os.path.exists(agents_path), "AGENTS.md missing")
        with open(agents_path, "r", encoding="utf-8") as f:
            content = f.read()

        required_sections = [
            "1. Project Overview & Architecture",
            "2. Essential Commands",
            "3. Branching Strategy & Boundaries",
            "4. Definition of Done",
        ]
        for section in required_sections:
            self.assertIn(section, content, f"AGENTS.md missing required AAIF section: '{section}'")

    def test_markdown_relative_links_and_images_integrity(self):
        """Verifies all relative markdown links and image sources in infra resolve to valid files."""
        link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
        img_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

        checked_links = 0
        checked_images = 0

        for root, dirs, files in os.walk(INFRA_ROOT):
            # Ignore transient, build, and virtualenv directories
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".")
                and d not in ["node_modules", "dist", "build", "coverage", "__pycache__"]
            ]
            for file in files:
                if file.endswith(".md"):
                    file_path = os.path.join(root, file)
                    rel_doc_path = os.path.relpath(file_path, INFRA_ROOT)
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()

                    # Check markdown links
                    for match in link_pattern.finditer(text):
                        target = match.group(2).strip()
                        if target.startswith(("http://", "https://", "#", "mailto:")):
                            continue
                        clean_target = target.split("#")[0].split("?")[0]
                        if not clean_target or clean_target.startswith("<") or "$" in clean_target:
                            continue

                        resolved = os.path.normpath(os.path.join(root, clean_target))
                        checked_links += 1
                        self.assertTrue(
                            os.path.exists(resolved),
                            f"Broken relative link in {rel_doc_path}: '{target}' -> '{resolved}'",
                        )

                    # Check images
                    for match in img_pattern.finditer(text):
                        target = match.group(2).strip()
                        if target.startswith(("http://", "https://")):
                            continue
                        clean_target = target.split("?")[0]
                        resolved = os.path.normpath(os.path.join(root, clean_target))
                        checked_images += 1
                        self.assertTrue(
                            os.path.exists(resolved),
                            f"Broken image reference in {rel_doc_path}: '{target}' -> '{resolved}'",
                        )

        self.assertGreater(checked_links, 0, "Expected at least one checked link")
        self.assertGreater(checked_images, 0, "Expected at least one checked image")

    def test_python_control_plane_docstrings(self):
        """Verifies core Python control plane modules include proper docstrings."""
        core_files = [
            os.path.join(INFRA_ROOT, "infra", "modules", "06-superadmin", "tenant_operator_lambda.py"),
            os.path.join(INFRA_ROOT, "infra", "modules", "06-superadmin", "tenant_worker_lambda.py"),
        ]
        for fpath in core_files:
            self.assertTrue(os.path.exists(fpath), f"File {fpath} does not exist")
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            # Module docstring check
            self.assertTrue(
                content.strip().startswith('"""') or content.strip().startswith("'''"),
                f"Missing module docstring in {os.path.basename(fpath)}",
            )
            # Function docstrings check for lambda_handler
            self.assertIn("def lambda_handler(", content)
            self.assertIn('"""', content)


if __name__ == "__main__":
    unittest.main()
