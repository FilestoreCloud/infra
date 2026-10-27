"""
Storix Asynchronous File Ingestion Worker Lambda.
Decouples document text extraction and OpenSearch indexing from the Nextcloud Web Task.
Consumes messages from Amazon SQS (triggered by S3 ObjectCreated events via EventBridge).
"""

import json
import logging
import os
import re
import urllib.parse
import urllib.request
import zlib
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
ENVIRONMENT_NAME = os.environ.get("ENVIRONMENT_NAME", "prod")
OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT", "")

_S3_CLIENT = None
_SSM_CLIENT = None


def get_s3_client():
    global _S3_CLIENT
    if _S3_CLIENT is None:
        _S3_CLIENT = boto3.client("s3", region_name=REGION)
    return _S3_CLIENT


def get_ssm_client():
    global _SSM_CLIENT
    if _SSM_CLIENT is None:
        _SSM_CLIENT = boto3.client("ssm", region_name=REGION)
    return _SSM_CLIENT


def resolve_opensearch_endpoint() -> str:
    """Resolve OpenSearch VPC endpoint from env or SSM."""
    global OPENSEARCH_ENDPOINT
    if OPENSEARCH_ENDPOINT:
        return OPENSEARCH_ENDPOINT
    try:
        param = get_ssm_client().get_parameter(
            Name=f"/nextcloud/{ENVIRONMENT_NAME}/infra/opensearch-endpoint"
        )
        OPENSEARCH_ENDPOINT = param["Parameter"]["Value"]
        return OPENSEARCH_ENDPOINT
    except Exception as exc:
        logger.warning("Could not resolve OpenSearch endpoint from SSM: %s", exc)
        return ""


def extract_raw_text(file_bytes: bytes, filename: str) -> str:
    """
    Extract readable text from file content based on file extension.
    Supports TXT, MD, JSON, CSV, PDF, and DOCX/XLSX text structures.
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext in [".txt", ".md", ".json", ".csv", ".xml", ".log", ".yaml", ".yml", ".html"]:
        try:
            return file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return file_bytes.decode("latin-1", errors="ignore")

    # PDF Text Extraction (decompress FlateDecode streams)
    if ext == ".pdf":
        extracted = []
        streams = re.findall(b"stream\r?\n(.*?)\r?\nendstream", file_bytes, re.DOTALL)
        for s in streams:
            try:
                decompressed = zlib.decompress(s).decode("latin-1", errors="ignore")
                # Extract text tokens inside parentheses: (Text) Tj or TJ
                text_tokens = re.findall(r"\((.*?)\)", decompressed)
                if text_tokens:
                    extracted.append(" ".join(text_tokens))
                else:
                    extracted.append(decompressed)
            except Exception:
                pass
        if extracted:
            return " ".join(extracted)
        return file_bytes.decode("latin-1", errors="ignore")

    # Fallback generic text decoding
    return file_bytes.decode("utf-8", errors="ignore")


def index_into_opensearch(endpoint: str, index_name: str, doc_id: str, document: Dict[str, Any]) -> bool:
    """Index extracted document into Amazon OpenSearch."""
    if not endpoint:
        logger.info("OpenSearch endpoint not configured, skipping indexing.")
        return True

    # Ensure index_name is lowercase alphanumeric with underscores
    sanitized_index = re.sub(r"[^a-z0-9_-]", "_", index_name.lower())
    url = f"https://{endpoint}/{sanitized_index}/_doc/{urllib.parse.quote(doc_id)}"
    data = json.dumps(document).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.getcode()
            logger.info("Indexed doc %s into %s status: %d", doc_id, sanitized_index, status)
            return status in [200, 201]
    except Exception as exc:
        logger.error("Failed to index into OpenSearch at %s: %s", url, exc)
        return False


def process_s3_record(bucket: str, key: str) -> bool:
    """Download file from S3, extract text, and index into OpenSearch."""
    logger.info("Processing S3 object s3://%s/%s", bucket, key)
    key_decoded = urllib.parse.unquote_plus(key)
    filename = os.path.basename(key_decoded)

    # Derive tenant ID from path prefix (e.g. tenants/{tenant_id}/... or default)
    tenant_id = "default"
    parts = key_decoded.split("/")
    if len(parts) >= 2 and parts[0] == "tenants":
        tenant_id = parts[1]
    elif "admin" in key_decoded:
        tenant_id = "admin"

    try:
        resp = get_s3_client().get_object(Bucket=bucket, Key=key_decoded)
        file_bytes = resp["Body"].read()
        content_length = resp.get("ContentLength", len(file_bytes))
        last_modified = str(resp.get("LastModified", ""))
    except ClientError as exc:
        logger.error("Error downloading s3://%s/%s: %s", bucket, key_decoded, exc)
        return False

    raw_text = extract_raw_text(file_bytes, filename)
    endpoint = resolve_opensearch_endpoint()

    doc = {
        "filename": filename,
        "s3_bucket": bucket,
        "s3_key": key_decoded,
        "tenant_id": tenant_id,
        "content": raw_text[:50000],  # index first 50KB of content
        "size_bytes": content_length,
        "last_modified": last_modified,
    }

    index_name = f"tenant_{tenant_id}"
    return index_into_opensearch(endpoint, index_name, key_decoded, doc)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda entrypoint for SQS batch execution."""
    logger.info("Received event: %s", json.dumps(event))

    records = event.get("Records", [])
    success_count = 0
    failure_count = 0

    for record in records:
        body_raw = record.get("body", "{}")
        try:
            body = json.loads(body_raw)
        except Exception:
            body = {}

        # 1. EventBridge S3 Event structure
        detail = body.get("detail", {})
        if "bucket" in detail and "object" in detail:
            bucket_name = detail["bucket"].get("name")
            object_key = detail["object"].get("key")
            if bucket_name and object_key:
                if process_s3_record(bucket_name, object_key):
                    success_count += 1
                else:
                    failure_count += 1
                continue

        # 2. Standard S3 Notification structure inside SQS body
        if "Records" in body:
            for s3_rec in body["Records"]:
                s3_info = s3_rec.get("s3", {})
                bucket_name = s3_info.get("bucket", {}).get("name")
                object_key = s3_info.get("object", {}).get("key")
                if bucket_name and object_key:
                    if process_s3_record(bucket_name, object_key):
                        success_count += 1
                    else:
                        failure_count += 1
                    continue

    logger.info("Processed batch: %d succeeded, %d failed", success_count, failure_count)
    return {
        "statusCode": 200,
        "processed": len(records),
        "succeeded": success_count,
        "failed": failure_count,
    }
