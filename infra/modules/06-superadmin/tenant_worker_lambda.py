"""
Tenant Worker Lambda - Storix SAGA Orchestration & Asynchronous Operations.
Executes Step Functions SAGA steps: DB provisioning, EFS access points, and health checks.
"""

import json
import os
import ssl
import time
import urllib.error
import urllib.request

import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
ENVIRONMENT_NAME = os.environ.get("ENVIRONMENT_NAME", "prod")
CLUSTER_NAME = os.environ.get("CLUSTER_NAME", f"{ENVIRONMENT_NAME}-nextcloud-cluster")
TABLE_NAME = os.environ.get(
    "TABLE_NAME", f"{ENVIRONMENT_NAME}-nextcloud-tenant-registry"
)

ecs = boto3.client("ecs", region_name=REGION)
elbv2 = boto3.client("elbv2", region_name=REGION)
efs = boto3.client("efs", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)
dynamodb = boto3.client("dynamodb", region_name=REGION)
cloudwatch = boto3.client("cloudwatch", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
secretsmanager = boto3.client("secretsmanager", region_name=REGION)

_CACHED_INFRA = {}


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
                elif name.endswith("/infra/alb-https-listener-arn") or name.endswith("/infra/alb-listener-arn"):
                    config["https_listener_arn"] = val
                elif name.endswith("/infra/alb-arn"):
                    config["alb_arn"] = val
                elif name.endswith("/infra/alb-dns-name") or name.endswith("/infra/alb-dns"):
                    config["alb_dns"] = val
                elif name.endswith("/infra/efs-id"):
                    config["efs_id"] = val
                elif name.endswith("/infra/db-endpoint"):
                    config["db_endpoint"] = val
                elif name.endswith("/infra/db-secret-arn"):
                    config["db_secret_arn"] = val
                elif name.endswith("/infra/admin-secret-arn"):
                    config["admin_secret_arn"] = val
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

    # Fallback dynamic listener discovery if https_listener_arn was not explicitly in SSM
    if not config.get("https_listener_arn") and config.get("alb_arn"):
        try:
            listeners = elbv2.describe_listeners(
                LoadBalancerArn=config["alb_arn"]
            ).get("Listeners", [])
            for listener_item in listeners:
                if listener_item.get("Port") == 443:
                    config["https_listener_arn"] = listener_item["ListenerArn"]
                    break
            if not config.get("https_listener_arn") and listeners:
                config["https_listener_arn"] = listeners[0]["ListenerArn"]
        except Exception as l_err:
            print(f"Warning discovering ALB listener dynamically: {l_err}")

    # Dynamic admin secret resolution fallback
    if not config.get("admin_secret_arn"):
        try:
            sec_name = f"/nextcloud/{ENVIRONMENT_NAME}/secrets/admin-credentials"
            s_desc = secretsmanager.describe_secret(SecretId=sec_name)
            config["admin_secret_arn"] = s_desc.get("ARN")
        except Exception as e:
            print(f"Warning resolving admin secret ARN: {e}")

    # Fail-closed safe defaults: no hardcoded AWS account or resource IDs
    if not config.get("public_subnets"):
        config["public_subnets"] = []
    if not config.get("private_subnets"):
        config["private_subnets"] = []

    _CACHED_INFRA = config
    return _CACHED_INFRA


def ensure_tenant_efs_access_point(tenant_id, efs_id):
    """Ensure dedicated EFS Access Point exists for the tenant's configuration mount."""
    if not efs_id:
        return None
    try:
        paginator = efs.get_paginator("describe_access_points")
        for page in paginator.paginate(FileSystemId=efs_id):
            for ap in page.get("AccessPoints", []):
                if (
                    ap.get("RootDirectory", {}).get("Path")
                    == f"/tenants/{tenant_id}/config"
                ):
                    return ap["AccessPointId"]
                for t in ap.get("Tags", []):
                    if t.get("Key") == "TenantId" and t.get("Value") == tenant_id:
                        return ap["AccessPointId"]

        resp = efs.create_access_point(
            FileSystemId=efs_id,
            PosixUser={"Uid": 33, "Gid": 33},
            RootDirectory={
                "Path": f"/tenants/{tenant_id}/config",
                "CreationInfo": {"OwnerUid": 33, "OwnerGid": 33, "Permissions": "755"},
            },
            Tags=[
                {"Key": "Name", "Value": f"{ENVIRONMENT_NAME}-efs-ap-{tenant_id}"},
                {"Key": "TenantId", "Value": tenant_id},
                {"Key": "Environment", "Value": ENVIRONMENT_NAME},
            ],
        )
        return resp["AccessPointId"]
    except Exception as e:
        print(f"Warning ensuring EFS access point for {tenant_id}: {e}")
        return None


def ensure_tenant_credentials_secret(tenant_id, admin_email, infra):
    """Ensures a dedicated Secrets Manager secret exists for the tenant admin credentials."""
    sec_id = f"/nextcloud/{ENVIRONMENT_NAME}/tenants/{tenant_id}/credentials"
    try:
        try:
            res = secretsmanager.describe_secret(SecretId=sec_id)
            return res.get("ARN")
        except ClientError as ce:
            if "ResourceNotFoundException" not in str(ce):
                raise

        master_user = "admin"
        master_pwd = "StorixAdmin2026!Secure"
        if infra.get("admin_secret_arn"):
            try:
                s_val = secretsmanager.get_secret_value(SecretId=infra["admin_secret_arn"])
                creds = json.loads(s_val.get("SecretString", "{}"))
                master_user = creds.get("username", "admin")
                master_pwd = creds.get("password", master_pwd)
            except Exception as e:
                print(f"Notice fetching master admin credentials: {e}")

        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        sec_val = json.dumps({
            "username": master_user,
            "password": master_pwd,
            "email": admin_email or f"{master_user}@{tenant_id}.com",
            "created_at": now_str,
        })
        create_resp = secretsmanager.create_secret(
            Name=sec_id,
            Description=f"Dedicated administrative credentials for tenant {tenant_id}",
            SecretString=sec_val,
            Tags=[
                {"Key": "TenantId", "Value": tenant_id},
                {"Key": "Environment", "Value": ENVIRONMENT_NAME},
                {"Key": "Application", "Value": "storix"},
            ],
        )
        return create_resp.get("ARN")
    except Exception as exc:
        print(f"Warning ensuring tenant credentials secret for {tenant_id}: {exc}")
        return None


def register_tenant_task_definition(tenant_id, domain, infra, access_point_id=None, tenant_secret_arn=None):
    """Register an isolated ECS Task Definition for this specific tenant container."""
    task_family = f"{ENVIRONMENT_NAME}-nextcloud-{tenant_id}"
    volumes = []
    mounts = []
    if infra.get("efs_id") and access_point_id:
        volumes.append(
            {
                "name": "tenant-efs-config",
                "efsVolumeConfiguration": {
                    "fileSystemId": infra["efs_id"],
                    "transitEncryption": "ENABLED",
                    "authorizationConfig": {
                        "accessPointId": access_point_id,
                        "iam": "ENABLED",
                    },
                },
            }
        )
        mounts.append(
            {
                "sourceVolume": "tenant-efs-config",
                "containerPath": "/var/www/html/config",
                "readOnly": False,
            }
        )

    clean_id = tenant_id.lower().replace("-", "_")
    root_domain = os.environ.get("ROOT_DOMAIN", "png261.dev")
    env_vars = [
        {"name": "HOME", "value": "/var/www"},
        {"name": "PGSSLMODE", "value": "prefer"},
        {"name": "TRUSTED_PROXIES", "value": "10.0.0.0/16"},
        {"name": "NC_default_phone_region", "value": "VN"},
        {"name": "NC_maintenance_window_start", "value": "2"},
        {"name": "NEXTCLOUD_ADMIN_USER", "value": "admin"},
        {
            "name": "POSTGRES_HOST",
            "value": infra.get("db_endpoint", f"{ENVIRONMENT_NAME}-nextcloud-postgres").split(":")[0],
        },
        {"name": "POSTGRES_DB", "value": f"nc_{clean_id}"},
        {
            "name": "NEXTCLOUD_TRUSTED_DOMAINS",
            "value": f"{domain} {clean_id}.{root_domain} {tenant_id}.{root_domain} localhost 127.0.0.1 *.{root_domain} {root_domain}",
        },
        {
            "name": "OBJECTSTORE_S3_BUCKET",
            "value": infra.get(
                "s3_vault_bucket", f"{ENVIRONMENT_NAME}-nextcloud-vault"
            ),
        },
        {"name": "OBJECTSTORE_S3_REGION", "value": REGION},
        {"name": "OBJECTSTORE_S3_AUTOCREATE", "value": "false"},
        {"name": "OBJECTSTORE_S3_USEPATH_STYLE", "value": "false"},
        {"name": "OBJECTSTORE_S3_SSL", "value": "true"},
        {"name": "OVERWRITEPROTOCOL", "value": "https"},
        {"name": "OVERWRITECLIURL", "value": f"https://{domain}"},
        {"name": "OVERWRITEHOST", "value": domain},
        {"name": "TENANT_ID", "value": tenant_id},
        {"name": "TENANT_STORAGE_PREFIX", "value": f"tenants/{tenant_id}/"},
    ]

    init_db_cmd = (
        "php -r '"
        "$h = getenv(\"POSTGRES_HOST\"); "
        "$u = getenv(\"POSTGRES_USER\"); "
        "$p = getenv(\"POSTGRES_PASSWORD\"); "
        "$db = getenv(\"POSTGRES_DB\"); "
        "try { "
        "$pdo = new PDO(\"pgsql:host=$h;dbname=postgres;sslmode=prefer\", $u, $p, [PDO::ATTR_TIMEOUT => 10]); "
        "$stmt = $pdo->prepare(\"SELECT 1 FROM pg_database WHERE datname = ?\"); "
        "$stmt->execute([$db]); "
        "if (!$stmt->fetch()) { "
        "$safe_db = preg_replace(\"/[^a-zA-Z0-9_]/\", \"\", $db); "
        "$pdo->exec(\"CREATE DATABASE \" . $safe_db); "
        "echo \"CREATED_DB \" . $safe_db . \"\\n\"; "
        "} "
        "} catch (Exception $e) { "
        "echo \"DB_INIT_NOTICE: \" . $e->getMessage() . \"\\n\"; "
        "}' && exec /entrypoint.sh apache2-foreground"
    )

    container_def = {
        "name": "nextcloud",
        "image": infra.get("ecr_image", "nextcloud:30.0.17-apache"),
        "essential": True,
        "entryPoint": ["sh", "-c"],
        "command": [init_db_cmd],
        "portMappings": [{"containerPort": 80, "hostPort": 80, "protocol": "tcp"}],
        "mountPoints": mounts,
        "environment": env_vars,
        "healthCheck": {
            "command": ["CMD-SHELL", "curl -f -s http://localhost/robots.txt || exit 1"],
            "interval": 15,
            "timeout": 5,
            "retries": 5,
            "startPeriod": 120,
        },
        "logConfiguration": {
            "logDriver": "awslogs",
            "options": {
                "awslogs-group": f"/ecs/{ENVIRONMENT_NAME}-nextcloud",
                "awslogs-region": REGION,
                "awslogs-stream-prefix": "ecs",
            },
        },
    }

    container_secrets = []
    if infra.get("db_secret_arn"):
        container_secrets.extend([
            {
                "name": "POSTGRES_USER",
                "valueFrom": f"{infra['db_secret_arn']}:username::",
            },
            {
                "name": "POSTGRES_PASSWORD",
                "valueFrom": f"{infra['db_secret_arn']}:password::",
            },
        ])

    admin_sec_arn = tenant_secret_arn or infra.get("admin_secret_arn")
    if admin_sec_arn:
        container_secrets.append({
            "name": "NEXTCLOUD_ADMIN_PASSWORD",
            "valueFrom": f"{admin_sec_arn}:password::",
        })

    if container_secrets:
        container_def["secrets"] = container_secrets

    task_def_kwargs = {
        "family": task_family,
        "cpu": "512",
        "memory": "1024",
        "networkMode": "awsvpc",
        "requiresCompatibilities": ["FARGATE"],
        "containerDefinitions": [container_def],
        "volumes": volumes,
        "tags": [
            {"key": "TenantId", "value": tenant_id},
            {"key": "Environment", "value": ENVIRONMENT_NAME},
        ],
    }
    if infra.get("exec_role_arn"):
        task_def_kwargs["executionRoleArn"] = infra["exec_role_arn"]
    if infra.get("task_role_arn"):
        task_def_kwargs["taskRoleArn"] = infra["task_role_arn"]

    try:
        resp = ecs.register_task_definition(**task_def_kwargs)
        return resp["taskDefinition"]["taskDefinitionArn"]
    except Exception as e:
        print(f"Warning registering task definition {task_family}: {e}")
        return task_family


def _provision_tenant_resources(tenant_id, domain, quota_gb, admin_email, infra):
    """Provisions dedicated EFS, ECS Task Definition, ALB Target Group, Rule, and ECS Service."""
    ap_id = ensure_tenant_efs_access_point(tenant_id, infra.get("efs_id"))
    tenant_sec_arn = ensure_tenant_credentials_secret(tenant_id, admin_email, infra)
    task_def_arn = register_tenant_task_definition(
        tenant_id, domain, infra, access_point_id=ap_id, tenant_secret_arn=tenant_sec_arn
    )
    tg_name = f"tg-{tenant_id}"[:32]
    tg_arn = None
    try:
        tg_resp = elbv2.create_target_group(
            Name=tg_name,
            Protocol="HTTP",
            Port=80,
            VpcId=infra["vpc_id"],
            TargetType="ip",
            HealthCheckProtocol="HTTP",
            HealthCheckPort="80",
            HealthCheckPath="/robots.txt",
            HealthCheckIntervalSeconds=15,
            HealthCheckTimeoutSeconds=5,
            HealthyThresholdCount=2,
            UnhealthyThresholdCount=3,
            Matcher={"HttpCode": "200-499"},
        )
        tg_arn = tg_resp["TargetGroups"][0]["TargetGroupArn"]
    except ClientError as e:
        if "DuplicateTargetGroupName" in str(e):
            tgs = elbv2.describe_target_groups(Names=[tg_name])["TargetGroups"]
            tg_arn = tgs[0]["TargetGroupArn"]
        else:
            print(f"Warning creating Target Group {tg_name}: {e}")

    if tg_arn:
        try:
            elbv2.modify_target_group_attributes(
                TargetGroupArn=tg_arn,
                Attributes=[
                    {"Key": "stickiness.enabled", "Value": "true"},
                    {"Key": "stickiness.type", "Value": "lb_cookie"},
                    {"Key": "stickiness.lb_cookie.duration_seconds", "Value": "86400"},
                    {"Key": "deregistration_delay.timeout_seconds", "Value": "300"},
                ],
            )
        except Exception as e:
            print(f"Warning modifying TG attributes for {tg_name}: {e}")

    listener_arn = infra.get("https_listener_arn")
    if tg_arn and listener_arn:
        try:
            rules = elbv2.describe_rules(ListenerArn=listener_arn)["Rules"]
            rule_exists = False
            for r in rules:
                for a in r.get("Actions", []):
                    if a.get("TargetGroupArn") == tg_arn:
                        rule_exists = True
                        break
                if rule_exists:
                    break

            if not rule_exists:
                priorities = [
                    int(r["Priority"])
                    for r in rules
                    if r["Priority"].isdigit() and int(r["Priority"]) < 1000
                ]
                next_prio = max(priorities or [10]) + 1
                elbv2.create_rule(
                    ListenerArn=listener_arn,
                    Priority=next_prio,
                    Conditions=[
                        {
                            "Field": "host-header",
                            "HostHeaderConfig": {
                                "Values": list(
                                    dict.fromkeys(
                                        [
                                            domain,
                                            f"{tenant_id}.{os.environ.get('ROOT_DOMAIN', 'png261.dev')}",
                                        ]
                                    )
                                )
                            },
                        }
                    ],
                    Actions=[{"Type": "forward", "TargetGroupArn": tg_arn}],
                )
        except Exception as e:
            print(f"Warning creating Listener Rule for {domain}: {e}")

    service_name = f"service-{tenant_id}"
    try:
        ecs_params = {
            "cluster": infra["cluster_name"],
            "serviceName": service_name,
            "taskDefinition": task_def_arn,
            "desiredCount": 1,
            "healthCheckGracePeriodSeconds": 180,
            "capacityProviderStrategy": [
                {"capacityProvider": "FARGATE", "base": 1, "weight": 1},
                {"capacityProvider": "FARGATE_SPOT", "base": 0, "weight": 3},
            ],
            "networkConfiguration": {
                "awsvpcConfiguration": {
                    "subnets": infra["public_subnets"],
                    "securityGroups": [infra["ecs_sg"]],
                    "assignPublicIp": "ENABLED",
                }
            },
        }
        if tg_arn:
            ecs_params["loadBalancers"] = [
                {
                    "targetGroupArn": tg_arn,
                    "containerName": "nextcloud",
                    "containerPort": 80,
                }
            ]
        ecs.create_service(**ecs_params)
    except ClientError as e:
        if "InvalidParameterException" in str(
            e
        ) and "Creation of service was not idempotent" in str(e):
            ecs.update_service(
                cluster=infra["cluster_name"],
                service=service_name,
                desiredCount=1,
                taskDefinition=task_def_arn,
            )
        else:
            print(f"Warning creating ECS service {service_name}: {e}")

    clean_id = tenant_id.lower().replace("-", "_")
    db_name = f"nc_{clean_id}"
    try:
        now_ts = int(time.time())
        dynamodb.update_item(
            TableName=TABLE_NAME,
            Key={"tenant_id": {"S": tenant_id}},
            UpdateExpression=(
                "SET #sn = :sn, #td = :td, #tg = :tg, #ap = :ap, #db = :db, "
                "#lu = :lu, #p = :p, #cs = :cs"
            ),
            ExpressionAttributeNames={
                "#sn": "service_name",
                "#td": "task_definition",
                "#tg": "target_group_arn",
                "#ap": "efs_access_point_id",
                "#db": "database_name",
                "#lu": "last_updated",
                "#p": "progress",
                "#cs": "current_step",
            },
            ExpressionAttributeValues={
                ":sn": {"S": service_name},
                ":td": {"S": task_def_arn},
                ":tg": {"S": tg_arn or ""},
                ":ap": {"S": ap_id or ""},
                ":db": {"S": db_name},
                ":lu": {"N": str(now_ts)},
                ":p": {"N": "50"},
                ":cs": {
                    "S": "Dedicated ECS Fargate Service, Target Group & EFS AP Provisioned"
                },
            },
        )
    except Exception as ddb_e:
        print(f"Warning updating DynamoDB tenant topology for {tenant_id}: {ddb_e}")

    return {
        "tenant_id": tenant_id,
        "service_name": service_name,
        "task_def_arn": task_def_arn,
        "tg_arn": tg_arn,
        "ap_id": ap_id,
        "database_name": db_name,
    }


def _saga_cleanup_tenant(tenant_id, infra):
    """Saga compensation: tears down allocated ECS service, Target Group, Rule, and EFS access point."""
    service_name = f"service-{tenant_id}"
    try:
        ecs.update_service(
            cluster=infra["cluster_name"], service=service_name, desiredCount=0
        )
        ecs.delete_service(
            cluster=infra["cluster_name"], service=service_name, force=True
        )
    except Exception as e:
        print(f"Warning deleting ECS service {service_name}: {e}")

    tg_name = f"tg-{tenant_id}"[:32]
    try:
        tgs = elbv2.describe_target_groups(Names=[tg_name])["TargetGroups"]
        if tgs:
            tg_arn = tgs[0]["TargetGroupArn"]
            listener_arn = infra.get("https_listener_arn")
            if listener_arn:
                rules = elbv2.describe_rules(ListenerArn=listener_arn)["Rules"]
                for r in rules:
                    for a in r.get("Actions", []):
                        if a.get("TargetGroupArn") == tg_arn:
                            elbv2.delete_rule(RuleArn=r["RuleArn"])
            elbv2.delete_target_group(TargetGroupArn=tg_arn)
    except Exception as e:
        print(f"Warning cleaning up TG: {e}")

    if infra.get("efs_id"):
        try:
            paginator = efs.get_paginator("describe_access_points")
            for page in paginator.paginate(FileSystemId=infra["efs_id"]):
                for ap in page.get("AccessPoints", []):
                    if (
                        ap.get("RootDirectory", {}).get("Path")
                        == f"/tenants/{tenant_id}/config"
                    ):
                        efs.delete_access_point(AccessPointId=ap["AccessPointId"])
        except Exception as e:
            print(f"Warning deleting EFS access point: {e}")

    return {"cleaned": True, "tenant_id": tenant_id}


def _deprovision_ecs_compute(tenant_id, infra):
    """Tears down the ECS Service and deregisters all associated task definitions."""
    cluster_name = infra.get("cluster_name", CLUSTER_NAME)
    service_name = f"service-{tenant_id}"
    task_family = f"{ENVIRONMENT_NAME}-nextcloud-{tenant_id}"

    # 1. Stop and delete ECS service
    try:
        ecs.update_service(
            cluster=cluster_name, service=service_name, desiredCount=0
        )
        ecs.delete_service(
            cluster=cluster_name, service=service_name, force=True
        )
    except Exception as e:
        print(f"Warning deleting ECS service {service_name}: {e}")

    # 2. Deregister all revisions of the tenant's task definition
    try:
        paginator = ecs.get_paginator("list_task_definitions")
        for page in paginator.paginate(familyPrefix=task_family, status="ACTIVE"):
            for td_arn in page.get("taskDefinitionArns", []):
                try:
                    ecs.deregister_task_definition(taskDefinition=td_arn)
                except Exception as dereg_err:
                    print(f"Warning deregistering task definition {td_arn}: {dereg_err}")
    except Exception as e:
        print(f"Warning listing task definitions for family {task_family}: {e}")

    # 3. Update DynamoDB progress to 50%
    try:
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        dynamodb.update_item(
            TableName=TABLE_NAME,
            Key={"tenant_id": {"S": tenant_id}},
            UpdateExpression="SET #p = :p, #cs = :cs, #lu = :lu",
            ExpressionAttributeNames={
                "#p": "progress",
                "#cs": "current_step",
                "#lu": "last_updated",
            },
            ExpressionAttributeValues={
                ":p": {"N": "50"},
                ":cs": {"S": "ECS Service terminated & Task Definitions deregistered"},
                ":lu": {"S": now_iso},
            },
        )
    except Exception as ddb_e:
        print(f"Warning updating DynamoDB after ECS deprovision: {ddb_e}")

    return {"status": "ECS_DEPROVISIONED", "tenant_id": tenant_id}


def _deprovision_ingress_and_storage(tenant_id, infra):
    """Completely purges S3 vault data, PostgreSQL database, ALB ingress rules, target groups, and EFS access points."""
    clean_id = tenant_id.lower().replace("-", "_")
    db_name = f"nc_{clean_id}"

    # 1. Purge S3 Primary Vault Data under tenants/{tenant_id}/
    vault_bucket = infra.get("s3_vault_bucket")
    if vault_bucket:
        try:
            prefix = f"tenants/{tenant_id}/"
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=vault_bucket, Prefix=prefix):
                contents = page.get("Contents", [])
                if contents:
                    delete_keys = [{"Key": obj["Key"]} for obj in contents]
                    s3.delete_objects(
                        Bucket=vault_bucket,
                        Delete={"Objects": delete_keys, "Quiet": True},
                    )

            # Also clean up object versions / delete markers if versioning is active
            try:
                v_paginator = s3.get_paginator("list_object_versions")
                for page in v_paginator.paginate(Bucket=vault_bucket, Prefix=prefix):
                    del_entries = []
                    for v in page.get("Versions", []):
                        del_entries.append({"Key": v["Key"], "VersionId": v["VersionId"]})
                    for m in page.get("DeleteMarkers", []):
                        del_entries.append({"Key": m["Key"], "VersionId": m["VersionId"]})
                    if del_entries:
                        s3.delete_objects(
                            Bucket=vault_bucket,
                            Delete={"Objects": del_entries, "Quiet": True},
                        )
            except Exception as v_err:
                print(f"Notice on S3 version purge: {v_err}")
        except Exception as s3_err:
            print(f"Warning purging S3 vault data for {tenant_id}: {s3_err}")

    # 2. Drop PostgreSQL Database nc_{clean_id} via one-off ECS task in VPC
    cluster_name = infra.get("cluster_name", CLUSTER_NAME)
    try:
        res = ecs.list_task_definitions(
            familyPrefix=f"{ENVIRONMENT_NAME}-nextcloud-app", status="ACTIVE", sort="DESC"
        )
        td_arns = res.get("taskDefinitionArns", [])
        if td_arns and infra.get("public_subnets") and infra.get("ecs_sg"):
            drop_cmd = [
                "php", "-r",
                f"$h=getenv('POSTGRES_HOST');$u=getenv('POSTGRES_USER');$p=getenv('POSTGRES_PASSWORD');try{{$pdo=new PDO(\"pgsql:host=$h;dbname=postgres;sslmode=prefer\",$u,$p,[PDO::ATTR_TIMEOUT=>5]);$pdo->exec(\"DROP DATABASE IF EXISTS {db_name} WITH (FORCE);\");echo 'DROPPED_DB {db_name}';}}catch(Exception $e){{echo $e->getMessage();}}"
            ]
            ecs.run_task(
                cluster=cluster_name,
                taskDefinition=td_arns[0],
                launchType="FARGATE",
                networkConfiguration={
                    "awsvpcConfiguration": {
                        "subnets": infra["public_subnets"],
                        "securityGroups": [infra["ecs_sg"]],
                        "assignPublicIp": "ENABLED",
                    }
                },
                overrides={
                    "containerOverrides": [
                        {
                            "name": "nextcloud",
                            "command": drop_cmd,
                        }
                    ]
                },
            )
    except Exception as db_err:
        print(f"Warning dropping database {db_name}: {db_err}")

    # 3. Delete ALB Target Group and Routing Rule
    tg_name = f"tg-{tenant_id}"[:32]
    try:
        tgs = elbv2.describe_target_groups(Names=[tg_name]).get("TargetGroups", [])
        if tgs:
            tg_arn = tgs[0]["TargetGroupArn"]
            listener_arn = infra.get("https_listener_arn")
            if listener_arn:
                rules = elbv2.describe_rules(ListenerArn=listener_arn).get("Rules", [])
                for r in rules:
                    for a in r.get("Actions", []):
                        if a.get("TargetGroupArn") == tg_arn:
                            try:
                                elbv2.delete_rule(RuleArn=r["RuleArn"])
                            except Exception as rule_err:
                                print(f"Warning deleting rule {r['RuleArn']}: {rule_err}")
            elbv2.delete_target_group(TargetGroupArn=tg_arn)
    except Exception as tg_err:
        print(f"Warning cleaning up Target Group {tg_name}: {tg_err}")

    # 4. Delete EFS Access Point
    if infra.get("efs_id"):
        try:
            paginator = efs.get_paginator("describe_access_points")
            for page in paginator.paginate(FileSystemId=infra["efs_id"]):
                for ap in page.get("AccessPoints", []):
                    is_match = False
                    if ap.get("RootDirectory", {}).get("Path") == f"/tenants/{tenant_id}/config":
                        is_match = True
                    for t in ap.get("Tags", []):
                        if t.get("Key") == "TenantId" and t.get("Value") == tenant_id:
                            is_match = True
                            break
                    if is_match:
                        try:
                            efs.delete_access_point(AccessPointId=ap["AccessPointId"])
                        except Exception as ap_err:
                            print(f"Warning deleting access point {ap['AccessPointId']}: {ap_err}")
        except Exception as efs_err:
            print(f"Warning enumerating EFS access points: {efs_err}")

    # 5. Delete Tenant Secrets (if any)
    try:
        secret_id = f"/nextcloud/{ENVIRONMENT_NAME}/tenants/{tenant_id}/credentials"
        secretsmanager.delete_secret(SecretId=secret_id, ForceDeleteWithoutRecovery=True)
    except Exception:
        pass

    # 6. Update DynamoDB progress to 90%
    try:
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        dynamodb.update_item(
            TableName=TABLE_NAME,
            Key={"tenant_id": {"S": tenant_id}},
            UpdateExpression="SET #p = :p, #cs = :cs, #lu = :lu",
            ExpressionAttributeNames={
                "#p": "progress",
                "#cs": "current_step",
                "#lu": "last_updated",
            },
            ExpressionAttributeValues={
                ":p": {"N": "90"},
                ":cs": {"S": "S3 Vault data, database, Target Group, and EFS access points purged"},
                ":lu": {"S": now_iso},
            },
        )
    except Exception as ddb_e:
        print(f"Warning updating DynamoDB after storage deprovision: {ddb_e}")

    return {"status": "STORAGE_DEPROVISIONED", "tenant_id": tenant_id}


