"""
Shared AWS clients, environment configurations, and DynamoDB unmarshaling utilities.
"""
import os
from typing import Any
import boto3

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TABLE_NAME = os.environ.get("TABLE_NAME", "prod-nextcloud-tenant-registry")
ADMIN_USERS_TABLE = os.environ.get(
    "ADMIN_USERS_TABLE",
    f"{os.environ.get('ENVIRONMENT_NAME', 'prod')}-nextcloud-admin-users",
)
AUDIT_LOGS_TABLE = os.environ.get(
    "AUDIT_LOGS_TABLE",
    f"{os.environ.get('ENVIRONMENT_NAME', 'prod')}-nextcloud-audit-logs",
)
CLUSTER_NAME = os.environ.get("CLUSTER_NAME", "prod-nextcloud-cluster")
ENVIRONMENT_NAME = os.environ.get("ENVIRONMENT_NAME", "prod")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")

SFN_LOG_GROUP = os.environ.get(
    "SFN_LOG_GROUP",
    f"/aws/vendedlogs/states/{ENVIRONMENT_NAME}-nextcloud-sfn",
)

STATE_MACHINE_PROVISION_ARN = os.environ.get("STATE_MACHINE_PROVISION_ARN", "")
STATE_MACHINE_SUSPEND_ARN = os.environ.get("STATE_MACHINE_SUSPEND_ARN", "")
STATE_MACHINE_RESUME_ARN = os.environ.get("STATE_MACHINE_RESUME_ARN", "")
STATE_MACHINE_DEPROVISION_ARN = os.environ.get("STATE_MACHINE_DEPROVISION_ARN", "")
STATE_MACHINE_SEED_ARN = os.environ.get("STATE_MACHINE_SEED_ARN", "")
STATE_MACHINE_DEMO_ARN = os.environ.get("STATE_MACHINE_DEMO_ARN", "")
STATE_MACHINE_FLEET_UPGRADE_ARN = os.environ.get("STATE_MACHINE_FLEET_UPGRADE_ARN", "")

dynamodb = boto3.client("dynamodb", region_name=REGION)
ecs = boto3.client("ecs", region_name=REGION)
elbv2 = boto3.client("elbv2", region_name=REGION)
cloudwatch = boto3.client("cloudwatch", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)
efs = boto3.client("efs", region_name=REGION)
secretsmanager = boto3.client("secretsmanager", region_name=REGION)
logs = boto3.client("logs", region_name=REGION)
cognito_idp = boto3.client("cognito-idp", region_name=REGION)
ses = boto3.client("ses", region_name=REGION)
sfn = boto3.client("stepfunctions", region_name=REGION)
xray = boto3.client("xray", region_name=REGION)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Admin-Token",
    "Content-Type": "application/json",
}

_CACHED_INFRA: dict[str, Any] = {}


def safe_put_metric_data(Namespace, MetricData):
    """Safely emit CloudWatch metrics without breaking request execution."""
    try:
        cloudwatch.put_metric_data(Namespace=Namespace, MetricData=MetricData)
    except Exception as exc:
        print(f"CloudWatch put_metric_data warning: {exc}")



_CACHED_ACCOUNT_ID = None


def get_aws_account_id() -> str:
    """Retrieve AWS Account ID dynamically via STS or environment, with caching."""
    global _CACHED_ACCOUNT_ID
    if _CACHED_ACCOUNT_ID:
        return _CACHED_ACCOUNT_ID
    account_id = os.environ.get("AWS_ACCOUNT_ID")
    if account_id:
        _CACHED_ACCOUNT_ID = account_id
        return _CACHED_ACCOUNT_ID
    try:
        sts_client = boto3.client("sts", region_name=REGION)
        caller = sts_client.get_caller_identity()
        _CACHED_ACCOUNT_ID = caller.get("Account", "")
        return _CACHED_ACCOUNT_ID
    except Exception:
        return ""


