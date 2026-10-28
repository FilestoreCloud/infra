#!/usr/bin/env python3
"""
Storix Platform Zero-Cost Teardown Automation
Natively tears down all AWS CloudFormation stacks, ECS resources, S3 versioned buckets,
EFS file systems, and CloudFront distributions in strict reverse-dependency order.
"""

import os
import sys
import time
import argparse
import boto3
from botocore.exceptions import ClientError


def get_client(service, region):
    return boto3.client(service, region_name=region)


def get_resource(service, region):
    return boto3.resource(service, region_name=region)


def empty_s3_bucket(bucket_name, region):
    s3_client = get_client("s3", region)
    s3_resource = get_resource("s3", region)
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ["NoSuchBucket", "404"]:
            return

    # 1. Remove bucket policy so nothing blocks deletion
    try:
        s3_client.delete_bucket_policy(Bucket=bucket_name)
    except Exception:
        pass

    # 2. Delete all versions and delete markers
    try:
        bucket = s3_resource.Bucket(bucket_name)
        bucket.object_versions.delete()
        print(f"  ✔ Emptied all objects and versions in S3 bucket: {bucket_name}")
    except Exception as e:
        print(f"  ⚠️ Warning emptying {bucket_name}: {e}")

    # 3. Attempt direct bucket deletion if retained
    try:
        s3_client.delete_bucket(Bucket=bucket_name)
        print(f"  ✔ Deleted S3 bucket: {bucket_name}")
    except Exception:
        pass


def empty_matching_s3_buckets(prefix, region):
    s3_client = get_client("s3", region)
    try:
        resp = s3_client.list_buckets()
        for b in resp.get("Buckets", []):
            name = b["Name"]
            if name.startswith(prefix):
                empty_s3_bucket(name, region)
    except Exception as e:
        print(f"  ⚠️ Warning listing S3 buckets: {e}")


def cleanup_ecs(cluster_name, region):
    ecs = get_client("ecs", region)
    try:
        services = ecs.list_services(cluster=cluster_name).get("serviceArns", [])
        for svc in services:
            print(f"  🛑 Scaling down and deleting ECS service: {svc}")
            try:
                ecs.update_service(cluster=cluster_name, service=svc, desiredCount=0)
                ecs.delete_service(cluster=cluster_name, service=svc, force=True)
            except Exception as se:
                print(f"     Warning deleting service {svc}: {se}")

        tasks = ecs.list_tasks(cluster=cluster_name).get("taskArns", [])
        for t in tasks:
            print(f"  🛑 Stopping task: {t}")
            try:
                ecs.stop_task(cluster=cluster_name, task=t)
            except Exception as te:
                print(f"     Warning stopping task {t}: {te}")

        time.sleep(5)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") != "ClusterNotFoundException":
            print(f"  ⚠️ ECS cluster cleanup warning: {e}")


def cleanup_efs(region):
    efs = get_client("efs", region)
    try:
        filesystems = efs.describe_file_systems().get("FileSystems", [])
        for fs in filesystems:
            fs_id = fs["FileSystemId"]
            name = fs.get("Name", "")
            if "nextcloud" in name or "storix" in name:
                print(f"  🔍 Inspecting EFS filesystem: {fs_id} ({name})")
                try:
                    mount_targets = efs.describe_mount_targets(FileSystemId=fs_id).get("MountTargets", [])
                    for mt in mount_targets:
                        mt_id = mt["MountTargetId"]
                        print(f"    Deleting mount target: {mt_id}")
                        efs.delete_mount_target(MountTargetId=mt_id)
                except Exception as mte:
                    print(f"    Mount target cleanup: {mte}")
    except Exception as e:
        print(f"  ⚠️ EFS check: {e}")


def get_failed_resources(cfn, stack_name):
    """Query CloudFormation describe_stack_resources to find resources currently in DELETE_FAILED."""
    try:
        resources = cfn.describe_stack_resources(StackName=stack_name).get("StackResources", [])
        failed = [
            r["LogicalResourceId"]
            for r in resources
            if r.get("ResourceStatus") == "DELETE_FAILED" and r["LogicalResourceId"] != stack_name
        ]
        return failed
    except Exception as e:
        print(f"  ⚠️ Could not query stack resources for {stack_name}: {e}")
        return []


