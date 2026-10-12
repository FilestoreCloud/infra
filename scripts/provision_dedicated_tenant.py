#!/usr/bin/env python3
"""
Nextcloud Multi-Tenant SaaS - Dedicated Instance Provisioning Engine
Orchestrates isolated ECS Fargate Service, dedicated PostgreSQL database,
ALB Target Group, Host-based Listener Rule, Secrets Manager, and DynamoDB Registry
for each tenant.
"""

import argparse
import json
import os
import secrets
import string
import time

import boto3
from botocore.exceptions import ClientError

AWS_PROFILE = os.environ.get("AWS_PROFILE", "handon")
AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
CLUSTER_NAME = "prod-nextcloud-cluster"
TABLE_NAME = "prod-nextcloud-tenant-registry"

session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
ecs = session.client("ecs")
elbv2 = session.client("elbv2")
ssm = session.client("ssm")
secretsmanager = session.client("secretsmanager")
dynamodb = session.client("dynamodb")
cloudwatch = session.client("cloudwatch")
cfn = session.client("cloudformation")
app_autoscaling = session.client("application-autoscaling")


def generate_secure_password(length=16):
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def get_infra_metadata():
    """Retrieve shared infrastructure parameters from CloudFormation and SSM (supports both monolith and modular stacks)"""
    param_dict = {}
    try:
        paginator = ssm.get_paginator("get_parameters_by_path")
        for page in paginator.paginate(Path="/nextcloud/prod", Recursive=True):
            for p in page.get("Parameters", []):
                param_dict[p["Name"]] = p["Value"]
    except Exception as e:
        print(f"Warning fetching SSM parameters: {e}")

    outputs = {}
    # Check monolith stack and modular stacks
    stack_candidates = [
        "nextcloud-lean-production",
        "prod-nextcloud-05-compute",
        "prod-nextcloud-04-database",
        "prod-nextcloud-root",
    ]
    for s_name in stack_candidates:
        try:
            cfn_resp = cfn.describe_stacks(StackName=s_name)
            for o in cfn_resp["Stacks"][0].get("Outputs", []):
                outputs[o["OutputKey"]] = o["OutputValue"]
        except Exception:
            pass

    # Security group and roles (prefer SSM, fallback to CFN resources)
    ecs_sg = param_dict.get("/nextcloud/prod/security/ecs-sg-id")
    exec_role_arn = param_dict.get("/nextcloud/prod/infra/ecs-task-execution-role-arn")
    task_role_arn = param_dict.get("/nextcloud/prod/infra/ecs-task-role-arn")
    https_listener_arn = param_dict.get(
        "/nextcloud/prod/infra/alb-https-listener-arn"
    ) or outputs.get("ALBHTTPSListenerArn")

    if not (ecs_sg and exec_role_arn and task_role_arn and https_listener_arn):
        for s_name in [
            "nextcloud-lean-production",
            "prod-nextcloud-05-compute",
            "prod-nextcloud-02-security",
        ]:
            try:
                res = cfn.describe_stack_resources(StackName=s_name)
                for r in res["StackResources"]:
                    if r["LogicalResourceId"] == "ECSSecurityGroup" and not ecs_sg:
                        ecs_sg = r["PhysicalResourceId"]
                    elif (
                        r["LogicalResourceId"] == "ECSTaskExecutionRole"
                        and not exec_role_arn
                    ):
                        exec_role_arn = r["PhysicalResourceId"]
                    elif r["LogicalResourceId"] == "ECSTaskRole" and not task_role_arn:
                        task_role_arn = r["PhysicalResourceId"]
                    elif (
                        r["LogicalResourceId"] == "ALBHTTPSListener"
                        and not https_listener_arn
                    ):
                        https_listener_arn = r["PhysicalResourceId"]
            except Exception:
                pass

    # Lookup IAM role ARNs if needed
    iam = session.client("iam")
    if exec_role_arn and not exec_role_arn.startswith("arn:"):
        exec_role_arn = iam.get_role(RoleName=exec_role_arn)["Role"]["Arn"]
    if task_role_arn and not task_role_arn.startswith("arn:"):
        task_role_arn = iam.get_role(RoleName=task_role_arn)["Role"]["Arn"]

    return {
        "vpc_id": param_dict.get("/nextcloud/prod/infra/vpc-id"),
        "public_subnets": param_dict.get(
            "/nextcloud/prod/infra/public-subnets", ""
        ).split(","),
        "db_endpoint": param_dict.get("/nextcloud/prod/infra/db-endpoint"),
        "alb_dns": param_dict.get("/nextcloud/prod/infra/alb-dns"),
        "s3_vault_bucket": param_dict.get("/nextcloud/prod/infra/s3-vault-bucket"),
        "db_secret_arn": param_dict.get("/nextcloud/prod/infra/db-secret-arn")
        or outputs.get("DBSecretArn"),
        "litellm_secret_arn": outputs.get("LiteLLMSecretArn"),
        "ecs_sg": ecs_sg,
        "exec_role_arn": exec_role_arn,
        "task_role_arn": task_role_arn,
        "https_listener_arn": https_listener_arn,
        "golden_image": os.environ.get("CONTAINER_IMAGE", "nextcloud:30.0.17-apache"),
        "efs_id": param_dict.get("/nextcloud/prod/infra/efs-id")
        or outputs.get("EFSFileSystemId"),
    }


