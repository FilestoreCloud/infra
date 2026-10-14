#!/usr/bin/env python3
"""
Deterministic and Reproducible Lambda Packaging Script for Storix Control Plane.
Packages tenant_operator_lambda.py into index.py inside a standardized zip archive.
Normalizes file timestamps, POSIX permissions, excludes bytecode artifacts,
and prints the resulting SHA256 checksum.
"""

import argparse
import hashlib
import os
import sys
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "infra", "modules", "06-superadmin"))
DEFAULT_SOURCE = os.path.join(MODULE_DIR, "tenant_operator_lambda.py")
DEFAULT_OUTPUT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "build", "tenant_operator.zip"))

# Fixed timestamp (1980-01-01 00:00:00) for deterministic zip output
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
# Standard POSIX permissions (0o644 readable by all, writable by owner)
FIXED_FILE_PERMISSIONS = 0o644 << 16


def package_lambda(source_path=DEFAULT_SOURCE, output_path=DEFAULT_OUTPUT):
    """Packages the source file into a deterministic zip archive."""
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"Lambda source not found at: {source_path}")

    # Exclude bytecode or cache artifacts
    if source_path.endswith(".pyc") or "__pycache__" in source_path:
        raise ValueError("Cannot package bytecode or __pycache__ artifacts.")

    # Ensure parent directory of target zip exists
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(source_path, "rb") as f:
        content = f.read()

    # Create deterministic zip archive
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zinfo = zipfile.ZipInfo(filename="index.py", date_time=FIXED_ZIP_TIMESTAMP)
        zinfo.external_attr = FIXED_FILE_PERMISSIONS
        zinfo.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(zinfo, content)

    # Compute and report SHA256 hash
    sha256 = hashlib.sha256()
    with open(output_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    digest = sha256.hexdigest()

    print(f"✅ Successfully packaged {source_path} -> {output_path}")
    print(f"📦 SHA256: {digest}")
    return digest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Package tenant_operator_lambda.py deterministically.")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Path to tenant_operator_lambda.py")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Path to destination zip file")
    args = parser.parse_args()

    try:
        package_lambda(args.source, args.output)
    except Exception as err:
        print(f"Error packaging lambda: {err}", file=sys.stderr)
        sys.exit(1)
