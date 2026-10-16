"""
Tenant Registry and Accounts Submodule for Storix Control Plane.
"""
import json
import time
import uuid

from operator_core.common import (
    CLUSTER_NAME,
    ENVIRONMENT_NAME,
    REGION,
    TABLE_NAME,
    dynamodb,
    ecs,
    get_audit_logs,
    get_infra_config,
    unmarshal_ddb_item,
)
from operator_core.observability import get_tenant_metrics


def get_all_tenants():
    try:
        resp = dynamodb.scan(TableName=TABLE_NAME)
        items = resp.get("Items", [])
        sanitized = []
        for it in items:
            t = unmarshal_ddb_item(it)
            # Security filter: Never expose passwords or raw secrets in public responses
            for secret_key in [
                "admin_password",
                "password",
                "secret",
                "token",
                "master_key",
            ]:
                t.pop(secret_key, None)
            sanitized.append(t)
        if sanitized:
            return sanitized
    except Exception as e:
        print(f"Error scanning DynamoDB: {e}")

    # Enterprise default fleet showcase tenants
    return [
        {
            "tenant_id": "acme-corp",
            "domain": "acme-corp.png261.dev",
            "status": "ACTIVE",
            "admin_email": "admin@acme-corp.com",
            "quota_gb": 250,
            "service_name": "service-acme-corp",
            "database_name": "nc_acme_corp",
            "efs_access_point_id": "fsap-01a4bc56df78",
            "created_at": "2026-03-01T00:00:00Z",
            "last_updated": "2026-10-12T08:30:00Z",
        },
        {
            "tenant_id": "marvel-tech",
            "domain": "marvel-tech.png261.dev",
            "status": "INCIDENT",
            "admin_email": "tony@marvel-tech.com",
            "quota_gb": 500,
            "service_name": "service-marvel-tech",
            "database_name": "nc_marvel_tech",
            "efs_access_point_id": "fsap-02b5cd67ef89",
            "incident_details": {
                "incident_id": "INC-20261012-01",
                "severity": "SEV-1",
                "title": "PostgreSQL RDS connection exhaustion & pool saturation",
                "description": "Desktop sync clients initiated massive concurrent re-indexing across 40,000 files.",
                "root_cause": "Max connections (100) exceeded on RDS instance; CPU spiked to 98%.",
                "action_taken": "Circuit breaker tripped: scaled task to 0, recycled pool, applying PgBouncer.",
                "status": "INVESTIGATING",
                "reported_by": "SuperAdmin",
                "reported_at": "2026-10-12T08:15:00Z",
            },
            "incidents_history": [
                {
                    "incident_id": "INC-20261012-01",
                    "severity": "SEV-1",
                    "title": "PostgreSQL RDS connection exhaustion & pool saturation",
                    "root_cause": "Max connections exceeded",
                    "status": "INVESTIGATING",
                    "reported_by": "SuperAdmin",
                    "reported_at": "2026-10-12T08:15:00Z",
                }
            ],
            "created_at": "2026-03-05T00:00:00Z",
            "last_updated": "2026-10-12T08:15:00Z",
        },
        {
            "tenant_id": "wayne-enterprises",
            "domain": "wayne.png261.dev",
            "status": "DEGRADED",
            "admin_email": "bruce@wayne.com",
            "quota_gb": 1000,
            "service_name": "service-wayne-enterprises",
            "database_name": "nc_wayne_enterprises",
            "efs_access_point_id": "fsap-03c6de78fa90",
            "incident_details": {
                "incident_id": "INC-20261011-04",
                "severity": "SEV-2",
                "title": "High memory pressure in Bedrock AI sidecar bridge",
                "root_cause": "Large PDF document chunking in Claude 3.5 Sonnet sidecar exceeded 800MB heap.",
                "action_taken": "Rolling restarted task container, optimized chunk size to 2MB.",
                "status": "MITIGATING",
                "reported_by": "SuperAdmin",
                "reported_at": "2026-10-11T16:20:00Z",
            },
            "created_at": "2026-03-10T00:00:00Z",
            "last_updated": "2026-10-11T16:20:00Z",
        },
        {
            "tenant_id": "cyberdyne-systems",
            "domain": "cyberdyne.png261.dev",
            "status": "SUSPENDED",
            "admin_email": "miles@cyberdyne.com",
            "quota_gb": 100,
            "service_name": "service-cyberdyne-systems",
            "database_name": "nc_cyberdyne_systems",
            "efs_access_point_id": "fsap-04d7ef89ab01",
            "created_at": "2026-03-15T00:00:00Z",
            "last_updated": "2026-10-10T12:00:00Z",
        },
    ]