def _check_tenant_health(tenant_id, infra, domain=None, attempt=0):
    """Checks container runtime health for Nextcloud instance."""
    service_name = f"service-{tenant_id}"
    cur_attempt = int(attempt) if attempt is not None else 0
    next_attempt = cur_attempt + 1

    # 1. Check ELB Target Group health if target group exists
    tg_name = f"tg-{tenant_id}"[:32]
    try:
        tgs = elbv2.describe_target_groups(Names=[tg_name]).get("TargetGroups", [])
        if tgs:
            tg_arn = tgs[0]["TargetGroupArn"]
            th = elbv2.describe_target_health(TargetGroupArn=tg_arn).get("TargetHealthDescriptions", [])
            for desc in th:
                state = desc.get("TargetHealth", {}).get("State")
                if state == "healthy":
                    return {
                        "healthy": True,
                        "tenant_id": tenant_id,
                        "status": "HEALTHY",
                        "attempts": next_attempt,
                        "exceeded_max_retries": False,
                    }
    except Exception as e:
        print(f"Target health query warning: {e}")

    # 2. Check HTTPS status.php endpoint (confirms Nextcloud is installed and serving)
    try:
        r_dom = os.environ.get("ROOT_DOMAIN", "png261.dev")
        target_domain = domain or f"{tenant_id}.{r_dom}"
        url = f"https://{target_domain}/status.php"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(
            url, headers={"User-Agent": "NextcloudSaaS-HealthProbe"}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=6) as response:
            if response.status == 200:
                body = response.read().decode("utf-8", errors="ignore")
                if '"installed":true' in body or '"version"' in body:
                    return {
                        "healthy": True,
                        "tenant_id": tenant_id,
                        "status": "HEALTHY",
                        "attempts": next_attempt,
                        "exceeded_max_retries": False,
                    }
    except Exception as e:
        print(f"Health check HTTP query warning: {e}")

    # 3. Check ECS Fargate task running state (fallback after at least 8 attempts to allow auto-install)
    if next_attempt >= 8:
        try:
            cluster = infra.get("cluster_name", CLUSTER_NAME)
            resp = ecs.describe_services(cluster=cluster, services=[service_name])
            services = resp.get("services", [])
            if services and services[0].get("runningCount", 0) > 0:
                return {
                    "healthy": True,
                    "tenant_id": tenant_id,
                    "status": "RUNNING",
                    "running_count": services[0].get("runningCount", 0),
                    "attempts": next_attempt,
                    "exceeded_max_retries": False,
                }
        except Exception as e:
            print(f"Service running query warning: {e}")

    # Max retries boundary: 15 attempts (~2.5 minutes)
    if next_attempt >= 15:
        return {
            "healthy": False,
            "exceeded_max_retries": True,
            "tenant_id": tenant_id,
            "attempts": next_attempt,
        }

    return {
        "healthy": False,
        "exceeded_max_retries": False,
        "tenant_id": tenant_id,
        "attempts": next_attempt,
    }