def delete_stack_safely(cfn, stack_name, max_wait_mins=15):
    try:
        desc = cfn.describe_stacks(StackName=stack_name)["Stacks"][0]
        status = desc["StackStatus"]
        print(f"\n📦 Stack [{stack_name}] status: {status}")
    except ClientError as e:
        if "does not exist" in str(e):
            print(f"✔ Stack [{stack_name}] does not exist (already deleted).")
            return True
        print(f"⚠️ Error checking stack {stack_name}: {e}")
        return False

    failed_resources = get_failed_resources(cfn, stack_name)

    try:
        if status == "DELETE_FAILED" and failed_resources:
            print(f"  ⚠️ Stack is DELETE_FAILED. Deleting with RetainResources={failed_resources}...")
            cfn.delete_stack(StackName=stack_name, RetainResources=failed_resources)
        else:
            cfn.delete_stack(StackName=stack_name)
    except Exception as e:
        print(f"  ⚠️ Error sending delete request for {stack_name}: {e}")

    print(f"  ⏳ Waiting for [{stack_name}] deletion to complete...")
    waiter = cfn.get_waiter("stack_delete_complete")
    attempts = max(1, (max_wait_mins * 60) // 10)
    try:
        waiter.wait(StackName=stack_name, WaiterConfig={"Delay": 10, "MaxAttempts": attempts})
        print(f"  ✔ Stack [{stack_name}] deleted successfully.")
        return True
    except Exception as e:
        print(f"  ⚠️ Waiter reported: {e}")
        # Retry with dynamically discovered failed resources
        try:
            cur = cfn.describe_stacks(StackName=stack_name)["Stacks"][0]["StackStatus"]
            if cur == "DELETE_FAILED":
                failed = get_failed_resources(cfn, stack_name)
                if failed:
                    print(f"  Retrying deletion of [{stack_name}] with RetainResources={failed}...")
                    cfn.delete_stack(StackName=stack_name, RetainResources=failed)
                    waiter.wait(StackName=stack_name, WaiterConfig={"Delay": 10, "MaxAttempts": attempts})
                    print(f"  ✔ Stack [{stack_name}] deleted successfully after retaining.")
                    return True
                else:
                    print(f"  Retrying deletion of [{stack_name}] without retain resources...")
                    cfn.delete_stack(StackName=stack_name)
                    waiter.wait(StackName=stack_name, WaiterConfig={"Delay": 10, "MaxAttempts": attempts})
                    print(f"  ✔ Stack [{stack_name}] deleted successfully.")
                    return True
        except Exception as retry_err:
            print(f"  ⚠️ Retry failed: {retry_err}")
        return False


def teardown(env: str, region: str):
    print("\n" + "=" * 70)
    print(f"🔥 NATIVE STORIX ZERO-COST TEARDOWN — ENVIRONMENT: {env} (Region: {region})")
    print("=" * 70)

    cfn = get_client("cloudformation", region)

    # 1. Observability
    delete_stack_safely(cfn, f"{env}-nextcloud-07-observability")

    # 2. SuperAdmin Console & Assets
    empty_matching_s3_buckets(f"{env}-storix-admin-", region)
    empty_matching_s3_buckets(f"{env}-nextcloud-admin-", region)
    delete_stack_safely(cfn, f"{env}-nextcloud-06-superadmin")

    # 3. Compute (ECS + OpenSearch)
    cleanup_ecs(f"{env}-nextcloud-cluster", region)
    delete_stack_safely(cfn, f"{env}-nextcloud-05-compute", max_wait_mins=15)
    # Direct cleanup of ECS cluster if retained
    try:
        ecs = get_client("ecs", region)
        ecs.delete_cluster(cluster=f"{env}-nextcloud-cluster")
        print(f"  ✔ Deleted retained ECS cluster: {env}-nextcloud-cluster")
    except Exception:
        pass

    # 4. OpenSearch Domain
    delete_stack_safely(cfn, f"{env}-nextcloud-05-opensearch", max_wait_mins=20)

    # 5. Database (Aurora PostgreSQL)
    delete_stack_safely(cfn, f"{env}-nextcloud-04-database", max_wait_mins=20)

    # 6. Storage (S3 Data/Vault/Quarantine buckets + EFS)
    print("\n🧹 Purging S3 Buckets in Module 03-Storage...")
    empty_matching_s3_buckets(f"{env}-nextcloud-data-", region)
    empty_matching_s3_buckets(f"{env}-nextcloud-vault-", region)
    empty_matching_s3_buckets(f"{env}-storix-vault-", region)
    empty_matching_s3_buckets(f"{env}-storix-audit-vault-", region)
    empty_matching_s3_buckets(f"{env}-storix-quarantine-", region)
    cleanup_efs(region)
    delete_stack_safely(cfn, f"{env}-nextcloud-03-storage", max_wait_mins=15)

    # 7. Security (IAM & Security Groups)
    delete_stack_safely(cfn, f"{env}-nextcloud-02-security", max_wait_mins=10)

    # 8. Networking (VPC, Subnets, Gateways)
    delete_stack_safely(cfn, f"{env}-nextcloud-01-networking", max_wait_mins=10)

    # 9. Final Sweep Check
    print("\n" + "=" * 70)
    print("🔍 Final Stack Status Verification & Sweep")
    print("=" * 70)
    for attempt in range(3):
        try:
            resp = cfn.list_stacks(
                StackStatusFilter=[
                    "CREATE_COMPLETE",
                    "UPDATE_COMPLETE",
                    "ROLLBACK_COMPLETE",
                    "DELETE_FAILED",
                    "DELETE_IN_PROGRESS"
                ]
            )
            remaining = [
                s["StackName"]
                for s in resp.get("StackSummaries", [])
                if s["StackName"].startswith(f"{env}-nextcloud-")
            ]
            if not remaining:
                print(f"🎉 All {env} CloudFormation stacks are 100% cleanly deleted.")
                break
            print(f"⚠️ Remaining stacks detected on attempt {attempt + 1}: {remaining}")
            for rem in remaining:
                delete_stack_safely(cfn, rem, max_wait_mins=5)
        except Exception as e:
            print(f"Error during final sweep: {e}")
            break

    print("\nTeardown complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Storix Platform Teardown")
    parser.add_argument("--env", required=True, help="Environment (dev, prod)")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "ap-southeast-1"))
    args = parser.parse_args()

    teardown(args.env, args.region)
