"""Unit tests verifying CloudFormation OpenSearch and Tika Extractor definitions."""

import unittest
from pathlib import Path

MODULES_DIR = Path(__file__).resolve().parents[2] / "infra" / "modules"
if not MODULES_DIR.exists():
    MODULES_DIR = Path(__file__).resolve().parents[2] / "modules"


class TestOpenSearchCloudFormation(unittest.TestCase):
    """Verifies OpenSearch CloudFormation template and ECS sidecar integration."""

    def test_opensearch_template_structure(self):
        """Verify opensearch.yaml parameters, resources, and outputs."""
        template_file = MODULES_DIR / "05-compute" / "opensearch.yaml"
        self.assertTrue(template_file.exists(), f"opensearch.yaml missing at {template_file}")

        content = template_file.read_text(encoding="utf-8")
        self.assertIn("AWS::OpenSearchService::Domain", content)
        self.assertIn("OpenSearchSecurityGroup", content)
        self.assertIn("SSMOpenSearchEndpoint", content)
        self.assertIn("SSMOpenSearchDomainArn", content)

        # Invariant: Port 443 HTTPS only
        self.assertIn("FromPort: 443", content)
        self.assertIn("ToPort: 443", content)
        self.assertIn("EnforceHTTPS: true", content)
        self.assertIn("Policy-Min-TLS-1-2-2019-07", content)

        # Node-to-node and at-rest encryption
        self.assertIn("NodeToNodeEncryptionOptions", content)
        self.assertIn("EncryptionAtRestOptions", content)

    def test_compute_template_tika_sidecar_integration(self):
        """Verify 05-compute template includes Tika extractor and OpenSearch parameters."""
        template_file = MODULES_DIR / "05-compute" / "template.yaml"
        content = template_file.read_text(encoding="utf-8")

        # OpenSearch parameters
        self.assertIn("OpenSearchEndpoint", content)
        self.assertIn("EnableTikaExtractor", content)

        # Environment bindings
        self.assertIn("OPENSEARCH_HOST", content)
        self.assertIn("TIKA_HOST", content)
        self.assertIn("TIKA_PORT", content)

        # Tika sidecar container
        self.assertIn("tika-extractor", content)
        self.assertIn("apache/tika:2.9.2.0", content)
        self.assertIn("ContainerPort: 9998", content)


if __name__ == "__main__":
    unittest.main()