def get_infra_config():
    """Dynamically resolve infrastructure parameters from SSM Parameter Store with caching and fallbacks."""
    global _CACHED_INFRA
    if _CACHED_INFRA:
        return _CACHED_INFRA

    prefix = f"/nextcloud/{ENVIRONMENT_NAME}"
    account_id = get_aws_account_id()
    default_ecr_image = (
        f"{account_id}.dkr.ecr.{REGION}.amazonaws.com/nextcloud-enterprise-ai:latest"
        if account_id
        else "nextcloud-enterprise-ai:latest"
    )

    config = {
        "vpc_id": os.environ.get("VPC_ID"),
        "public_subnets": [
            s.strip()
            for s in os.environ.get("PUBLIC_SUBNETS", "").split(",")
            if s.strip()
        ],
        "private_subnets": [
            s.strip()
            for s in os.environ.get("PRIVATE_SUBNETS", "").split(",")
            if s.strip()
        ],
        "ecs_sg": os.environ.get("ECS_SECURITY_GROUP"),
        "https_listener_arn": os.environ.get("HTTPS_LISTENER_ARN"),
        "alb_arn": os.environ.get("ALB_ARN"),
        "alb_dns": os.environ.get("ALB_DNS"),
        "efs_id": os.environ.get("EFS_ID"),
        "db_endpoint": os.environ.get("DB_ENDPOINT"),
        "db_secret_arn": os.environ.get("DB_SECRET_ARN"),
        "s3_vault_bucket": os.environ.get("S3_VAULT_BUCKET"),
        "cluster_name": os.environ.get("CLUSTER_NAME", CLUSTER_NAME),
        "task_role_arn": os.environ.get("TASK_ROLE_ARN"),
        "exec_role_arn": os.environ.get("EXEC_ROLE_ARN"),
        "ecr_image": os.environ.get("CONTAINER_IMAGE", default_ecr_image),
    }

    try:
        paginator = ssm.get_paginator("get_parameters_by_path")
        for page in paginator.paginate(Path=prefix, Recursive=True):
            for param in page.get("Parameters", []):
                name = param["Name"]
                val = param["Value"]
                if name.endswith("/infra/vpc-id"):
                    config["vpc_id"] = val
                elif name.endswith("/infra/public-subnets"):
                    config["public_subnets"] = [
                        s.strip() for s in val.split(",") if s.strip()
                    ]
                elif name.endswith("/infra/private-subnets"):
                    config["private_subnets"] = [
                        s.strip() for s in val.split(",") if s.strip()
                    ]
                elif name.endswith("/security/ecs-sg-id"):
                    config["ecs_sg"] = val
                elif name.endswith("/infra/alb-https-listener-arn"):
                    config["https_listener_arn"] = val
                elif name.endswith("/infra/alb-arn"):
                    config["alb_arn"] = val
                elif name.endswith("/infra/alb-dns-name"):
                    config["alb_dns"] = val
                elif name.endswith("/infra/efs-id"):
                    config["efs_id"] = val
                elif name.endswith("/infra/db-endpoint"):
                    config["db_endpoint"] = val
                elif name.endswith("/infra/db-secret-arn"):
                    config["db_secret_arn"] = val
                elif name.endswith("/infra/s3-vault-bucket"):
                    config["s3_vault_bucket"] = val
                elif name.endswith("/infra/ecs-cluster-name"):
                    config["cluster_name"] = val
                elif name.endswith("/infra/ecs-task-role-arn"):
                    config["task_role_arn"] = val
                elif name.endswith("/infra/ecs-task-execution-role-arn"):
                    config["exec_role_arn"] = val
                elif name.endswith("/infra/ecr-repo-uri"):
                    config["ecr_image"] = f"{val}:latest"
    except Exception as e:
        print(f"Warning fetching SSM parameters: {e}")

    # Fail-closed safe defaults: no hardcoded AWS account or resource IDs
    if not config.get("public_subnets"):
        config["public_subnets"] = []
    if not config.get("private_subnets"):
        config["private_subnets"] = []

    _CACHED_INFRA = config
    return _CACHED_INFRA


def unmarshal_ddb_val(v):
    """Helper to unmarshal single DynamoDB typed attribute value."""
    if not isinstance(v, dict):
        return v
    if "S" in v:
        return v["S"]
    if "N" in v:
        return int(v["N"]) if v["N"].isdigit() else float(v["N"])
    if "BOOL" in v:
        return v["BOOL"]
    if "M" in v:
        return {k: unmarshal_ddb_val(mv) for k, mv in v["M"].items()}
    if "L" in v:
        return [unmarshal_ddb_val(lv) for lv in v["L"]]
    if "NULL" in v:
        return None
    return list(v.values())[0]


def unmarshal_ddb_item(item):
    """Helper to convert DynamoDB low-level JSON into clean Python dict."""
    result = {}
    for k, v in item.items():
        result[k] = unmarshal_ddb_val(v)
    return result


def get_audit_logs(limit=50):
    """Retrieve recent immutable audit trail records."""
    audit_records = []
    try:
        resp = dynamodb.scan(TableName=AUDIT_LOGS_TABLE, Limit=limit)
        for item in resp.get("Items", []):
            audit_records.append(
                {
                    "event_id": item.get("event_id", {}).get("S", ""),
                    "timestamp": item.get("timestamp", {}).get("S", ""),
                    "actor": item.get("actor", {}).get("S", ""),
                    "role": item.get("role", {}).get("S", ""),
                    "action": item.get("action", {}).get("S", ""),
                    "target": item.get("target", {}).get("S", ""),
                    "status": item.get("status", {}).get("S", "SUCCESS"),
                    "details": item.get("details", {}).get("S", ""),
                    "ip_address": item.get("ip_address", {}).get("S", ""),
                }
            )
        audit_records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    except Exception as e:
        print(f"Warning scanning audit logs from DynamoDB: {e}")
    return audit_records[:limit]

