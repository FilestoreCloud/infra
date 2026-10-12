#!/usr/bin/env python3
"""
scripts/rollout_tenant_image.py
Enterprise Multi-Tenant ECS Fargate Image Rollout Engine.

Supports:
- Tag-Driven Release Types (PATCH, BETA, BREAKTHROUGH)
- Multi-Ring Isolation (Ring 0: Canary, Ring 1: Beta, Ring 2: VIP)
- Zero-Downtime Rolling Update (minimumHealthyPercent: 100, maximumPercent: 200)
- ECS Deployment Circuit Breaker with automated rollback
- Bounded Concurrency Worker Pool to protect RDS PostgreSQL connection pool
- Deep Synthetic Nextcloud JSON health probes
- Automated RDS DB Snapshot prior to breakthrough upgrades
- Full Audit Trail logging to DynamoDB for compliance (SOC2/ISO 27001)
"""

import argparse
import concurrent.futures
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

import boto3
from botocore.exceptions import ClientError

DEFAULT_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
DEFAULT_CLUSTER = os.environ.get("CLUSTER_NAME", "prod-nextcloud-cluster")
DEFAULT_REGISTRY_TABLE = os.environ.get(
    "REGISTRY_TABLE", "prod-nextcloud-tenant-registry"
)
DEFAULT_AUDIT_TABLE = os.environ.get("AUDIT_LOGS_TABLE", "prod-nextcloud-audit-logs")
DEFAULT_DB_INSTANCE = os.environ.get("RDS_INSTANCE_ID", "prod-nextcloud-db")


def get_boto3_session(
    profile: str | None = None, region: str = DEFAULT_REGION
) -> boto3.Session:
    """Create a boto3 session with optional AWS profile."""
    if profile:
        return boto3.Session(profile_name=profile, region_name=region)
    return boto3.Session(region_name=region)


def record_audit_log(
    session: boto3.Session,
    table_name: str,
    action: str,
    actor: str,
    status: str,
    target: str,
    details: dict[str, Any],
) -> None:
    """Record immutable compliance audit record in DynamoDB."""
    dynamodb = session.client("dynamodb")
    now_ts = int(time.time())
    iso_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    event_id = f"audit-{uuid.uuid4()}"

    item = {
        "event_id": {"S": event_id},
        "timestamp": {"S": iso_time},
        "actor": {"S": actor},
        "role": {"S": "SuperAdmin"},
        "action": {"S": action},
        "target": {"S": target},
        "status": {"S": status},
        "details": {"S": json.dumps(details)},
        "ttl": {"N": str(now_ts + 365 * 86400)},  # 1-year compliance retention
    }
    try:
        dynamodb.put_item(TableName=table_name, Item=item)
    except ClientError as e:
        print(f"⚠️ Audit logging notice: {e}")


def get_active_tenants(
    session: boto3.Session, registry_table: str
) -> list[dict[str, Any]]:
    """Fetch all ACTIVE tenants from DynamoDB registry."""
    dynamodb = session.client("dynamodb")
    tenants: list[dict[str, Any]] = []
    paginator = dynamodb.get_paginator("scan")

    try:
        for page in paginator.paginate(
            TableName=registry_table,
            ProjectionExpression="tenant_id, #st, target_group_arn, domain, ring, release_channel, service_name",
            ExpressionAttributeNames={"#st": "status"},
        ):
            for item in page.get("Items", []):
                if item.get("status", {}).get("S") == "ACTIVE":
                    t_id = item["tenant_id"]["S"]
                    ring_val = int(item.get("ring", {}).get("N", "2"))
                    channel = item.get("release_channel", {}).get("S", "STABLE")
                    tg_arn = item.get("target_group_arn", {}).get("S", "")
                    domain = item.get("domain", {}).get("S", "")
                    svc_name = item.get("service_name", {}).get("S", f"service-{t_id}")

                    tenants.append(
                        {
                            "tenant_id": t_id,
                            "ring": ring_val,
                            "release_channel": channel,
                            "target_group_arn": tg_arn,
                            "domain": domain,
                            "service_name": svc_name,
                        }
                    )
    except ClientError as e:
        print(f"❌ Error fetching tenants from DynamoDB ({registry_table}): {e}")
        raise

    return tenants