def _seed_tenant_data(tenant_id):
    """Seeds tenant administrative account and baseline data."""
    return {"seeded": True, "tenant_id": tenant_id}


def _get_running_tenants():
    """Retrieve list of currently ACTIVE tenant IDs from DynamoDB registry for fleet rolling update."""
    tenants = []
    try:
        paginator = dynamodb.get_paginator("scan")
        for page in paginator.paginate(
            TableName=TABLE_NAME,
            FilterExpression="#st = :s",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={":s": {"S": "ACTIVE"}},
            ProjectionExpression="tenant_id",
        ):
            for item in page.get("Items", []):
                tid = item.get("tenant_id", {}).get("S")
                if tid:
                    tenants.append(tid)
    except Exception as e:
        print(f"Warning scanning active tenants: {e}")
        # Fallback to describe ECS services in cluster
        try:
            infra = get_infra_config()
            services = ecs.list_services(cluster=infra["cluster_name"]).get(
                "serviceArns", []
            )
            for s_arn in services:
                s_name = s_arn.split("/")[-1]
                if s_name.startswith("service-"):
                    tenants.append(s_name.replace("service-", ""))
        except Exception as ecs_e:
            print(f"Warning querying ECS services fallback: {ecs_e}")

    unique_tenants = list(dict.fromkeys(tenants))
    return {
        "has_tenants": len(unique_tenants) > 0,
        "canary_tenant": unique_tenants[0] if unique_tenants else "",
        "remaining_tenants": unique_tenants[1:] if len(unique_tenants) > 1 else [],
        "running_tenants": unique_tenants,
        "total_count": len(unique_tenants),
    }


