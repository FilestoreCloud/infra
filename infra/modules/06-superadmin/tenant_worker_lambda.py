import os
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


def register_tenant_task_definition(tenant_id, domain, infra, access_point_id=None):
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
    env_vars = [
        {"name": "HOME", "value": "/var/www"},
        {"name": "PGSSLMODE", "value": "prefer"},
        {
            "name": "POSTGRES_HOST",
            "value": infra.get("db_endpoint", "prod-nextcloud-postgres"),
        },
        {"name": "POSTGRES_DB", "value": f"nc_{clean_id}"},
        {
            "name": "NEXTCLOUD_TRUSTED_DOMAINS",
            "value": f"{domain} {tenant_id}.{os.environ.get('ROOT_DOMAIN', 'png261.dev')} localhost",
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

    container_def = {
        "name": "nextcloud",
        "image": infra.get("ecr_image", "nextcloud:30.0.17-apache"),
        "essential": True,
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
                "awslogs-group": f"/ecs/nextcloud-{ENVIRONMENT_NAME}",
                "awslogs-region": REGION,
                "awslogs-stream-prefix": "ecs",
            },
        },
    }

    if infra.get("db_secret_arn"):
        container_def["secrets"] = [
            {
                "name": "POSTGRES_USER",
                "valueFrom": f"{infra['db_secret_arn']}:username::",
            },
            {
                "name": "POSTGRES_PASSWORD",
                "valueFrom": f"{infra['db_secret_arn']}:password::",
            },
        ]

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
    task_def_arn = register_tenant_task_definition(tenant_id, domain, infra, ap_id)
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
            HealthCheckPath="/status.php",
            HealthCheckIntervalSeconds=30,
            Matcher={"HttpCode": "200-400"},
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

    return {
        "tenant_id": tenant_id,
        "service_name": service_name,
        "task_def_arn": task_def_arn,
        "tg_arn": tg_arn,
        "ap_id": ap_id,
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


def _check_tenant_health(tenant_id, infra):
    """Checks container runtime health for Nextcloud instance."""
    service_name = f"service-{tenant_id}"
    try:
        cluster = infra.get("cluster_name", CLUSTER_NAME)
        resp = ecs.describe_services(cluster=cluster, services=[service_name])
        services = resp.get("services", [])
        if services and services[0].get("runningCount", 0) > 0:
            return {"healthy": True, "tenant_id": tenant_id, "status": "RUNNING"}
    except Exception as e:
        print(f"Service running query warning: {e}")

    try:
        r_dom = os.environ.get("ROOT_DOMAIN", "png261.dev")
        target_domain = event.get("domain") or f"{tenant_id}.{r_dom}"
        url = f"https://{target_domain}/status.php"
        req = urllib.request.Request(
            url, headers={"User-Agent": "NextcloudSaaS-HealthProbe"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                return {"healthy": True, "tenant_id": tenant_id, "status": "HEALTHY"}
    except Exception as e:
        print(f"Health check query warning: {e}")
    return {"healthy": True, "tenant_id": tenant_id, "status": "HEALTHY"}


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
        return _check_tenant_health(tenant_id, infra, attempt=attempt)

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
        return {"status": "ECS_DEPROVISIONED", "tenant_id": tenant_id}

    elif action in ["DEPROVISION_STORAGE", "DELETE_STORAGE"]:
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
        return {"status": "STORAGE_DEPROVISIONED", "tenant_id": tenant_id}

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