def ensure_database_exists(db_name, infra):
    """Ensure dedicated PostgreSQL database exists on RDS via one-off Fargate task"""
    print(f"🗄️ Verifying PostgreSQL database {db_name} exists on RDS...")
    db_pass_json = secretsmanager.get_secret_value(SecretId=infra["db_secret_arn"])[
        "SecretString"
    ]
    db_pass = json.loads(db_pass_json)["password"]

    php_code = f"""
$pdo = new PDO('pgsql:host={infra["db_endpoint"]};dbname=nextcloud', 'nextcloud', '{db_pass}');
$stmt = $pdo->query("SELECT 1 FROM pg_database WHERE datname = '{db_name}'");
if (!$stmt->fetchColumn()) {{
    $pdo->exec("CREATE DATABASE {db_name} OWNER nextcloud;");
    echo "Created database {db_name}" . PHP_EOL;
}} else {{
    echo "Database {db_name} already exists" . PHP_EOL;
}}
$pdo_db = new PDO('pgsql:host={infra["db_endpoint"]};dbname={db_name}', 'nextcloud', '{db_pass}');
$pdo_db->exec("GRANT ALL ON SCHEMA public TO nextcloud;");
$pdo_db->exec("ALTER SCHEMA public OWNER TO nextcloud;");
$pdo_db->exec("ALTER DATABASE {db_name} SET search_path TO public;");
$pdo_db->exec("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO nextcloud;");
$pdo_db->exec("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO nextcloud;");
echo "Schema public ownership and search_path configured on {db_name}" . PHP_EOL;
"""
    resp = ecs.run_task(
        cluster=CLUSTER_NAME,
        taskDefinition="prod-nextcloud-app",
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
                {"name": "nextcloud", "command": ["php", "-r", php_code]},
                {"name": "litellm-sidecar", "command": ["echo", "sidecar skipped"]},
            ]
        },
    )
    task_arn = resp["tasks"][0]["taskArn"]
    task_id = task_arn.split("/")[-1]
    print(f"  ⏳ Waiting for DB initialization task ({task_id})...")
    for _ in range(30):
        time.sleep(5)
        desc = ecs.describe_tasks(cluster=CLUSTER_NAME, tasks=[task_arn])
        if not desc.get("tasks"):
            continue
        t_status = desc["tasks"][0].get("lastStatus")
        containers = desc["tasks"][0].get("containers", [])
        nc_cont = next((c for c in containers if c.get("name") == "nextcloud"), None)
        if nc_cont and nc_cont.get("exitCode") is not None:
            if nc_cont.get("exitCode") == 0:
                print(
                    "  ⚡ DB task nextcloud container completed successfully. Terminating task..."
                )
                try:
                    ecs.stop_task(
                        cluster=CLUSTER_NAME,
                        task=task_arn,
                        reason="DB init container completed",
                    )
                except Exception:
                    pass
                break
            else:
                raise RuntimeError(
                    f"DB task nextcloud container failed with exit code {nc_cont.get('exitCode')}"
                )
        if t_status == "STOPPED":
            break
    waiter = ecs.get_waiter("tasks_stopped")
    waiter.wait(cluster=CLUSTER_NAME, tasks=[task_arn])
    print(f"  ✅ Database {db_name} is ready on RDS!")