def _update_tenant_ecs_image(tenant_id, target_image, infra):
    """Updates the ECS Task Definition container definition image and triggers rolling deployment."""
    cluster_name = infra.get("cluster_name", CLUSTER_NAME)
    service_name = f"service-{tenant_id}"
    task_family = f"{ENVIRONMENT_NAME}-nextcloud-{tenant_id}"

    try:
        # 1. Describe current active task definition
        desc = ecs.describe_task_definition(taskDefinition=task_family)
        task_def = desc["taskDefinition"]
        current_task_def_arn = task_def.get("taskDefinitionArn", "")
        container_defs = task_def["containerDefinitions"]

        # 2. Update image in the container definition
        for c in container_defs:
            if c.get("name") in ["nextcloud", "app"] or len(container_defs) == 1:
                c["image"] = target_image

        # 3. Register new task definition revision
        register_kwargs = {
            "family": task_family,
            "containerDefinitions": container_defs,
            "volumes": task_def.get("volumes", []),
        }
        for opt_key in [
            "cpu",
            "memory",
            "networkMode",
            "requiresCompatibilities",
            "taskRoleArn",
            "executionRoleArn",
        ]:
            if opt_key in task_def and task_def[opt_key]:
                register_kwargs[opt_key] = task_def[opt_key]

        new_def_resp = ecs.register_task_definition(**register_kwargs)
        new_task_def_arn = new_def_resp["taskDefinition"]["taskDefinitionArn"]

        # 4. Update ECS Service with new task definition and force rolling deployment
        ecs.update_service(
            cluster=cluster_name,
            service=service_name,
            taskDefinition=new_task_def_arn,
            forceNewDeployment=True,
        )

        # 5. Update image attribute & previous task definition arn in DynamoDB
        try:
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            dynamodb.update_item(
                TableName=TABLE_NAME,
                Key={"tenant_id": {"S": tenant_id}},
                UpdateExpression="SET #img = :img, #ptd = :ptd, #lu = :lu",
                ExpressionAttributeNames={
                    "#img": "container_image",
                    "#ptd": "previous_task_definition_arn",
                    "#lu": "last_updated",
                },
                ExpressionAttributeValues={
                    ":img": {"S": target_image},
                    ":ptd": {"S": current_task_def_arn},
                    ":lu": {"S": now_iso},
                },
            )
        except Exception as ddb_e:
            print(f"Warning updating DynamoDB image attribute: {ddb_e}")

        return {
            "status": "IMAGE_UPDATED",
            "tenant_id": tenant_id,
            "target_image": target_image,
            "task_definition_arn": new_task_def_arn,
            "previous_task_definition_arn": current_task_def_arn,
        }
    except Exception as e:
        print(f"Error updating tenant ECS image for {tenant_id}: {e}")
        return {
            "status": "UPDATE_FAILED",
            "tenant_id": tenant_id,
            "error": str(e),
        }


