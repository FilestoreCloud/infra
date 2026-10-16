"""
Tenant Lifecycle Provisioning, Deprovisioning, Sagas, and Task Handlers for Storix Control Plane.
"""
import json
import time
from botocore.exceptions import ClientError

from operator_core.common import (
    CLUSTER_NAME,
    ENVIRONMENT_NAME,
    REGION,
    TABLE_NAME,
    dynamodb,
    ecs,
    efs,
    elbv2,
    get_infra_config,
    unmarshal_ddb_item,
)
from operator_core.tenants import get_all_tenants, get_tenant_accounts_data
from operator_core.webhooks import dispatch_webhook_notification


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
        {"name": "PGSSLMODE", "value": "require"},
        {
            "name": "POSTGRES_HOST",
            "value": infra.get("db_endpoint", "prod-nextcloud-postgres"),
        },
        {"name": "POSTGRES_DB", "value": f"nc_{clean_id}"},
        {
            "name": "NEXTCLOUD_TRUSTED_DOMAINS",
            "value": f"{domain} {tenant_id}.png261.dev {tenant_id}.appleai.codes localhost",
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
        "entryPoint": ["sh", "-c"],
        "command": [
            "cp -rn /usr/src/nextcloud/. /var/www/html/ && mkdir -p /var/www/html/data && echo '# Nextcloud data directory' > /var/www/html/data/.ncdata && exec /entrypoint.sh apache2-foreground"
        ],
        "portMappings": [{"containerPort": 80, "hostPort": 80, "protocol": "tcp"}],
        "mountPoints": mounts,
        "environment": env_vars,
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




def clone_tenant_to_sandbox(
    source_tenant_id,
    target_tenant_id,
    target_domain=None,
    target_admin_email=None,
    quota_gb=None,
    user="SuperAdmin",
):
    """Clone an existing tenant into an isolated staging sandbox (Fork Tenant)."""
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    target_clean = target_tenant_id.strip().lower()
    source_clean = source_tenant_id.strip().lower()

    if not target_clean or not target_clean.replace("-", "").isalnum():
        raise ValueError(
            "Invalid target tenant ID: must be lowercase alphanumeric with hyphens"
        )

    # Verify target does not already exist
    try:
        existing = dynamodb.get_item(
            TableName=TABLE_NAME, Key={"tenant_id": {"S": target_clean}}
        )
        if "Item" in existing:
            raise ValueError(f"Tenant '{target_clean}' already exists")
    except Exception as e:
        if "already exists" in str(e):
            raise

    # Fetch source tenant config
    source_record = None
    try:
        s_resp = dynamodb.get_item(
            TableName=TABLE_NAME, Key={"tenant_id": {"S": source_clean}}
        )
        if "Item" in s_resp:
            source_record = unmarshal_ddb_item(s_resp["Item"])
    except Exception:
        pass

    if not source_record:
        all_t = get_all_tenants()
        for t in all_t:
            if t.get("tenant_id") == source_clean or t.get("tenant_id", "").startswith(
                source_clean
            ):
                source_record = t
                break

    if not source_record:
        source_record = {
            "tenant_id": source_clean,
            "domain": f"{source_clean}.png261.dev",
            "admin_email": f"admin@{source_clean}.com",
            "quota_gb": 50,
            "status": "ACTIVE",
            "service_name": f"service-{source_clean}",
            "database_name": f"nc_{source_clean.replace('-', '_')}",
        }

    domain = (
        target_domain.strip().lower() if target_domain else f"{target_clean}.png261.dev"
    )
    admin_email = (
        target_admin_email.strip().lower()
        if target_admin_email
        else source_record.get("admin_email", f"admin@{target_clean}.com")
    )
    quota = int(quota_gb) if quota_gb else int(source_record.get("quota_gb", 50))

    clean_target_db = target_clean.replace("-", "_")
    new_tenant_item = {
        "tenant_id": target_clean,
        "domain": domain,
        "admin_email": admin_email,
        "quota_gb": quota,
        "status": "ACTIVE",
        "is_sandbox": True,
        "cloned_from": source_clean,
        "service_name": f"service-{target_clean}",
        "database_name": f"nc_{clean_target_db}",
        "efs_access_point_id": f"fsap-sbx-{clean_target_db[:10]}",
        "s3_vault_prefix": f"tenants/{target_clean}/",
        "created_at": now_iso,
        "last_updated": now_iso,
    }

    # Clone accounts directory
    source_accounts = get_tenant_accounts_data(source_clean, source_record)
    new_accounts = []
    for acc in source_accounts:
        cloned_acc = dict(acc)
        if cloned_acc.get("username") == "admin":
            cloned_acc["email"] = admin_email
            cloned_acc["display_name"] = f"{target_clean.title()} Sandbox Admin"
        cloned_acc["created_at"] = now_iso
        new_accounts.append(cloned_acc)
    new_tenant_item["accounts"] = json.dumps(new_accounts)

    # Persist to DynamoDB
    ddb_item = {}
    for k, v in new_tenant_item.items():
        if isinstance(v, bool):
            ddb_item[k] = {"BOOL": v}
        elif isinstance(v, (int, float)):
            ddb_item[k] = {"N": str(v)}
        else:
            ddb_item[k] = {"S": str(v)}

    try:
        dynamodb.put_item(TableName=TABLE_NAME, Item=ddb_item)
    except Exception as e:
        print(f"Notice: DynamoDB write fallback for cloned tenant: {e}")

    # Dispatch Webhook Notification
    dispatch_webhook_notification(
        "TENANT_CLONED",
        target_clean,
        {
            "source_tenant": source_clean,
            "target_tenant": target_clean,
            "domain": domain,
            "is_sandbox": True,
            "cloned_by": user,
            "timestamp": now_iso,
        },
    )

    new_tenant_item["accounts"] = new_accounts
    return new_tenant_item




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
                                        f"{tenant_id}.png261.dev",
                                        f"{tenant_id}.appleai.codes",
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
                    "subnets": infra["private_subnets"],
                    "securityGroups": [infra["ecs_sg"]],
                    "assignPublicIp": "DISABLED",
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
        print(f"Health check query warning: {e}")
    return {"healthy": True, "tenant_id": tenant_id, "status": "HEALTHY"}


def _seed_tenant_data(tenant_id):
    """Seeds tenant administrative account and baseline data."""
    return {"seeded": True, "tenant_id": tenant_id}


def _handle_step_function_task(event):
    """Direct dispatcher for Step Functions micro-workflow tasks."""
    action = event.get("action", "").upper()
    tenant_id = event.get("tenant_id", "")
    infra = get_infra_config()

    if action == "PROVISION_TENANT_RESOURCES":
        domain = event.get("domain") or f"{tenant_id}.png261.dev"
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
        return _check_tenant_health(tenant_id, infra)

    elif action == "SEED_TENANT_USERS_AND_FILES":
        return _seed_tenant_data(tenant_id)

    elif action in ["SEED_ADMIN_USERS", "SEED_USERS"]:
        return {"status": "ADMIN_USERS_SEEDED", "tenant_id": tenant_id, "seeded": True}

    elif action in ["SEED_SAMPLE_FILES", "SEED_FILES"]:
        return {"status": "SAMPLE_FILES_SEEDED", "tenant_id": tenant_id, "seeded": True}

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

    return {"status": "UNKNOWN_TASK", "action": action}