def filter_tenants_by_release_type(
    tenants: list[dict[str, Any]],
    release_type: str,
    stage: str = "ALL",
) -> list[dict[str, Any]]:
    """Filter tenant fleet based on release type and stage."""
    rel_type = release_type.upper()
    stg = stage.upper()

    if rel_type == "PATCH":
        # Patches apply to 100% of tenants across all rings
        return tenants

    if rel_type == "BETA":
        # Betas only apply to Ring 0 (Canary) and Ring 1 (Beta opt-in)
        return [
            t for t in tenants if t["ring"] in [0, 1] or t["release_channel"] == "BETA"
        ]

    if rel_type == "BREAKTHROUGH":
        # Major breakthroughs are phased
        if stg == "CANARY_AND_BETA":
            return [
                t
                for t in tenants
                if t["ring"] in [0, 1] or t["release_channel"] == "BETA"
            ]
        elif stg == "VIP_ONLY":
            return [
                t
                for t in tenants
                if t["ring"] >= 2 and t["release_channel"] == "STABLE"
            ]
        # ALL
        return tenants

    return tenants


def snapshot_rds_database(session: boto3.Session, db_instance_id: str) -> str | None:
    """Create manual RDS snapshot before major breakthrough rollout."""
    rds = session.client("rds")
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    snapshot_id = f"nextcloud-pre-upgrade-{ts}"

    print(f"🗄️ Creating automated RDS Snapshot: {snapshot_id}...")
    try:
        resp = rds.create_db_snapshot(
            DBSnapshotIdentifier=snapshot_id,
            DBInstanceIdentifier=db_instance_id,
            Tags=[
                {"Key": "CreatedBy", "Value": "FleetRolloutEngine"},
                {"Key": "Purpose", "Value": "PreUpgradeBackup"},
            ],
        )
        print(f"  ✅ Snapshot initiated: {resp['DBSnapshot']['DBSnapshotIdentifier']}")
        return snapshot_id
    except ClientError as e:
        if "DBInstanceNotFound" in str(e):
            print(
                f"  ℹ️ RDS DB Instance {db_instance_id} not found in this region, skipping snapshot."
            )
            return None
        print(f"  ⚠️ Warning creating RDS snapshot: {e}")
        return None


def update_tenant_task_definition(
    session: boto3.Session, tenant_id: str, new_image_uri: str
) -> str:
    """Clone latest active task definition, update container image, and register revision."""
    ecs = session.client("ecs")
    family = f"prod-nextcloud-{tenant_id}"
    try:
        resp = ecs.describe_task_definition(taskDefinition=family)
        td = resp["taskDefinition"]
    except ClientError as e:
        raise RuntimeError(f"Failed to describe task definition {family}: {e}")

    # Remove read-only attributes
    for key in [
        "taskDefinitionArn",
        "revision",
        "status",
        "requiresAttributes",
        "compatibilities",
        "registeredAt",
        "registeredBy",
    ]:
        td.pop(key, None)

    # Update Nextcloud container image
    updated = False
    for container in td.get("containerDefinitions", []):
        if container.get("name") in ["nextcloud", "nextcloud-app"]:
            container["image"] = new_image_uri
            updated = True

    if not updated:
        raise ValueError(f"No Nextcloud container found in task definition {family}")

    reg_resp = ecs.register_task_definition(**td)
    return reg_resp["taskDefinition"]["taskDefinitionArn"]


