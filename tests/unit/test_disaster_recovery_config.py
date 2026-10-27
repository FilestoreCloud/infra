"""Unit tests verifying Multi-Region Disaster Recovery CloudFormation configurations."""

import unittest
from pathlib import Path

MODULES_DIR = Path(__file__).resolve().parents[2] / "infra" / "modules"
if not MODULES_DIR.exists():
    MODULES_DIR = Path(__file__).resolve().parents[2] / "modules"


class TestDisasterRecoveryConfig(unittest.TestCase):
    """Verifies S3 Cross-Region Replication, Aurora Global DB, and Failover SAGA."""

    def test_s3_cross_region_replication_configuration(self):
        """Verify 03-storage template has S3 CRR, Replication Time Control, and Role."""
        template_file = MODULES_DIR / "03-storage" / "template.yaml"
        content = template_file.read_text(encoding="utf-8")

        self.assertIn("EnableCrossRegionReplication", content)
        self.assertIn("DRDestinationRegion", content)
        self.assertIn("S3ReplicationRole", content)
        self.assertIn("ReplicationConfiguration", content)
        self.assertIn("StorixDisasterRecoveryReplication", content)
        self.assertIn("ReplicationTime", content)
        self.assertIn("Minutes: 15", content)

    def test_s3_malware_quarantine_bucket(self):
        """Verify 03-storage template includes dedicated Quarantine Bucket."""
        template_file = MODULES_DIR / "03-storage" / "template.yaml"
        content = template_file.read_text(encoding="utf-8")

        self.assertIn("EnableMalwareProtection", content)
        self.assertIn("QuarantineBucket", content)
        self.assertIn("MalwareQuarantineIsolation", content)

    def test_aurora_global_database_configuration(self):
        """Verify 04-database template-aurora has Aurora Global Cluster configuration."""
        template_file = MODULES_DIR / "04-database" / "template-aurora.yaml"
        content = template_file.read_text(encoding="utf-8")

        self.assertIn("EnableGlobalDatabase", content)
        self.assertIn("AuroraGlobalCluster", content)
        self.assertIn("AWS::RDS::GlobalCluster", content)
        self.assertIn("GlobalClusterIdentifier", content)

    def test_failover_saga_state_machine_definition(self):
        """Verify 06-superadmin failover_saga.yaml defines valid SAGA state transitions."""
        template_file = MODULES_DIR / "06-superadmin" / "failover_saga.yaml"
        self.assertTrue(template_file.exists(), f"failover_saga.yaml missing at {template_file}")

        content = template_file.read_text(encoding="utf-8")
        self.assertIn("AWS::StepFunctions::StateMachine", content)
        self.assertIn("DRFailoverSagaRole", content)
        self.assertIn("PromoteAuroraGlobalCluster", content)
        self.assertIn("ScaleUpDRFargateFleet", content)
        self.assertIn("SwitchRoute53DNSFailover", content)
        self.assertIn("CompensatingRollbackNotice", content)


if __name__ == "__main__":
    unittest.main()
