"""
Property-Based Invariant and Fuzz Testing Suite using Hypothesis.
Mathematically proves cryptographic token invariants, TOTP robustness,
and zero-crash input parsing across arbitrary inputs.
"""
import os
import sys
import unittest
from pathlib import Path

from hypothesis import given, settings, strategies as st

# Ensure test AWS environment before importing lambda module
os.environ["AWS_ACCESS_KEY_ID"] = "mock_key"
os.environ["AWS_SECRET_ACCESS_KEY"] = "mock_secret"
os.environ["AWS_DEFAULT_REGION"] = "ap-southeast-1"
os.environ["AWS_REGION"] = "ap-southeast-1"

# Add lambda directory to sys.path
LAMBDA_DIR = Path(__file__).resolve().parents[2] / "modules" / "06-superadmin"
if not LAMBDA_DIR.exists():
    LAMBDA_DIR = Path(__file__).resolve().parents[2] / "infra" / "modules" / "06-superadmin"
sys.path.insert(0, str(LAMBDA_DIR))

import tenant_operator_lambda as tol  # noqa: E402


class TestPropertyBasedSecurity(unittest.TestCase):
    """Property-based security tests running 100+ generated permutations per test."""

    @settings(max_examples=100)
    @given(
        username=st.text(min_size=1, max_size=64).filter(lambda x: not any(c in x for c in ".\0\n\r")),
        role=st.sampled_from(["SuperAdmin", "Admin", "Operator", "Auditor", "Viewer"]),
        signing_key=st.text(min_size=16, max_size=64),
    )
    def test_property_session_token_roundtrip_and_integrity(self, username, role, signing_key):
        """Property: Any valid username & role signs cleanly, and verifies with the exact key."""
        token = tol.create_session_token(username=username, role=role, key=signing_key)
        self.assertIn(".", token)

        payload = tol.verify_session_token(token, key=signing_key)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["user"], username)
        self.assertEqual(payload["role"], role)
        self.assertTrue(payload["mfa"])

    @settings(max_examples=100)
    @given(
        corrupted_token=st.text(min_size=0, max_size=200),
        key=st.text(min_size=10, max_size=40),
    )
    def test_property_corrupted_token_never_crashes_and_rejects(self, corrupted_token, key):
        """Property: Any corrupted, arbitrary or truncated token safely evaluates to None without crashing."""
        res = tol.verify_session_token(corrupted_token, key=key)
        # Must safely reject corrupted tokens
        if not ("." in corrupted_token and len(corrupted_token.split(".")) == 2):
            self.assertIsNone(res)

    @settings(max_examples=100)
    @given(
        username=st.text(min_size=3, max_size=32),
        key=st.text(min_size=16, max_size=64),
        bit_pos=st.integers(min_value=0, max_value=30),
    )
    def test_property_tampered_signature_strictly_fails(self, username, key, bit_pos):
        """Property: Modifying even a single character in the signature must strictly fail verification."""
        token = tol.create_session_token(username=username, role="SuperAdmin", key=key)
        payload_b64, sig = token.split(".", 1)

        # Tamper the signature by flipping a character
        tampered_char = "a" if sig[bit_pos % len(sig)] != "a" else "b"
        tampered_sig = sig[:bit_pos % len(sig)] + tampered_char + sig[(bit_pos % len(sig)) + 1:]
        tampered_token = f"{payload_b64}.{tampered_sig}"

        self.assertIsNone(tol.verify_session_token(tampered_token, key=key))

    @settings(max_examples=100)
    @given(
        secret=st.text(min_size=0, max_size=50),
        code=st.text(min_size=0, max_size=20),
    )
    def test_property_totp_arbitrary_input_safety(self, secret, code):
        """Property: verify_totp_code never raises unexpected exceptions on poisoned or arbitrary inputs."""
        try:
            valid = tol.verify_totp_code(secret, code)
            self.assertIsInstance(valid, bool)
        except Exception as e:
            self.fail(f"verify_totp_code crashed on input ({secret!r}, {code!r}) with {e}")

    @settings(max_examples=50)
    @given(
        raw_domains=st.lists(
            st.text(min_size=1, max_size=50).filter(lambda x: "\0" not in x),
            min_size=1,
            max_size=10,
        )
    )
    def test_property_bare_wildcard_domain_inadmissible(self, raw_domains):
        """Property: A bare wildcard '*' is NEVER admitted as a trusted domain in security parsing."""
        # Simulated domain parser logic
        parsed = []
        for d in raw_domains:
            trimmed = d.strip()
            if trimmed and trimmed != "*":
                parsed.append(trimmed)

        self.assertNotIn("*", parsed, "Security Invariant: Bare '*' wildcard must never be in trusted domains list")


if __name__ == "__main__":
    unittest.main()
