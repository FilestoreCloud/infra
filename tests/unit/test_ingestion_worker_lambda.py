"""Unit tests verifying Asynchronous Ingestion Worker Lambda functionality."""

import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
from moto import mock_aws

MODULE_PATH = Path(__file__).resolve().parents[2] / "infra" / "modules" / "05-compute" / "ingestion_worker_lambda.py"
spec = importlib.util.spec_from_file_location("ingestion_worker_lambda", str(MODULE_PATH))
assert spec is not None and spec.loader is not None
ingestion_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingestion_mod)

extract_raw_text = ingestion_mod.extract_raw_text
process_s3_record = ingestion_mod.process_s3_record
lambda_handler = ingestion_mod.lambda_handler


@mock_aws
class TestIngestionWorkerLambda(unittest.TestCase):
    """Test suite for SQS/S3 event ingestion and text extraction."""

    def setUp(self):
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_SECURITY_TOKEN"] = "testing"
        os.environ["AWS_SESSION_TOKEN"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "ap-southeast-1"
        self.region = "ap-southeast-1"
        self.bucket = "prod-nextcloud-vault-123456789-ap-southeast-1"
        self.s3 = boto3.client("s3", region_name=self.region)
        self.s3.create_bucket(
            Bucket=self.bucket,
            CreateBucketConfiguration={"LocationConstraint": self.region},
        )

    def test_extract_raw_text_plain_text(self):
        content = "Dữ liệu văn bản mật của Storix Enterprise mã DOC_9999".encode("utf-8")
        extracted = extract_raw_text(content, "document.txt")
        self.assertIn("DOC_9999", extracted)

    def test_extract_raw_text_markdown(self):
        content = "# Tiêu Đề\nNội dung Markdown bảo mật".encode("utf-8")
        extracted = extract_raw_text(content, "notes.md")
        self.assertIn("Nội dung Markdown", extracted)

    def test_process_s3_record_success(self):
        with patch.object(ingestion_mod, "index_into_opensearch", return_value=True) as mock_index:
            key = "tenants/acme/files/tai_lieu.txt"
            file_body = "Nội dung tệp kế toán doanh nghiệp Acme".encode("utf-8")
            self.s3.put_object(Bucket=self.bucket, Key=key, Body=file_body)

            result = process_s3_record(self.bucket, key)
            self.assertTrue(result)
            mock_index.assert_called_once()
            args, kwargs = mock_index.call_args
            # Verify index_name is tenant_acme
            self.assertEqual(args[1], "tenant_acme")
            # Verify document content
            doc = args[3]
            self.assertEqual(doc["tenant_id"], "acme")
            self.assertIn("Acme", doc["content"])

    def test_lambda_handler_eventbridge_s3_event(self):
        with patch.object(ingestion_mod, "process_s3_record", return_value=True) as mock_process:
            eventbridge_event = {
                "Records": [
                    {
                        "messageId": "msg-123",
                        "body": json.dumps({
                            "source": "aws.s3",
                            "detail-type": "Object Created",
                            "detail": {
                                "bucket": {"name": self.bucket},
                                "object": {"key": "tenants/tenant1/files/report.pdf"},
                            },
                        }),
                    }
                ]
            }

            res = lambda_handler(eventbridge_event, None)
            self.assertEqual(res["statusCode"], 200)
            self.assertEqual(res["processed"], 1)
            self.assertEqual(res["succeeded"], 1)
            mock_process.assert_called_once_with(self.bucket, "tenants/tenant1/files/report.pdf")


if __name__ == "__main__":
    unittest.main()