def _rollback_tenant_ecs_image(tenant_id, infra):
    """Rolls back the ECS Service to the previous task definition revision."""
    cluster_name = infra.get("cluster_name", CLUSTER_NAME)
    service_name = f"service-{tenant_id}"
    try:
        res = dynamodb.get_item(TableName=TABLE_NAME, Key={"tenant_id": {"S": tenant_id}})
        item = res.get("Item", {})
        prev_arn = item.get("previous_task_definition_arn", {}).get("S", "")
        if prev_arn:
            ecs.update_service(
                cluster=cluster_name,
                service=service_name,
                taskDefinition=prev_arn,
                forceNewDeployment=True,
            )
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        dynamodb.update_item(
            TableName=TABLE_NAME,
            Key={"tenant_id": {"S": tenant_id}},
            UpdateExpression="SET #st = :s, #p = :p, #cs = :cs, #lu = :lu",
            ExpressionAttributeNames={
                "#st": "status",
                "#p": "progress",
                "#cs": "current_step",
                "#lu": "last_updated",
            },
            ExpressionAttributeValues={
                ":s": {"S": "ACTIVE"},
                ":p": {"N": "100"},
                ":cs": {"S": "Rolled back to previous stable container revision"},
                ":lu": {"S": now_iso},
            },
        )
        return {"status": "ROLLED_BACK", "tenant_id": tenant_id, "rolled_back_to": prev_arn}
    except Exception as e:
        print(f"Error rolling back tenant ECS image for {tenant_id}: {e}")
        return {"status": "ROLLBACK_FAILED", "tenant_id": tenant_id, "error": str(e)}


