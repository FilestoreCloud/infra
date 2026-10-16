"""
High-Fidelity In-Memory AWS Integration Tests with Moto.
Validates DynamoDB Single-Table OCC, SecretsManager, and CloudWatch metrics.
"""
import os
import sys
import unittest
from pathlib import Path

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

import boto3  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
from moto import mock_aws  # noqa: E402

import operator_core.common as occ  # noqa: E402

# Import control plane utilities
from operator_core.common import (  # noqa: E402
    safe_put_metric_data,
    unmarshal_ddb_item,
)


@mock_aws
class TestAwsMotoIntegration(unittest.TestCase):
    def setUp(self):
        self.region = "ap-southeast-1"
        self.table_name = "prod-nextcloud-tenant-registry"

        # In-memory DynamoDB
        self.dynamodb = boto3.client("dynamodb", region_name=self.region)
        occ.dynamodb = self.dynamodb
        self.dynamodb.create_table(
            TableName=self.table_name,
            KeySchema=[{"AttributeName": "tenant_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "tenant_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # In-memory SecretsManager
        self.secretsmanager = boto3.client("secretsmanager", region_name=self.region)
        occ.secretsmanager = self.secretsmanager
        self.secretsmanager.create_secret(
            Name="prod-nextcloud-master-key",
            SecretString='{"master_key": "super-secure-production-signing-key-12345"}',
        )

        # In-memory CloudWatch
        self.cloudwatch = boto3.client("cloudwatch", region_name=self.region)
        occ.cloudwatch = self.cloudwatch

    def test_dynamodb_unmarshal_nested_schema(self):
        """Verify unmarshal_ddb_item faithfully converts nested DynamoDB types."""
        ddb_item = {
            "tenant_id": {"S": "acme-corp"},
            "quota_gb": {"N": "250"},
            "is_active": {"BOOL": True},
            "features": {"L": [{"S": "ai_assistant"}, {"S": "s3_primary"}]},
            "metadata": {
                "M": {
                    "tier": {"S": "enterprise"},
                    "max_users": {"N": "500"},
                    "custom_domain": {"NULL": True},
                }
            },
        }

        unmarshaled = unmarshal_ddb_item(ddb_item)
        self.assertEqual(unmarshaled["tenant_id"], "acme-corp")
        self.assertEqual(unmarshaled["quota_gb"], 250)
        self.assertTrue(unmarshaled["is_active"])
        self.assertEqual(unmarshaled["features"], ["ai_assistant", "s3_primary"])
        self.assertEqual(unmarshaled["metadata"]["tier"], "enterprise")
        self.assertEqual(unmarshaled["metadata"]["max_users"], 500)
        self.assertIsNone(unmarshaled["metadata"]["custom_domain"])

    def test_dynamodb_optimistic_concurrency_control(self):
        """Verify atomic insertion and version-based conditional updates (OCC)."""
        tenant_id = "tenant-occ-test"
        
        # 1. Initial atomic insert with condition attribute_not_exists(tenant_id)
        self.dynamodb.put_item(
            TableName=self.table_name,
            Item={
                "tenant_id": {"S": tenant_id},
                "status": {"S": "ACTIVE"},
                "version": {"N": "1"},
            },
            ConditionExpression="attribute_not_exists(tenant_id)",
        )

        # 2. Duplicate insert must raise ConditionalCheckFailedException
        with self.assertRaises(ClientError) as ctx:
            self.dynamodb.put_item(
                TableName=self.table_name,
                Item={
                    "tenant_id": {"S": tenant_id},
                    "status": {"S": "DUPLICATE"},
                    "version": {"N": "1"},
                },
                ConditionExpression="attribute_not_exists(tenant_id)",
            )
        self.assertEqual(ctx.exception.response["Error"]["Code"], "ConditionalCheckFailedException")

        # 3. Successful OCC update: updating from version 1 -> 2
        self.dynamodb.update_item(
            TableName=self.table_name,
            Key={"tenant_id": {"S": tenant_id}},
            UpdateExpression="SET #status = :new_status, #version = :new_ver",
            ConditionExpression="#version = :expected_ver",
            ExpressionAttributeNames={"#status": "status", "#version": "version"},
            ExpressionAttributeValues={
                ":new_status": {"S": "SUSPENDED"},
                ":new_ver": {"N": "2"},
                ":expected_ver": {"N": "1"},
            },
        )

        # 4. Stale OCC update: trying to update with expected version 1 fails
        with self.assertRaises(ClientError) as ctx:
            self.dynamodb.update_item(
                TableName=self.table_name,
                Key={"tenant_id": {"S": tenant_id}},
                UpdateExpression="SET #status = :new_status, #version = :new_ver",
                ConditionExpression="#version = :expected_ver",
                ExpressionAttributeNames={"#status": "status", "#version": "version"},
                ExpressionAttributeValues={
                    ":new_status": {"S": "ACTIVE"},
                    ":new_ver": {"N": "3"},
                    ":expected_ver": {"N": "1"},  # Stale! Current version is 2
                },
            )
        self.assertEqual(ctx.exception.response["Error"]["Code"], "ConditionalCheckFailedException")

    def test_secrets_manager_retrieval(self):
        """Verify SecretsManager retrieval returns valid secret string."""
        resp = self.secretsmanager.get_secret_value(SecretId="prod-nextcloud-master-key")
        self.assertIn("super-secure-production-signing-key-12345", resp["SecretString"])

    def test_cloudwatch_metric_emission_in_memory(self):
        """Verify safe_put_metric_data emits into CloudWatch without raising exceptions."""
        safe_put_metric_data(
            Namespace="Storix/ControlPlane",
            MetricData=[
                {
                    "MetricName": "TenantApiLatency",
                    "Value": 45.2,
                    "Unit": "Milliseconds",
                    "Dimensions": [{"Name": "Action", "Value": "GetTenants"}],
                }
            ],
        )

        # Query metrics from CloudWatch in-memory
        metrics = self.cloudwatch.list_metrics(Namespace="Storix/ControlPlane")
        metric_names = [m["MetricName"] for m in metrics.get("Metrics", [])]
        self.assertIn("TenantApiLatency", metric_names)


if __name__ == "__main__":
    unittest.main()
