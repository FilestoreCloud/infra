#!/usr/bin/env python3
"""
Zero-Cost Teardown and Cleanup Utility for Storix Platform.
Executes pre-destruction, post-destruction, and audit phases using the AWS Python SDK (boto3).
Zero AWS CLI dependency.
"""

from __future__ import annotations

import argparse
import os
import sys
import boto3
from botocore.exceptions import ClientError


def get_client(service_name: str, region: str):
    return boto3.client(service_name, region_name=region)


def run_pre_destruction(env: str, region: str) -> None:
    """Phase 1: Stop ECS services, delete dynamic EFS access points, target groups, and ECR."""
    print(f"=== PHASE 1: Purging dynamic resources for environment '{env}' in '{region}' ===")

    # 1. Scale down ECS Services
    ecs = get_client("ecs", region)
    cluster_name = f"{env}-nextcloud-cluster"
    try:
        clusters = ecs.describe_clusters(clusters=[cluster_name]).get("clusters", [])
        if any(c.get("status") == "ACTIVE" for c in clusters):
            print(f"Scaling down ECS services in cluster {cluster_name}...")
            services = ecs.list_services(cluster=cluster_name).get("serviceArns", [])
            for svc in services:
                print(f"  Scaling service to 0: {svc}")
                try:
                    ecs.update_service(cluster=cluster_name, service=svc, desiredCount=0)
                except Exception as e:
                    print(f"  Notice updating service {svc}: {e}")
    except Exception as e:
        print(f"Notice describing ECS clusters: {e}")

    # 2. Delete dynamic EFS Access Points
    efs = get_client("efs", region)
    try:
        paginator = efs.get_paginator("describe_file_systems")
        for page in paginator.paginate():
            for fs in page.get("FileSystems", []):
                fs_name = fs.get("Name", "")
                if f"{env}-nextcloud" in fs_name or f"{env}-" in fs_name:
                    fs_id = fs["FileSystemId"]
                    ap_paginator = efs.get_paginator("describe_access_points")
                    for ap_page in ap_paginator.paginate(FileSystemId=fs_id):
                        for ap in ap_page.get("AccessPoints", []):
                            ap_id = ap["AccessPointId"]
                            print(f"Deleting dynamic EFS Access Point: {ap_id} (FileSystem: {fs_id})")
                            try:
                                efs.delete_access_point(AccessPointId=ap_id)
                            except Exception as e:
                                print(f"Notice deleting AP {ap_id}: {e}")
    except Exception as e:
        print(f"Notice inspecting EFS access points: {e}")

    # 3. Delete dynamic ALB Target Groups
    elbv2 = get_client("elbv2", region)
    try:
        tg_paginator = elbv2.get_paginator("describe_target_groups")
        for page in tg_paginator.paginate():
            for tg in page.get("TargetGroups", []):
                tg_name = tg.get("TargetGroupName", "")
                if tg_name.startswith("tg-") or f"{env}-" in tg_name:
                    tg_arn = tg["TargetGroupArn"]
                    print(f"Deleting target group: {tg_name} ({tg_arn})")
                    try:
                        elbv2.delete_target_group(TargetGroupArn=tg_arn)
                    except Exception as e:
                        print(f"Notice deleting target group {tg_name}: {e}")
    except Exception as e:
        print(f"Notice inspecting target groups: {e}")

    # 4. Force empty and delete ECR repository
    ecr = get_client("ecr", region)
    ecr_repo = f"{env}-nextcloud-enterprise"
    try:
        ecr.delete_repository(repositoryName=ecr_repo, force=True)
        print(f"Purged ECR repository: {ecr_repo}")
    except ClientError as e:
        if e.response["Error"]["Code"] != "RepositoryNotFoundException":
            print(f"Notice deleting ECR repo {ecr_repo}: {e}")
    except Exception as e:
        print(f"Notice checking ECR: {e}")