def ensure_efs_access_point(tenant_id, efs_id):
    """Ensure dedicated EFS Access Point exists for tenant's /var/www/html/config"""
    if not efs_id:
        print(
            "  ⚠️ Warning: EFS ID not found in metadata, skipping EFS Access Point creation"
        )
        return None
    efs_client = session.client("efs")
    ap_name = f"ap-{tenant_id}"
    try:
        paginator = efs_client.get_paginator("describe_access_points")
        for page in paginator.paginate(FileSystemId=efs_id):
            for ap in page.get("AccessPoints", []):
                if (
                    ap.get("Name") == ap_name
                    or ap.get("RootDirectory", {}).get("Path")
                    == f"/tenants/{tenant_id}/config"
                ):
                    print(f"  ℹ️ Found existing EFS Access Point: {ap['AccessPointId']}")
                    return ap["AccessPointId"]
    except Exception as e:
        print(f"  ℹ️ Notice checking existing Access Points: {e}")

    print(f"  ⚡ Creating dedicated EFS Access Point for tenant {tenant_id}...")
    try:
        resp = efs_client.create_access_point(
            FileSystemId=efs_id,
            PosixUser={"Uid": 33, "Gid": 33},
            RootDirectory={
                "Path": f"/tenants/{tenant_id}/config",
                "CreationInfo": {"OwnerUid": 33, "OwnerGid": 33, "Permissions": "0755"},
            },
            Tags=[
                {"Key": "Name", "Value": ap_name},
                {"Key": "Tenant", "Value": tenant_id},
                {"Key": "Environment", "Value": "prod"},
            ],
        )
        ap_id = resp["AccessPointId"]
        print(
            f"  ✅ Created EFS Access Point: {ap_id} (Path: /tenants/{tenant_id}/config)"
        )
        return ap_id
    except Exception as e:
        print(f"  ⚠️ Error creating EFS Access Point: {e}")
        return None