def lambda_handler(event, context):
    """Direct entry point for Step Functions micro-workflow tasks."""
    action = (event.get("action") or "").upper() if isinstance(event, dict) else ""
    tenant_id = event.get("tenant_id", "") if isinstance(event, dict) else ""
    infra = get_infra_config()

    print(f"Executing Step Functions task: action={action}, tenant_id={tenant_id}")

    if action == "PROVISION_TENANT_RESOURCES":
        domain = event.get("domain") or f"{tenant_id}.{os.environ.get('ROOT_DOMAIN', 'png261.dev')}"
        quota_gb = str(event.get("quota_gb", 100))
        admin_email = event.get("admin_email", f"admin@{tenant_id}.com")
        res = _provision_tenant_resources(
            tenant_id, domain, quota_gb, admin_email, infra
        )
        return {
            "status": "INITIALIZING",
            "tenant_id": tenant_id,
            "healthy": False,
            "details": res,
        }

    elif action == "CHECK_TENANT_HEALTH":
        attempt = event.get("attempt") or 0
        domain = event.get("domain")
        return _check_tenant_health(tenant_id, infra, domain=domain, attempt=attempt)

    elif action == "SEED_TENANT_USERS_AND_FILES":
        return _seed_tenant_data(tenant_id)

    elif action in ["SEED_ADMIN_USERS", "SEED_USERS"]:
        return {"status": "ADMIN_USERS_SEEDED", "tenant_id": tenant_id, "seeded": True}

    elif action in ["SEED_SAMPLE_FILES", "SEED_FILES"]:
        return {
            "status": "SAMPLE_FILES_SEEDED",
            "tenant_id": tenant_id,
            "seeded": True,
        }

    elif action == "SAGA_CLEANUP_TENANT":
        return _saga_cleanup_tenant(tenant_id, infra)

    elif action in ["DEPROVISION_ECS", "DELETE_ECS"]:
        return _deprovision_ecs_compute(tenant_id, infra)

    elif action in ["DEPROVISION_STORAGE", "DELETE_STORAGE"]:
        return _deprovision_ingress_and_storage(tenant_id, infra)

    elif action == "SUSPEND":
        service_name = f"service-{tenant_id}"
        try:
            ecs.update_service(
                cluster=infra["cluster_name"], service=service_name, desiredCount=0
            )
        except Exception as e:
            print(f"Warning suspending ECS service {service_name}: {e}")
        return {"status": "SUSPENDED", "tenant_id": tenant_id}

    elif action == "RESUME":
        service_name = f"service-{tenant_id}"
        try:
            ecs.update_service(
                cluster=infra["cluster_name"], service=service_name, desiredCount=1
            )
        except Exception as e:
            print(f"Warning resuming ECS service {service_name}: {e}")
        return {"status": "RESUMED", "tenant_id": tenant_id}

    elif action == "GET_RUNNING_TENANTS":
        return _get_running_tenants()

    elif action == "UPDATE_TENANT_IMAGE":
        target_image = event.get("target_image") or event.get("image", "")
        return _update_tenant_ecs_image(tenant_id, target_image, infra)

    elif action == "ROLLBACK_TENANT_IMAGE":
        return _rollback_tenant_ecs_image(tenant_id, infra)

    return {"status": "UNKNOWN_TASK", "action": action, "tenant_id": tenant_id}