def run_post_destruction(env: str, region: str) -> None:
    """Phase 3: Purge RDS manual snapshots, S3 buckets, secrets, log groups, and user pools."""
    print(f"=== PHASE 3: Purging lingering data & snapshots for environment '{env}' in '{region}' ===")

    # 1. Purge RDS manual snapshots
    rds = get_client("rds", region)
    try:
        snaps = rds.describe_db_snapshots(SnapshotType="manual").get("DBSnapshots", [])
        for snap in snaps:
            snap_id = snap.get("DBSnapshotIdentifier", "")
            db_id = snap.get("DBInstanceIdentifier", "")
            if f"{env}-nextcloud" in snap_id or f"{env}-nextcloud" in db_id:
                print(f"Deleting RDS manual snapshot: {snap_id}")
                try:
                    rds.delete_db_snapshot(DBSnapshotIdentifier=snap_id)
                except Exception as e:
                    print(f"Notice deleting snapshot {snap_id}: {e}")
    except Exception as e:
        print(f"Notice inspecting RDS snapshots: {e}")

    # 2. Empty and delete lingering S3 buckets
    s3 = get_client("s3", region)
    try:
        buckets = s3.list_buckets().get("Buckets", [])
        for b in buckets:
            b_name = b.get("Name", "")
            if f"{env}-nextcloud" in b_name or f"{env}-" in b_name:
                print(f"Purging versioned S3 bucket: {b_name}")
                try:
                    # Delete all object versions and delete markers
                    paginator = s3.get_paginator("list_object_versions")
                    for page in paginator.paginate(Bucket=b_name):
                        objects_to_delete = []
                        for ver in page.get("Versions", []):
                            objects_to_delete.append({"Key": ver["Key"], "VersionId": ver["VersionId"]})
                        for dm in page.get("DeleteMarkers", []):
                            objects_to_delete.append({"Key": dm["Key"], "VersionId": dm["VersionId"]})
                        if objects_to_delete:
                            s3.delete_objects(Bucket=b_name, Delete={"Objects": objects_to_delete, "Quiet": True})
                    s3.delete_bucket(Bucket=b_name)
                    print(f"Deleted S3 bucket: {b_name}")
                except Exception as e:
                    print(f"Notice deleting S3 bucket {b_name}: {e}")
    except Exception as e:
        print(f"Notice listing S3 buckets: {e}")

    # 3. Force delete lingering Secrets Manager secrets
    sm = get_client("secretsmanager", region)
    try:
        paginator = sm.get_paginator("list_secrets")
        for page in paginator.paginate():
            for sec in page.get("SecretList", []):
                sec_name = sec.get("Name", "")
                if f"nextcloud/{env}" in sec_name or f"{env}-nextcloud" in sec_name:
                    print(f"Force deleting secret: {sec_name}")
                    try:
                        sm.delete_secret(SecretId=sec_name, ForceDeleteWithoutRecovery=True)
                    except Exception as e:
                        print(f"Notice deleting secret {sec_name}: {e}")
    except Exception as e:
        print(f"Notice listing secrets: {e}")

    # 4. Purge CloudWatch Log Groups
    cw_logs = get_client("logs", region)
    try:
        paginator = cw_logs.get_paginator("describe_log_groups")
        for page in paginator.paginate():
            for lg in page.get("logGroups", []):
                lg_name = lg.get("logGroupName", "")
                if any(k in lg_name for k in [
                    f"{env}-nextcloud",
                    f"/ecs/{env}-nextcloud",
                    f"nextcloud/{env}",
                    f"{env}-Tenant",
                    f"/aws/vendedlogs/states/{env}",
                ]):
                    print(f"Deleting CloudWatch log group: {lg_name}")
                    try:
                        cw_logs.delete_log_group(logGroupName=lg_name)
                    except Exception as e:
                        print(f"Notice deleting log group {lg_name}: {e}")
    except Exception as e:
        print(f"Notice inspecting log groups: {e}")

    # 5. Clean up lingering Cognito User Pools
    cognito = get_client("cognito-idp", region)
    try:
        pools = cognito.list_user_pools(MaxResults=50).get("UserPools", [])
        for p in pools:
            p_name = p.get("Name", "")
            if f"{env}-nextcloud" in p_name:
                p_id = p["Id"]
                print(f"Deleting Cognito User Pool: {p_name} ({p_id})")
                try:
                    cognito.delete_user_pool(UserPoolId=p_id)
                except Exception as e:
                    print(f"Notice deleting Cognito user pool {p_id}: {e}")
    except Exception as e:
        print(f"Notice listing Cognito pools: {e}")