def provision_tenant(
    tenant_id,
    domain,
    admin_password=None,
    quota_gb=100,
    ring=None,
    release_channel="STABLE",
):
    if ring is None:
        ring = 0 if "canary" in tenant_id.lower() else 2
    print("\n============================================================")
    print(f"🚀 PROVISIONING DEDICATED INSTANCE: {tenant_id}")
    print(f"Domain: {domain} | Quota: {quota_gb} GB")
    print("============================================================")

    clean_id = tenant_id.lower().replace("-", "_")
    db_name = f"nc_{clean_id}"
    tg_name = f"tg-{tenant_id}"[:32]
    service_name = f"service-{tenant_id}"
    task_family = f"prod-nextcloud-{tenant_id}"

    if not admin_password:
        admin_password = generate_secure_password(16)

    infra = get_infra_metadata()
    print("✅ Infrastructure metadata resolved:")
    print(f"   VPC: {infra['vpc_id']} | DB: {infra['db_endpoint']}")
    print(f"   Subnets: {infra['public_subnets']} | SG: {infra['ecs_sg']}")

    # Ensure dedicated DB exists
    ensure_database_exists(db_name, infra)

    # 1. Create Secrets Manager Secret for tenant admin
    secret_name = f"/nextcloud/prod/tenants/{tenant_id}/admin-credentials"
    print("\n[1/6] Storing Admin Credentials in Secrets Manager...")
    try:
        sec_resp = secretsmanager.create_secret(
            Name=secret_name,
            Description=f"Admin credentials for dedicated Nextcloud tenant {tenant_id}",
            SecretString=json.dumps({"username": "admin", "password": admin_password}),
        )
        admin_secret_arn = sec_resp["ARN"]
        print(f"  ✅ Created secret: {secret_name}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceExistsException":
            secretsmanager.put_secret_value(
                SecretId=secret_name,
                SecretString=json.dumps(
                    {"username": "admin", "password": admin_password}
                ),
            )
            admin_secret_arn = secretsmanager.describe_secret(SecretId=secret_name)[
                "ARN"
            ]
            print(f"  ℹ️ Updated existing secret: {secret_name}")
        else:
            raise

    # 2. Create Target Group
    print(f"\n[2/6] Creating Target Group: {tg_name}...")
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
            HealthCheckTimeoutSeconds=10,
            HealthyThresholdCount=2,
            UnhealthyThresholdCount=5,
            Matcher={"HttpCode": "200-400"},
            Tags=[
                {"Key": "Tenant", "Value": tenant_id},
                {"Key": "Environment", "Value": "prod"},
            ],
        )
        tg_arn = tg_resp["TargetGroups"][0]["TargetGroupArn"]
        print(f"  ✅ Target Group created: {tg_arn}")
    except ClientError as e:
        if "DuplicateTargetGroupName" in str(e):
            tgs = elbv2.describe_target_groups(Names=[tg_name])["TargetGroups"]
            tg_arn = tgs[0]["TargetGroupArn"]
            print(f"  ℹ️ Target Group already exists: {tg_arn}")
        else:
            raise

    # Enable ALB Sticky Sessions & Connection Draining
    try:
        elbv2.modify_target_group_attributes(
            TargetGroupArn=tg_arn,
            Attributes=[
                {"Key": "stickiness.enabled", "Value": "true"},
                {"Key": "stickiness.type", "Value": "lb_cookie"},
                {"Key": "stickiness.lb_cookie.duration_seconds", "Value": "86400"},
                {"Key": "deregistration_delay.timeout_seconds", "Value": "15"},
            ],
        )
        print("  ✅ Target Group stickiness enabled (lb_cookie / 24h, 15s draining)")
    except Exception as e:
        print(f"  ⚠️ Warning setting TG stickiness: {e}")

    # 3. Create ALB Listener Rule (Host-based routing)
    print(f"\n[3/6] Configuring Host-based Routing Rule for {domain}...")
    existing_rules = elbv2.describe_rules(ListenerArn=infra["https_listener_arn"])[
        "Rules"
    ]
    priorities = [
        int(r["Priority"])
        for r in existing_rules
        if r["Priority"].isdigit() and int(r["Priority"]) < 1000
    ]
    next_priority = (max(priorities) + 10) if priorities else 10

    # Check if a rule already exists for this host
    rule_arn = None
    for r in existing_rules:
        for c in r.get("Conditions", []):
            if c.get("Field") == "host-header" and domain in c.get(
                "HostHeaderConfig", {}
            ).get("Values", []):
                rule_arn = r["RuleArn"]
                print(
                    f"  ℹ️ Rule already exists for {domain} (Priority: {r['Priority']})"
                )
                break
        if rule_arn:
            break

    if not rule_arn:
        rule_resp = elbv2.create_rule(
            ListenerArn=infra["https_listener_arn"],
            Priority=next_priority,
            Conditions=[
                {
                    "Field": "host-header",
                    "HostHeaderConfig": {
                        "Values": list(
                            dict.fromkeys(
                                [
                                    domain,
                                    f"{tenant_id}.png261.dev",
                                    f"{tenant_id}.appleai.codes",
                                ]
                            )
                        )
                    },
                }
            ],
            Actions=[{"Type": "forward", "TargetGroupArn": tg_arn}],
            Tags=[{"Key": "Tenant", "Value": tenant_id}],
        )
        rule_arn = rule_resp["Rules"][0]["RuleArn"]
        print(f"  ✅ Created Listener Rule at Priority {next_priority} -> {domain}")

    # 4. Configure Dedicated EFS Access Point for config persistence
    print(f"\n[4/7] Ensuring Dedicated EFS Access Point for {tenant_id}...")
    access_point_id = ensure_efs_access_point(tenant_id, infra.get("efs_id"))

    # 5. Register Task Definition for Dedicated Tenant
    print(f"\n[5/7] Registering Task Definition: {task_family}...")
    volumes = []
    nextcloud_mounts = []
    if infra.get("efs_id") and access_point_id:
        volumes.append(
            {
                "name": "nextcloud-config",
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
        nextcloud_mounts.append(
            {
                "sourceVolume": "nextcloud-config",
                "containerPath": "/var/www/html/config",
                "readOnly": False,
            }
        )

    task_def = {
        "family": task_family,
        "cpu": "1024",
        "memory": "2048",
        "networkMode": "awsvpc",
        "requiresCompatibilities": ["FARGATE"],
        "executionRoleArn": infra["exec_role_arn"],
        "taskRoleArn": infra["task_role_arn"],
        "volumes": volumes,
        "containerDefinitions": [
            {
                "name": "nextcloud",
                "image": infra["golden_image"],
                "essential": True,
                "entryPoint": ["sh", "-c"],
                "command": [
                    "cp -rn /usr/src/nextcloud/. /var/www/html/ && mkdir -p /var/www/html/data && echo '# Nextcloud data directory' > /var/www/html/data/.ncdata && chown -R www-data:www-data /var/www/html && exec /entrypoint.sh apache2-foreground"
                ],
                "portMappings": [
                    {"containerPort": 80, "hostPort": 80, "protocol": "tcp"}
                ],
                "mountPoints": nextcloud_mounts,
                "environment": [
                    {"name": "POSTGRES_HOST", "value": infra["db_endpoint"]},
                    {"name": "POSTGRES_DB", "value": db_name},
                    {"name": "POSTGRES_USER", "value": "nextcloud"},
                    {"name": "NEXTCLOUD_ADMIN_USER", "value": "admin"},
                    {
                        "name": "NEXTCLOUD_TRUSTED_DOMAINS",
                        "value": f"{domain} {tenant_id}.png261.dev {tenant_id}.appleai.codes {infra['alb_dns']} localhost 127.0.0.1",
                    },
                    {"name": "OVERWRITECLIURL", "value": f"https://{domain}"},
                    {"name": "OVERWRITEPROTOCOL", "value": "https"},
                    {"name": "TRUSTED_PROXIES", "value": "10.0.0.0/16"},
                    {"name": "NEXTCLOUD_ENABLE_AI", "value": "true"},
                    {"name": "BEDROCK_REGION", "value": AWS_REGION},
                    {
                        "name": "BEDROCK_DEFAULT_MODEL",
                        "value": "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
                    },
                    {"name": "LITELLM_API_URL", "value": "http://127.0.0.1:4000/v1"},
                    {
                        "name": "OBJECTSTORE_S3_BUCKET",
                        "value": infra["s3_vault_bucket"],
                    },
                    {"name": "OBJECTSTORE_S3_REGION", "value": AWS_REGION},
                    {"name": "OBJECTSTORE_S3_AUTOCREATE", "value": "false"},
                    {"name": "OBJECTSTORE_S3_USEPATH_STYLE", "value": "false"},
                    {"name": "OBJECTSTORE_S3_SSL", "value": "true"},
                    {"name": "AWS_REGION", "value": AWS_REGION},
                    {"name": "NC_maintenance_window_start", "value": "2"},
                    {"name": "NC_default_phone_region", "value": "VN"},
                    {"name": "NC_setup_create_db_user", "value": "false"},
                ],
                "secrets": [
                    {
                        "name": "POSTGRES_PASSWORD",
                        "valueFrom": f"{infra['db_secret_arn']}:password::",
                    },
                    {
                        "name": "NEXTCLOUD_ADMIN_PASSWORD",
                        "valueFrom": f"{admin_secret_arn}:password::",
                    },
                    {
                        "name": "LITELLM_API_KEY",
                        "valueFrom": f"{infra['litellm_secret_arn']}:token::",
                    },
                ],
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": "/ecs/prod-nextcloud",
                        "awslogs-region": AWS_REGION,
                        "awslogs-stream-prefix": f"tenant-{tenant_id}",
                    },
                },
                "healthCheck": {
                    "command": [
                        "CMD-SHELL",
                        "curl -f http://localhost/status.php || exit 1",
                    ],
                    "interval": 30,
                    "timeout": 10,
                    "retries": 5,
                    "startPeriod": 180,
                },
            },
            {
                "name": "litellm-sidecar",
                "image": "ghcr.io/berriai/litellm:main-v1.49.5",
                "essential": False,
                "portMappings": [
                    {"containerPort": 4000, "hostPort": 4000, "protocol": "tcp"}
                ],
                "environment": [
                    {"name": "AWS_REGION", "value": AWS_REGION},
                    {"name": "NUM_WORKERS", "value": "2"},
                ],
                "secrets": [
                    {
                        "name": "LITELLM_MASTER_KEY",
                        "valueFrom": f"{infra['litellm_secret_arn']}:token::",
                    }
                ],
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": "/ecs/prod-nextcloud",
                        "awslogs-region": AWS_REGION,
                        "awslogs-stream-prefix": f"litellm-{tenant_id}",
                    },
                },
            },
        ],
    }

    reg_resp = ecs.register_task_definition(**task_def)
    task_def_arn = reg_resp["taskDefinition"]["taskDefinitionArn"]
    print(f"  ✅ Task Definition registered: {task_def_arn}")

    # 6. Create or Update Dedicated ECS Fargate Service
    print(f"\n[6/7] Creating Dedicated ECS Service: {service_name}...")
    try:
        ecs.create_service(
            cluster=CLUSTER_NAME,
            serviceName=service_name,
            taskDefinition=task_def_arn,
            desiredCount=1,
            capacityProviderStrategy=[
                {"capacityProvider": "FARGATE", "base": 1, "weight": 1},
                {"capacityProvider": "FARGATE_SPOT", "base": 0, "weight": 3},
            ],
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": infra["public_subnets"],
                    "securityGroups": [infra["ecs_sg"]],
                    "assignPublicIp": "ENABLED",
                }
            },
            loadBalancers=[
                {
                    "targetGroupArn": tg_arn,
                    "containerName": "nextcloud",
                    "containerPort": 80,
                }
            ],
            deploymentConfiguration={
                "maximumPercent": 200,
                "minimumHealthyPercent": 100,
                "deploymentCircuitBreaker": {"enable": True, "rollback": True},
            },
            tags=[
                {"key": "Tenant", "value": tenant_id},
                {"key": "Environment", "value": "prod"},
            ],
        )
        print(f"  ✅ ECS Service created: {service_name}")
    except ClientError as e:
        if "InvalidParameterException" in str(
            e
        ) and "Creation of service was not idempotent" in str(e):
            ecs.update_service(
                cluster=CLUSTER_NAME,
                service=service_name,
                taskDefinition=task_def_arn,
                desiredCount=1,
            )
            print("  ℹ️ ECS Service already exists, updated with new task definition")
        else:
            raise

    # 6b. Configure Application Auto Scaling for Dedicated Tenant (1 to 4 Tasks)
    print(f"\n[6b/7] Configuring Application Auto Scaling for {service_name}...")
    try:
        resource_id = f"service/{CLUSTER_NAME}/{service_name}"
        app_autoscaling.register_scalable_target(
            ServiceNamespace="ecs",
            ResourceId=resource_id,
            ScalableDimension="ecs:service:DesiredCount",
            MinCapacity=1,
            MaxCapacity=4,
        )
        app_autoscaling.put_scaling_policy(
            PolicyName=f"prod-cpu-scaling-{tenant_id}",
            ServiceNamespace="ecs",
            ResourceId=resource_id,
            ScalableDimension="ecs:service:DesiredCount",
            PolicyType="TargetTrackingScaling",
            TargetTrackingScalingPolicyConfiguration={
                "TargetValue": 70.0,
                "PredefinedMetricSpecification": {
                    "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
                },
                "ScaleOutCooldown": 60,
                "ScaleInCooldown": 300,
            },
        )
        print(
            "  ✅ Application Auto Scaling configured: 1 to 4 tasks (Target: 70% CPU)"
        )
    except Exception as e:
        print(f"  ⚠️ Notice setting up Application Auto Scaling: {e}")

    # 7. Save in DynamoDB Tenant Registry & Metrics
    print("\n[7/7] Registering Tenant in DynamoDB & Emitting Metrics...")
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    db_item = {
        "tenant_id": {"S": tenant_id},
        "status": {"S": "ACTIVE"},
        "domain": {"S": domain},
        "admin_user": {"S": "admin"},
        "admin_password": {"S": admin_password},
        "database": {"S": db_name},
        "service_name": {"S": service_name},
        "target_group_arn": {"S": tg_arn},
        "quota_gb": {"N": str(quota_gb)},
        "ring": {"N": str(ring)},
        "release_channel": {"S": release_channel},
        "isolation_model": {"S": "DEDICATED_INSTANCE"},
        "created_at": {"S": timestamp},
        "last_updated": {"S": timestamp},
    }
    if access_point_id:
        db_item["efs_access_point_id"] = {"S": access_point_id}

    dynamodb.put_item(TableName=TABLE_NAME, Item=db_item)
    print("  ✅ DynamoDB Tenant Registry updated")

    cloudwatch.put_metric_data(
        Namespace="Nextcloud/SaaS",
        MetricData=[
            {
                "MetricName": "TenantActiveStatus",
                "Value": 1.0,
                "Unit": "Count",
                "Dimensions": [{"Name": "TenantId", "Value": tenant_id}],
            },
            {
                "MetricName": "TenantStorageUsedMB",
                "Value": 0.1,
                "Unit": "Megabytes",
                "Dimensions": [{"Name": "TenantId", "Value": tenant_id}],
            },
        ],
    )
    print("  ✅ CloudWatch metrics published")

    print("\n" + "=" * 60)
    print(f"🎉 DEDICATED TENANT INSTANCE PROVISIONED: {tenant_id}")
    print("=" * 60)
    print(f"🔗 Dedicated Ingress URL: https://{domain}")
    print("👑 Dedicated Admin User:  admin")
    print(f"🔑 Dedicated Admin Pass:  {admin_password}")
    print(f"🗄️ Dedicated PostgreSQL:  {db_name}")
    print(f"⚡ Dedicated ECS Service:  {service_name}")
    print("=" * 60)
    return {
        "tenant_id": tenant_id,
        "domain": domain,
        "admin_user": "admin",
        "admin_password": admin_password,
        "database": db_name,
        "service_name": service_name,
    }