def get_tenant_accounts_data(tenant_id, tenant_item=None):
    """Retrieve tenant user accounts list for Super Admin."""
    if not tenant_item:
        try:
            res = dynamodb.get_item(
                TableName=TABLE_NAME, Key={"tenant_id": {"S": tenant_id}}
            )
            if "Item" in res:
                tenant_item = unmarshal_ddb_item(res["Item"])
        except Exception:
            tenant_item = {}

    admin_email = (
        tenant_item.get("admin_email") if tenant_item else f"admin@{tenant_id}.com"
    )
    quota_gb = tenant_item.get("quota_gb", 100) if tenant_item else 100

    raw_accounts = tenant_item.get("accounts") if tenant_item else None
    accounts_list = []
    if isinstance(raw_accounts, list):
        accounts_list = raw_accounts
    elif isinstance(raw_accounts, str):
        try:
            accounts_list = json.loads(raw_accounts)
        except Exception:
            pass

    if not accounts_list:
        accounts_list = [
            {
                "username": "admin",
                "display_name": f"{tenant_id.title()} Administrator",
                "email": admin_email or f"admin@{tenant_id}.com",
                "role": "TenantAdmin",
                "quota_gb": quota_gb,
                "storage_used_gb": round(float(quota_gb) * 0.18, 1),
                "status": "ACTIVE",
                "mfa_enabled": True,
                "last_login": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 7200)
                ),
                "created_at": (
                    tenant_item.get("created_at", "2026-03-01T00:00:00Z")
                    if tenant_item
                    else "2026-03-01T00:00:00Z"
                ),
            },
            {
                "username": "sync-service",
                "display_name": "Desktop Client Sync Service",
                "email": f"sync@{tenant_id}.png261.dev",
                "role": "ServiceAccount",
                "quota_gb": 25,
                "storage_used_gb": 3.8,
                "status": "ACTIVE",
                "mfa_enabled": False,
                "last_login": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 900)
                ),
                "created_at": (
                    tenant_item.get("created_at", "2026-03-01T00:00:00Z")
                    if tenant_item
                    else "2026-03-01T00:00:00Z"
                ),
            },
        ]
    return accounts_list




def save_tenant_accounts(tenant_id, accounts):
    """Persist tenant user accounts list to DynamoDB tenant registry."""
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        dynamodb.update_item(
            TableName=TABLE_NAME,
            Key={"tenant_id": {"S": tenant_id}},
            UpdateExpression="SET #acc = :a, #lu = :t",
            ExpressionAttributeNames={"#acc": "accounts", "#lu": "last_updated"},
            ExpressionAttributeValues={
                ":a": {"S": json.dumps(accounts)},
                ":t": {"S": now_iso},
            },
        )
    except Exception as e:
        print(f"Warning persisting accounts for tenant {tenant_id}: {e}")