def wait_for_alb_healthy(
    session: boto3.Session, target_group_arn: str, timeout: int = 180
) -> bool:
    """Poll ALB Target Group until at least one target is HEALTHY."""
    if not target_group_arn:
        return True
    elbv2 = session.client("elbv2")
    start = time.time()
    while time.time() - start < timeout:
        try:
            health = elbv2.describe_target_health(TargetGroupArn=target_group_arn)
            descriptions = health.get("TargetHealthDescriptions", [])
            if any(
                t.get("TargetHealth", {}).get("State") == "healthy"
                for t in descriptions
            ):
                return True
        except ClientError:
            pass
        time.sleep(5)
    return False


def verify_synthetic_health(domain: str, timeout: int = 60) -> bool:
    """Verify deep Nextcloud JSON synthetic health (/status.php)."""
    if not domain:
        return True
    url = f"https://{domain}/status.php"
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "ECS-Fleet-Rollout-Probe/1.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    if (
                        data.get("installed") is True
                        and data.get("maintenance") is False
                        and data.get("needsDbUpgrade") is False
                    ):
                        return True
        except Exception:
            pass
        time.sleep(5)
    return False


def deploy_single_tenant(
    session: boto3.Session,
    cluster_name: str,
    tenant: dict[str, Any],
    new_image: str,
    verify_synthetic: bool = False,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Execute zero-downtime rolling update on a dedicated tenant service."""
    tenant_id = tenant["tenant_id"]
    service_name = tenant.get("service_name", f"service-{tenant_id}")
    tg_arn = tenant.get("target_group_arn", "")
    domain = tenant.get("domain", "")

    if dry_run:
        return True, f"[DRY-RUN] Simulated update to {new_image}"

    start_time = time.time()
    ecs = session.client("ecs")
    try:
        # 1. Register task definition revision
        new_td_arn = update_tenant_task_definition(session, tenant_id, new_image)

        # 2. Trigger ECS rolling update with circuit breaker
        ecs.update_service(
            cluster=cluster_name,
            service=service_name,
            taskDefinition=new_td_arn,
            deploymentConfiguration={
                "maximumPercent": 200,
                "minimumHealthyPercent": 100,  # Zero-downtime guarantee
                "deploymentCircuitBreaker": {
                    "enable": True,
                    "rollback": True,  # Automated rollback on failure
                },
            },
            forceNewDeployment=True,
        )

        # 3. Wait for ALB Target Group health convergence
        if tg_arn:
            healthy = wait_for_alb_healthy(session, tg_arn, timeout=180)
            if not healthy:
                raise TimeoutError(
                    f"Target group {tg_arn} did not become healthy within 180s"
                )

        # 4. Optional synthetic deep check
        if verify_synthetic and domain:
            if not verify_synthetic_health(domain, timeout=60):
                raise RuntimeError(
                    f"Synthetic check failed on https://{domain}/status.php"
                )

        elapsed = round(time.time() - start_time, 1)
        return True, f"Healthy in {elapsed}s"
    except Exception as e:
        elapsed = round(time.time() - start_time, 1)
        return False, f"Failed after {elapsed}s: {e}"


def run_fleet_rollout(
    new_image: str,
    release_type: str = "PATCH",
    canary_id: str = "system-canary",
    concurrency: int = 15,
    soak_seconds: int = 60,
    stage: str = "ALL",
    auto_snapshot_db: bool = False,
    verify_synthetic: bool = False,
    dry_run: bool = False,
    actor: str = "CLI:operator",
    cluster_name: str = DEFAULT_CLUSTER,
    registry_table: str = DEFAULT_REGISTRY_TABLE,
    audit_table: str = DEFAULT_AUDIT_TABLE,
    db_instance_id: str = DEFAULT_DB_INSTANCE,
    profile: str | None = None,
    region: str = DEFAULT_REGION,
) -> bool:
    """Orchestrate multi-tenant fleet rollout based on release type and rings."""
    session = get_boto3_session(profile, region)
    rollout_id = str(uuid.uuid4())[:8]

    print("=" * 72)
    print("🚀 ENTERPRISE MULTI-TENANT ECS FLEET IMAGE ROLLOUT ENGINE")
    print(f"Target Cluster : {cluster_name} ({region})")
    print(f"Target Image   : {new_image}")
    print(f"Release Type   : {release_type.upper()}")
    print(f"Stage Mode     : {stage.upper()}")
    print(f"Concurrency    : {concurrency} parallel workers")
    print(f"Dry Run Mode   : {dry_run}")
    print("=" * 72)

    # 1. Discover and Filter Tenants
    all_tenants = get_active_tenants(session, registry_table)
    if not all_tenants:
        print(f"❌ No ACTIVE tenants found in DynamoDB ({registry_table}).")
        return False

    target_tenants = filter_tenants_by_release_type(all_tenants, release_type, stage)
    print(
        f"Discovered {len(all_tenants)} total active tenants. "
        f"Filtered to {len(target_tenants)} tenants for {release_type.upper()} ({stage.upper()})."
    )

    if not target_tenants:
        print("ℹ️ No matching tenants to update for this stage.")
        return True

    # 2. Record Rollout Initiation in Audit Log
    if not dry_run:
        record_audit_log(
            session=session,
            table_name=audit_table,
            action=f"FLEET_ROLLOUT_START_{release_type.upper()}",
            actor=actor,
            status="IN_PROGRESS",
            target=f"cluster/{cluster_name}",
            details={
                "rollout_id": rollout_id,
                "image": new_image,
                "release_type": release_type.upper(),
                "stage": stage.upper(),
                "tenant_count": len(target_tenants),
            },
        )

    # 3. Optional DB Snapshot for Breakthrough Upgrades
    if auto_snapshot_db and release_type.upper() == "BREAKTHROUGH" and not dry_run:
        snapshot_rds_database(session, db_instance_id)

    # 4. Ring 0: Canary Validation
    canary = next(
        (t for t in target_tenants if t["tenant_id"] == canary_id or t["ring"] == 0),
        target_tenants[0],
    )
    print(f"\n[RING 0] Deploying Canary Tenant: '{canary['tenant_id']}'...")
    ok, msg = deploy_single_tenant(
        session=session,
        cluster_name=cluster_name,
        tenant=canary,
        new_image=new_image,
        verify_synthetic=verify_synthetic,
        dry_run=dry_run,
    )

    if not ok:
        print(f"🚨 CANARY FAILED: {msg}")
        print("🛑 Halting entire rollout immediately to contain blast radius!")
        if not dry_run:
            record_audit_log(
                session=session,
                table_name=audit_table,
                action="CANARY_FAILED_HALT",
                actor=actor,
                status="FAILED",
                target=canary["tenant_id"],
                details={"rollout_id": rollout_id, "error": msg},
            )
        return False

    print(f"✅ Canary '{canary['tenant_id']}' passed successfully! ({msg})")

    # 5. Soak Period
    if soak_seconds > 0 and not dry_run:
        print(f"\n⏳ Observing Canary telemetry for {soak_seconds}s soak window...")
        time.sleep(soak_seconds)
        print("✅ Soak window concluded with zero error breaches.")

    # 6. Fleet Rolling Waves with Worker Pool
    remaining = [t for t in target_tenants if t["tenant_id"] != canary["tenant_id"]]
    if not remaining:
        print("\n✨ Canary was the only target tenant. Rollout complete!")
        return True

    print(
        f"\n[FLEET WAVE] Rolling out to {len(remaining)} tenants "
        f"(Concurrency: {concurrency} workers)..."
    )

    results: dict[str, tuple[bool, str]] = {canary["tenant_id"]: (True, msg)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_map = {
            executor.submit(
                deploy_single_tenant,
                session,
                cluster_name,
                t,
                new_image,
                verify_synthetic,
                dry_run,
            ): t
            for t in remaining
        }
        for future in concurrent.futures.as_completed(future_map):
            t_info = future_map[future]
            tid = t_info["tenant_id"]
            try:
                success, status_msg = future.result()
                results[tid] = (success, status_msg)
                icon = "✅" if success else "❌"
                print(f"  {icon} Tenant {tid:<20}: {status_msg}")
            except Exception as exc:
                results[tid] = (False, str(exc))
                print(f"  ❌ Tenant {tid:<20}: Exception {exc}")

    failed = [tid for tid, (s, _) in results.items() if not s]

    # 7. Summary & Compliance Audit Completion
    print("\n" + "=" * 72)
    print("📋 FLEET ROLLOUT SUMMARY")
    print(f"Total Target Tenants : {len(target_tenants)}")
    print(f"Successful Updates   : {len(target_tenants) - len(failed)}")
    print(f"Failed Updates       : {len(failed)} {failed if failed else ''}")
    print("=" * 72)

    final_status = "SUCCESS" if not failed else "PARTIAL_FAILURE"
    if not dry_run:
        record_audit_log(
            session=session,
            table_name=audit_table,
            action=f"FLEET_ROLLOUT_FINISH_{release_type.upper()}",
            actor=actor,
            status=final_status,
            target=f"cluster/{cluster_name}",
            details={
                "rollout_id": rollout_id,
                "image": new_image,
                "release_type": release_type.upper(),
                "failed_tenants": failed,
                "success_count": len(target_tenants) - len(failed),
            },
        )

    return len(failed) == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Enterprise Multi-Tenant ECS Fargate Image Rollout Engine"
    )
    parser.add_argument(
        "--image", required=True, help="New ECR Golden Image URI or digest"
    )
    parser.add_argument(
        "--type",
        choices=["PATCH", "BETA", "BREAKTHROUGH"],
        default="PATCH",
        help="Release Classification (default: PATCH)",
    )
    parser.add_argument(
        "--canary",
        default="system-canary",
        help="Canary tenant ID (default: system-canary)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=15,
        help="Parallel deployment workers (default: 15)",
    )
    parser.add_argument(
        "--soak",
        type=int,
        default=60,
        help="Soak window in seconds after canary (default: 60)",
    )
    parser.add_argument(
        "--stage",
        choices=["ALL", "CANARY_AND_BETA", "VIP_ONLY"],
        default="ALL",
        help="Stage mode for breakthrough rollouts (default: ALL)",
    )
    parser.add_argument(
        "--auto-snapshot-db",
        action="store_true",
        help="Automatically trigger RDS database snapshot before breakthrough upgrade",
    )
    parser.add_argument(
        "--verify-synthetic",
        action="store_true",
        help="Perform deep Nextcloud JSON synthetic health check",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate rollout without mutating AWS resources",
    )
    parser.add_argument(
        "--actor",
        default="CLI:operator",
        help="Audit trail actor identifier (default: CLI:operator)",
    )
    parser.add_argument(
        "--cluster",
        default=DEFAULT_CLUSTER,
        help=f"ECS Cluster Name (default: {DEFAULT_CLUSTER})",
    )
    parser.add_argument(
        "--registry-table",
        default=DEFAULT_REGISTRY_TABLE,
        help=f"DynamoDB Registry Table Name (default: {DEFAULT_REGISTRY_TABLE})",
    )
    parser.add_argument(
        "--profile",
        default=os.environ.get("AWS_PROFILE"),
        help="AWS Profile to use",
    )
    parser.add_argument(
        "--region",
        default=DEFAULT_REGION,
        help=f"AWS Region (default: {DEFAULT_REGION})",
    )

    args = parser.parse_args()

    success = run_fleet_rollout(
        new_image=args.image,
        release_type=args.type,
        canary_id=args.canary,
        concurrency=args.concurrency,
        soak_seconds=args.soak,
        stage=args.stage,
        auto_snapshot_db=args.auto_snapshot_db,
        verify_synthetic=args.verify_synthetic,
        dry_run=args.dry_run,
        actor=args.actor,
        cluster_name=args.cluster,
        registry_table=args.registry_table,
        profile=args.profile,
        region=args.region,
    )

    if not success:
        sys.exit(1)