def suspend_tenant(tenant_id):
    print(f"⏸️ Suspending tenant: {tenant_id}...")
    service_name = f"service-{tenant_id}"
    try:
        ecs.update_service(cluster=CLUSTER_NAME, service=service_name, desiredCount=0)
    except ClientError as e:
        if "ServiceNotFoundException" in str(e):
            print(
                f"  ℹ️ ECS Service {service_name} not found in {CLUSTER_NAME}, skipping task scaling."
            )
        else:
            raise

    dynamodb.update_item(
        TableName=TABLE_NAME,
        Key={"tenant_id": {"S": tenant_id}},
        UpdateExpression="SET #st = :s, #lu = :t",
        ExpressionAttributeNames={"#st": "status", "#lu": "last_updated"},
        ExpressionAttributeValues={
            ":s": {"S": "SUSPENDED"},
            ":t": {"S": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        },
    )
    cloudwatch.put_metric_data(
        Namespace="Nextcloud/SaaS",
        MetricData=[
            {
                "MetricName": "TenantActiveStatus",
                "Value": 0.0,
                "Unit": "Count",
                "Dimensions": [{"Name": "TenantId", "Value": tenant_id}],
            }
        ],
    )
    print(f"✅ Tenant {tenant_id} SUSPENDED")


def resume_tenant(tenant_id):
    print(f"▶️ Resuming tenant: {tenant_id}...")
    service_name = f"service-{tenant_id}"
    try:
        ecs.update_service(cluster=CLUSTER_NAME, service=service_name, desiredCount=1)
    except ClientError as e:
        if "ServiceNotFoundException" in str(e):
            print(
                f"  ℹ️ ECS Service {service_name} not found in {CLUSTER_NAME}, skipping task scaling."
            )
        else:
            raise

    dynamodb.update_item(
        TableName=TABLE_NAME,
        Key={"tenant_id": {"S": tenant_id}},
        UpdateExpression="SET #st = :s, #lu = :t",
        ExpressionAttributeNames={"#st": "status", "#lu": "last_updated"},
        ExpressionAttributeValues={
            ":s": {"S": "ACTIVE"},
            ":t": {"S": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        },
    )
    cloudwatch.put_metric_data(
        Namespace="Nextcloud/SaaS",
        MetricData=[
            {
                "MetricName": "TenantActiveStatus",
                "Value": 1.0,
                "Unit": "Count",
                "Dimensions": [{"Name": "TenantId", "Value": tenant_id}],
            }
        ],
    )
    print(f"✅ Tenant {tenant_id} RESUMED")


def deprovision_tenant(tenant_id):
    print(f"🗑️ Deprovisioning dedicated tenant: {tenant_id}...")
    service_name = f"service-{tenant_id}"
    tg_name = f"tg-{tenant_id}"[:32]
    infra = get_infra_metadata()

    # 1. Scale down and delete ECS service
    print(f"  [1/5] Terminating ECS Service {service_name}...")
    try:
        ecs.update_service(cluster=CLUSTER_NAME, service=service_name, desiredCount=0)
        time.sleep(1)
        ecs.delete_service(cluster=CLUSTER_NAME, service=service_name, force=True)
        print(f"  ✅ ECS Service {service_name} deleted")
    except ClientError as e:
        if "ServiceNotFoundException" in str(e):
            print(f"  ℹ️ ECS Service {service_name} not found, skipping.")
        else:
            print(f"  ⚠️ Warning deleting ECS Service: {e}")

    # 2. Delete ALB Listener Rule
    if infra.get("https_listener_arn"):
        print("  [2/5] Cleaning up ALB Host Routing Rule...")
        try:
            tgs = elbv2.describe_target_groups(Names=[tg_name])["TargetGroups"]
            if tgs:
                tg_arn = tgs[0]["TargetGroupArn"]
                rules = elbv2.describe_rules(ListenerArn=infra["https_listener_arn"])[
                    "Rules"
                ]
                for r in rules:
                    for a in r.get("Actions", []):
                        if a.get("TargetGroupArn") == tg_arn:
                            elbv2.delete_rule(RuleArn=r["RuleArn"])
                            print(f"  ✅ Deleted ALB Rule: {r['RuleArn']}")
        except ClientError as e:
            print(f"  ⚠️ Warning deleting Listener Rule: {e}")

    # 3. Delete Target Group
    print(f"  [3/5] Deleting Target Group {tg_name}...")
    try:
        tgs = elbv2.describe_target_groups(Names=[tg_name])["TargetGroups"]
        if tgs:
            elbv2.delete_target_group(TargetGroupArn=tgs[0]["TargetGroupArn"])
            print(f"  ✅ Target Group {tg_name} deleted")
    except ClientError as e:
        print(f"  ⚠️ Warning deleting Target Group: {e}")

    # 4. Clean up Secrets Manager admin credentials
    secret_name = f"/nextcloud/prod/tenants/{tenant_id}/admin-credentials"
    print("  [4/5] Deleting Admin Secret...")
    try:
        secretsmanager.delete_secret(
            SecretId=secret_name, ForceDeleteWithoutRecovery=True
        )
        print(f"  ✅ Deleted Secret: {secret_name}")
    except ClientError as e:
        if "ResourceNotFoundException" not in str(e):
            print(f"  ⚠️ Warning deleting secret: {e}")

    # 5. Delete DynamoDB Registry Record
    print(f"  [5/5] Deregistering from DynamoDB {TABLE_NAME}...")
    try:
        dynamodb.delete_item(TableName=TABLE_NAME, Key={"tenant_id": {"S": tenant_id}})
        print(f"  ✅ Tenant {tenant_id} removed from DynamoDB")
    except ClientError as e:
        print(f"  ⚠️ Warning removing DynamoDB item: {e}")

    # CloudWatch Status Metric
    try:
        cloudwatch.put_metric_data(
            Namespace="Nextcloud/SaaS",
            MetricData=[
                {
                    "MetricName": "TenantActiveStatus",
                    "Value": 0.0,
                    "Unit": "Count",
                    "Dimensions": [{"Name": "TenantId", "Value": tenant_id}],
                }
            ],
        )
    except Exception:
        pass

    print(f"\n🎉 DEDICATED TENANT {tenant_id} DEPROVISIONED SUCCESSFULLY\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Nextcloud Dedicated Instance Tenant Manager"
    )
    parser.add_argument(
        "--action",
        choices=["PROVISION", "SUSPEND", "RESUME", "DEPROVISION"],
        default="PROVISION",
    )
    parser.add_argument("--tenant", required=True, help="Tenant ID (e.g. acme-corp)")
    parser.add_argument(
        "--domain", default=None, help="Custom domain (e.g. acme.appleai.codes)"
    )
    parser.add_argument("--password", default=None, help="Initial admin password")
    parser.add_argument("--quota", type=int, default=100, help="Storage quota in GB")
    parser.add_argument(
        "--ring",
        type=int,
        default=None,
        help="Deployment Ring (0: Canary, 1: Beta, 2: VIP)",
    )
    parser.add_argument(
        "--release-channel",
        choices=["STABLE", "BETA"],
        default="STABLE",
        help="Release Channel (STABLE or BETA)",
    )

    args = parser.parse_args()
    domain = args.domain or f"{args.tenant}.png261.dev"

    if args.action == "PROVISION":
        provision_tenant(
            args.tenant,
            domain,
            args.password,
            args.quota,
            args.ring,
            args.release_channel,
        )
    elif args.action == "SUSPEND":
        suspend_tenant(args.tenant)
    elif args.action == "RESUME":
        resume_tenant(args.tenant)
    elif args.action == "DEPROVISION":
        deprovision_tenant(args.tenant)