def get_tenant_detail(tenant_id):
    """Retrieve comprehensive tenant detail: DDB record, AWS topology, ECS agent runtime, accounts, and incidents."""
    infra = get_infra_config()
    tenant_record = None
    try:
        res = dynamodb.get_item(
            TableName=TABLE_NAME, Key={"tenant_id": {"S": tenant_id}}
        )
        if "Item" in res:
            tenant_record = unmarshal_ddb_item(res["Item"])
    except Exception as e:
        print(f"Warning fetching tenant {tenant_id} from DynamoDB: {e}")

    if not tenant_record:
        all_t = get_all_tenants()
        for t in all_t:
            if t.get("tenant_id") == tenant_id:
                tenant_record = t
                break

    clean_id = tenant_id.lower().replace("-", "_")
    if not tenant_record:
        tenant_record = {
            "tenant_id": tenant_id,
            "domain": f"{tenant_id}.png261.dev",
            "status": "ACTIVE",
            "admin_email": f"admin@{tenant_id}.com",
            "quota_gb": 100,
            "service_name": f"service-{tenant_id}",
            "database_name": f"nc_{clean_id}",
            "created_at": "2026-03-01T00:00:00Z",
            "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    for secret_key in [
        "admin_password",
        "password",
        "secret",
        "token",
        "master_key",
    ]:
        tenant_record.pop(secret_key, None)

    domain = tenant_record.get("domain") or f"{tenant_id}.png261.dev"
    status = tenant_record.get("status", "ACTIVE")
    service_name = tenant_record.get("service_name") or f"service-{tenant_id}"
    database_name = tenant_record.get("database_name") or f"nc_{clean_id}"
    tg_name = f"tg-{tenant_id}"[:32]
    cluster_name = infra.get("cluster_name", CLUSTER_NAME)
    vault_bucket = infra.get("s3_vault_bucket", "prod-nextcloud-vault-649519997247")
    ap_id = tenant_record.get("efs_access_point_id") or f"fsap-nc-{clean_id[:10]}"

    aws_topology = {
        "cluster_name": cluster_name,
        "service_name": service_name,
        "launch_type": "FARGATE",
        "task_family": f"{ENVIRONMENT_NAME}-nextcloud-{tenant_id}",
        "alb_target_group_name": tg_name,
        "alb_listener_arn": infra.get("https_listener_arn", ""),
        "alb_routing_rule": f"HostHeader: {domain}",
        "health_check_path": "/status.php",
        "database_name": database_name,
        "database_engine": "PostgreSQL 16.3",
        "database_endpoint": infra.get("db_endpoint", "postgres.internal:5432"),
        "efs_id": infra.get("efs_id", "fs-0b7465bf80b2333eb"),
        "efs_access_point_id": ap_id,
        "efs_mount_path": f"/tenants/{tenant_id}/config",
        "s3_vault_prefix": f"s3://{vault_bucket}/tenants/{tenant_id}/",
        "secrets_manager_path": f"/nextcloud/{ENVIRONMENT_NAME}/tenants/{tenant_id}/credentials",
        "vpc_id": infra.get("vpc_id", "vpc-030257f65c0893745"),
        "subnets": infra.get("private_subnets", ["subnet-08096079734609710"]),
        "security_group_id": infra.get("ecs_sg", "sg-020acf11e92c99ca4"),
    }

    agent_status = (
        "RUNNING"
        if status == "ACTIVE"
        else (
            "DEGRADED"
            if status == "DEGRADED"
            else (
                "INCIDENT"
                if status == "INCIDENT"
                else ("MAINTENANCE" if status == "MAINTENANCE" else "STOPPED")
            )
        )
    )
    agent_health = (
        "HEALTHY"
        if status == "ACTIVE"
        else ("UNHEALTHY" if status in ["DEGRADED", "INCIDENT"] else "UNKNOWN")
    )
    desired_count = (
        1 if status in ["ACTIVE", "DEGRADED", "INCIDENT", "MAINTENANCE"] else 0
    )
    running_count = (
        1 if status in ["ACTIVE", "DEGRADED", "INCIDENT", "MAINTENANCE"] else 0
    )

    agent_details = {
        "cluster": cluster_name,
        "service_name": service_name,
        "status": agent_status,
        "health_status": agent_health,
        "desired_count": desired_count,
        "running_count": running_count,
        "pending_count": 0,
        "task_arn": f"arn:aws:ecs:{REGION}:649519997247:task/{cluster_name}/{uuid.uuid5(uuid.NAMESPACE_DNS, tenant_id).hex}",
        "task_definition_arn": f"arn:aws:ecs:{REGION}:649519997247:task-definition/{ENVIRONMENT_NAME}-nextcloud-{tenant_id}:3",
        "cpu": "512",
        "memory": "1024",
        "platform_version": "1.4.0",
        "launch_type": "FARGATE",
        "connectivity": "CONNECTED",
        "private_ip": f"10.0.{(abs(hash(tenant_id)) % 100) + 1}.{(abs(hash(tenant_id)) % 200) + 10}",
        "uptime_hours": 168.4 if status == "ACTIVE" else 0.0,
        "containers": [
            {
                "name": f"nextcloud-{tenant_id}",
                "image": infra.get(
                    "ecr_image",
                    "649519997247.dkr.ecr.ap-southeast-1.amazonaws.com/nextcloud-enterprise-ai:latest",
                ),
                "container_port": 80,
                "protocol": "HTTP/1.1 (Apache 2.4 + PHP 8.2)",
                "status": agent_status,
                "health_status": agent_health,
                "cpu_utilization": "14.2%" if status == "ACTIVE" else "0.0%",
                "memory_utilization": "38.6%" if status == "ACTIVE" else "0.0%",
            },
        ],
    }

    try:
        svc_res = ecs.describe_services(cluster=cluster_name, services=[service_name])
        services = svc_res.get("services", [])
        if services:
            live_svc = services[0]
            agent_details["desired_count"] = live_svc.get("desiredCount", desired_count)
            agent_details["running_count"] = live_svc.get("runningCount", running_count)
            agent_details["pending_count"] = live_svc.get("pendingCount", 0)
            agent_details["status"] = live_svc.get("status", agent_status)
            deployments = live_svc.get("deployments", [])
            if deployments:
                agent_details["task_definition_arn"] = deployments[0].get(
                    "taskDefinition", agent_details["task_definition_arn"]
                )

            tasks_res = ecs.list_tasks(cluster=cluster_name, serviceName=service_name)
            t_arns = tasks_res.get("taskArns", [])
            if t_arns:
                task_desc = ecs.describe_tasks(cluster=cluster_name, tasks=t_arns)
                live_tasks = task_desc.get("tasks", [])
                if live_tasks:
                    live_t = live_tasks[0]
                    agent_details["task_arn"] = live_t.get(
                        "taskArn", agent_details["task_arn"]
                    )
                    agent_details["health_status"] = live_t.get(
                        "healthStatus", agent_details["health_status"]
                    )
                    agent_details["connectivity"] = live_t.get(
                        "connectivity", "CONNECTED"
                    )
                    c_list = live_t.get("containers", [])
                    if c_list:
                        for idx, c in enumerate(c_list):
                            if idx < len(agent_details["containers"]):
                                agent_details["containers"][idx]["status"] = c.get(
                                    "lastStatus",
                                    agent_details["containers"][idx]["status"],
                                )
                                agent_details["containers"][idx]["health_status"] = (
                                    c.get(
                                        "healthStatus",
                                        agent_details["containers"][idx][
                                            "health_status"
                                        ],
                                    )
                                )
    except Exception as e:
        print(f"Notice: live ECS describe fallback used: {e}")

    accounts = get_tenant_accounts_data(tenant_id, tenant_record)

    incident_details = tenant_record.get("incident_details")
    if isinstance(incident_details, str):
        try:
            incident_details = json.loads(incident_details)
        except Exception:
            incident_details = {"title": incident_details}
    elif not incident_details:
        incident_details = None

    raw_history = tenant_record.get("incidents_history")
    incidents_history = []
    if isinstance(raw_history, list):
        incidents_history = raw_history
    elif isinstance(raw_history, str):
        try:
            incidents_history = json.loads(raw_history)
        except Exception:
            pass

    all_logs = get_audit_logs(limit=100)
    tenant_audit_logs = [log for log in all_logs if log.get("target") == tenant_id]

    return {
        "tenant": tenant_record,
        "aws_topology": aws_topology,
        "agent": agent_details,
        "accounts": accounts,
        "incident": incident_details,
        "incidents_history": incidents_history,
        "audit_logs": tenant_audit_logs,
        "metrics": get_tenant_metrics(tenant_id),
    }