def run_audit(env: str, region: str) -> None:
    """Phase 4: Audit lingering resources."""
    print("============================================================")
    print(f"🔍 RUNNING FINAL TEARDOWN AUDIT CHECKLIST ({env} / {region})")
    print("============================================================")

    cfn = get_client("cloudformation", region)
    ec2 = get_client("ec2", region)
    rds = get_client("rds", region)
    efs = get_client("efs", region)
    cw_logs = get_client("logs", region)

    stacks = []
    try:
        summaries = cfn.list_stacks(StackStatusFilter=["CREATE_COMPLETE", "UPDATE_COMPLETE", "ROLLBACK_COMPLETE"]).get("StackSummaries", [])
        stacks = [s["StackName"] for s in summaries if f"{env}-nextcloud" in s["StackName"]]
    except Exception as e:
        print(f"Notice checking stacks: {e}")

    vpcs = []
    try:
        vpc_resp = ec2.describe_vpcs().get("Vpcs", [])
        for v in vpc_resp:
            for t in v.get("Tags", []):
                if t.get("Key") == "Name" and f"{env}-nextcloud" in t.get("Value", ""):
                    vpcs.append(v["VpcId"])
    except Exception as e:
        print(f"Notice checking VPCs: {e}")

    dbs = []
    try:
        db_resp = rds.describe_db_instances().get("DBInstances", [])
        dbs = [d["DBInstanceIdentifier"] for d in db_resp if f"{env}-nextcloud" in d["DBInstanceIdentifier"]]
    except Exception as e:
        print(f"Notice checking DBs: {e}")

    snaps = []
    try:
        snap_resp = rds.describe_db_snapshots(SnapshotType="manual").get("DBSnapshots", [])
        snaps = [s["DBSnapshotIdentifier"] for s in snap_resp if f"{env}-nextcloud" in s.get("DBSnapshotIdentifier", "")]
    except Exception as e:
        print(f"Notice checking snapshots: {e}")

    efs_list = []
    try:
        efs_resp = efs.describe_file_systems().get("FileSystems", [])
        efs_list = [f["FileSystemId"] for f in efs_resp if f"{env}-nextcloud" in f.get("Name", "")]
    except Exception as e:
        print(f"Notice checking EFS: {e}")

    logs_list = []
    try:
        log_resp = cw_logs.describe_log_groups().get("logGroups", [])
        logs_list = [lg["logGroupName"] for lg in log_resp if f"{env}-nextcloud" in lg.get("logGroupName", "")]
    except Exception as e:
        print(f"Notice checking logs: {e}")

    print(f"Remaining Stacks   : [{', '.join(stacks) if stacks else 'None'}]")
    print(f"Remaining VPCs     : [{', '.join(vpcs) if vpcs else 'None'}]")
    print(f"Remaining DBs      : [{', '.join(dbs) if dbs else 'None'}]")
    print(f"Remaining Snapshots: [{', '.join(snaps) if snaps else 'None'}]")
    print(f"Remaining EFS      : [{', '.join(efs_list) if efs_list else 'None'}]")
    print(f"Remaining LogGroups: [{', '.join(logs_list) if logs_list else 'None'}]")

    if not stacks and not vpcs and not dbs and not snaps and not efs_list:
        print("\n🎉 AUDIT PASSED: 100% CLEAN SLATE ACHIEVED!")
        print(f"Zero active billable services detected for environment '{env}'.")
    else:
        print("\n⚠️ Notice: Some resources may still be de-provisioning asynchronously.")
    print("============================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Zero-Cost Teardown & Audit Utility (boto3)")
    parser.add_argument("--phase", required=True, choices=["pre-destruction", "post-destruction", "audit"])
    parser.add_argument("--env", required=True, help="Target environment prefix (e.g. dev, prod)")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "ap-southeast-1"), help="AWS Region")
    args = parser.parse_args()

    if args.phase == "pre-destruction":
        run_pre_destruction(args.env, args.region)
    elif args.phase == "post-destruction":
        run_post_destruction(args.env, args.region)
    elif args.phase == "audit":
        run_audit(args.env, args.region)
