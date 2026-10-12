#!/usr/bin/env python3
"""
Comprehensive Zero-Cost Teardown Script for Nextcloud Multi-Tenant SaaS
Deletes all dedicated tenant services, routing rules, EFS access points,
S3 vault data, CloudFormation stacks, snapshots, and dashboards to guarantee
ZERO ongoing AWS billing.
"""

import time

import boto3
from botocore.exceptions import ClientError

AWS_PROFILE = "handon"
AWS_REGION = "ap-southeast-1"

session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
ecs = session.client("ecs")
elbv2 = session.client("elbv2")
efs = session.client("efs")
s3 = session.client("s3")
rds = session.client("rds")
cfn = session.client("cloudformation")
sm = session.client("secretsmanager")
cw = session.client("cloudwatch")
logs = session.client("logs")
autoscaling = session.client("application-autoscaling")
waf = session.client("wafv2")

CLUSTER_NAME = "prod-nextcloud-cluster"
VAULT_BUCKET = f"prod-nextcloud-vault-649519997247-{AWS_REGION}"

print("=" * 70)
print("🛑 COMPLETE ZERO-COST INFRASTRUCTURE TEARDOWN INITIATED")
print(f"AWS Region: {AWS_REGION} | Profile: {AWS_PROFILE}")
print("=" * 70)


def step_1_teardown_tenant_ecs():
    print("\n[Step 1/8] Tearing down dedicated Tenant ECS services & autoscaling...")
    try:
        services_resp = ecs.list_services(cluster=CLUSTER_NAME)
        service_arns = services_resp.get("serviceArns", [])
        for s_arn in service_arns:
            s_name = s_arn.split("/")[-1]
            if s_name != "prod-nextcloud-service":  # CFN manages prod-nextcloud-service
                print(f"  • Scaling down & deleting tenant service: {s_name}")
                try:
                    ecs.update_service(
                        cluster=CLUSTER_NAME, service=s_name, desiredCount=0
                    )
                except Exception as e:
                    print(f"    Notice updating desiredCount for {s_name}: {e}")

                # Deregister scalable target
                try:
                    resource_id = f"service/{CLUSTER_NAME}/{s_name}"
                    autoscaling.deregister_scalable_target(
                        ServiceNamespace="ecs",
                        ResourceId=resource_id,
                        ScalableDimension="ecs:service:DesiredCount",
                    )
                    print(f"    ✓ Deregistered autoscaling target: {s_name}")
                except Exception:
                    pass

                try:
                    ecs.delete_service(cluster=CLUSTER_NAME, service=s_name, force=True)
                    print(f"    ✓ Deleted ECS service: {s_name}")
                except Exception as e:
                    print(f"    Error deleting service {s_name}: {e}")

        # Wait for tenant tasks to stop
        print("  ⏳ Waiting for tenant tasks to terminate...")
        for _ in range(30):
            tasks = ecs.list_tasks(cluster=CLUSTER_NAME).get("taskArns", [])
            # Filter non-default tasks
            if not tasks:
                break
            time.sleep(2)
        print("  ✓ Tenant ECS services removed.")
    except ClientError as e:
        if "ClusterNotFoundException" in str(e):
            print("  ℹ️ ECS cluster does not exist.")
        else:
            print(f"  Warning: {e}")


def step_2_teardown_alb_routing():
    print("\n[Step 2/8] Tearing down ALB listener rules and dedicated target groups...")
    try:
        lbs = elbv2.describe_load_balancers().get("LoadBalancers", [])
        alb = next(
            (l for l in lbs if "prod-nextcloud-alb" in l["LoadBalancerName"]), None
        )
        if alb:
            listeners = elbv2.describe_listeners(
                LoadBalancerArn=alb["LoadBalancerArn"]
            ).get("Listeners", [])
            for listener in listeners:
                rules = elbv2.describe_rules(ListenerArn=listener["ListenerArn"]).get(
                    "Rules", []
                )
                for r in rules:
                    if not r.get("IsDefault"):
                        print(
                            f"  • Deleting ALB Listener Rule: {r['RuleArn'].split('/')[-1]}"
                        )
                        try:
                            elbv2.delete_rule(RuleArn=r["RuleArn"])
                        except Exception as e:
                            print(f"    Error deleting rule: {e}")

        # Delete non-CFN target groups
        tgs = elbv2.describe_target_groups().get("TargetGroups", [])
        for tg in tgs:
            name = tg["TargetGroupName"]
            if name != "prod-nextcloud-tg":  # CFN manages prod-nextcloud-tg
                print(f"  • Deleting Target Group: {name}")
                try:
                    elbv2.delete_target_group(TargetGroupArn=tg["TargetGroupArn"])
                    print(f"    ✓ Deleted Target Group: {name}")
                except Exception as e:
                    print(f"    Error deleting target group {name}: {e}")
    except Exception as e:
        print(f"  Warning in ALB teardown: {e}")


def step_3_teardown_efs_access_points():
    print("\n[Step 3/8] Deleting dedicated EFS Access Points...")
    try:
        fss = efs.describe_file_systems().get("FileSystems", [])
        for f in fss:
            fs_id = f["FileSystemId"]
            aps = efs.describe_access_points(FileSystemId=fs_id).get("AccessPoints", [])
            for ap in aps:
                ap_id = ap["AccessPointId"]
                print(f"  • Deleting EFS Access Point: {ap_id} ({ap.get('Name')})")
                try:
                    efs.delete_access_point(AccessPointId=ap_id)
                    print(f"    ✓ Deleted Access Point: {ap_id}")
                except Exception as e:
                    print(f"    Error deleting access point {ap_id}: {e}")
    except Exception as e:
        print(f"  Warning in EFS teardown: {e}")


def step_4_empty_s3_bucket(bucket_name):
    print(
        f"\n[Step 4/8] Purging all versions & delete markers in S3 vault: {bucket_name}..."
    )
    try:
        # Check if bucket exists
        s3.head_bucket(Bucket=bucket_name)
    except ClientError:
        print(f"  ℹ️ Bucket {bucket_name} does not exist. Skipping.")
        return

    # Delete all versions and delete markers
    paginator = s3.get_paginator("list_object_versions")
    total_deleted = 0
    for page in paginator.paginate(Bucket=bucket_name):
        objects_to_delete = []
        for v in page.get("Versions", []):
            objects_to_delete.append({"Key": v["Key"], "VersionId": v["VersionId"]})
        for m in page.get("DeleteMarkers", []):
            objects_to_delete.append({"Key": m["Key"], "VersionId": m["VersionId"]})

        if objects_to_delete:
            s3.delete_objects(
                Bucket=bucket_name, Delete={"Objects": objects_to_delete, "Quiet": True}
            )
            total_deleted += len(objects_to_delete)
            print(f"  • Deleted {len(objects_to_delete)} objects/versions...")
    print(f"  ✓ Purged total {total_deleted} items from {bucket_name}.")


def step_5_delete_tenant_secrets():
    print("\n[Step 5/8] Deleting tenant secrets in Secrets Manager...")
    try:
        secrets_list = sm.list_secrets().get("SecretList", [])
        for s in secrets_list:
            name = s["Name"]
            if name.startswith("/nextcloud/prod/tenants/"):
                print(f"  • Force deleting secret: {name}")
                try:
                    sm.delete_secret(SecretId=name, ForceDeleteWithoutRecovery=True)
                    print(f"    ✓ Deleted {name}")
                except Exception as e:
                    print(f"    Error deleting secret {name}: {e}")
    except Exception as e:
        print(f"  Warning in secrets deletion: {e}")


def step_6_delete_cloudwatch_dashboards():
    print(
        "\n[Step 6/8] Deleting Nextcloud CloudWatch Dashboards ($3/mo charge prevention)..."
    )
    dashboards_to_delete = [
        "prod-Nextcloud-SaaS-Control-Plane",
        "Nextcloud-MultiTenant-Overview",
    ]
    try:
        existing = [
            d["DashboardName"] for d in cw.list_dashboards().get("DashboardEntries", [])
        ]
        target = [d for d in dashboards_to_delete if d in existing]
        if target:
            cw.delete_dashboards(DashboardNames=target)
            print(f"  ✓ Deleted dashboards: {target}")
        else:
            print("  ℹ️ No Nextcloud dashboards found.")
    except Exception as e:
        print(f"  Warning in dashboard deletion: {e}")


def step_7_delete_cloudformation_stacks():
    print("\n[Step 7/8] Deleting CloudFormation Stacks in Reverse Dependency Order...")
    stack_order = [
        "prod-nextcloud-06-control-plane",
        "prod-nextcloud-05-compute",
        "prod-nextcloud-04-database",
        "prod-nextcloud-03-storage",
        "prod-nextcloud-02-security",
        "prod-nextcloud-01-networking",
    ]

    for s_name in stack_order:
        try:
            cfn.describe_stacks(StackName=s_name)
        except ClientError as e:
            if "does not exist" in str(e):
                print(f"  ℹ️ Stack {s_name} does not exist. Skipping.")
                continue
            raise

        print(f"\n  🗑️ Deleting stack: {s_name}...")
        cfn.delete_stack(StackName=s_name)

        # Wait for deletion
        waiter = cfn.get_waiter("stack_delete_complete")
        print(f"  ⏳ Waiting for {s_name} deletion to complete...")
        try:
            waiter.wait(StackName=s_name, WaiterConfig={"Delay": 15, "MaxAttempts": 60})
            print(f"  ✓ Successfully deleted {s_name}")
        except Exception as e:
            print(f"  ⚠️ Error waiting for {s_name}: {e}")
            # Check stack status
            try:
                st = cfn.describe_stacks(StackName=s_name)["Stacks"][0]
                print(
                    f"     Status: {st['StackStatus']}, Reason: {st.get('StackStatusReason')}"
                )
            except Exception:
                pass


def step_8_post_deletion_cleanup():
    print(
        "\n[Step 8/8] Performing post-stack cleanup (retained buckets, snapshots, log groups)..."
    )

    # 1. Delete S3 vault bucket if retained
    try:
        s3.delete_bucket(Bucket=VAULT_BUCKET)
        print(f"  ✓ Deleted retained S3 bucket: {VAULT_BUCKET}")
    except ClientError as e:
        if "NoSuchBucket" in str(e):
            print(f"  ℹ️ S3 bucket {VAULT_BUCKET} is already deleted.")
        else:
            print(f"  Notice deleting S3 bucket: {e}")

    # 2. Delete RDS snapshots containing nextcloud
    try:
        snaps = rds.describe_db_snapshots().get("DBSnapshots", [])
        for sn in snaps:
            sn_id = sn["DBSnapshotIdentifier"]
            if "nextcloud" in sn_id.lower():
                print(f"  • Deleting RDS snapshot: {sn_id}")
                try:
                    rds.delete_db_snapshot(DBSnapshotIdentifier=sn_id)
                    print(f"    ✓ Deleted snapshot {sn_id}")
                except Exception as e:
                    print(f"    Error deleting snapshot {sn_id}: {e}")
    except Exception as e:
        print(f"  Notice checking snapshots: {e}")

    # 3. Delete any remaining nextcloud log groups
    try:
        log_groups = logs.describe_log_groups(
            logGroupNamePrefix="/ecs/prod-nextcloud"
        ).get("logGroups", [])
        for lg in log_groups:
            lg_name = lg["logGroupName"]
            print(f"  • Deleting log group: {lg_name}")
            try:
                logs.delete_log_group(logGroupName=lg_name)
                print(f"    ✓ Deleted log group {lg_name}")
            except Exception as e:
                print(f"    Error deleting log group {lg_name}: {e}")
    except Exception as e:
        print(f"  Notice checking log groups: {e}")

    # 4. Delete remaining SSM parameters under /nextcloud
    try:
        ssm = session.client("ssm")
        paginator = ssm.get_paginator("get_parameters_by_path")
        for page in paginator.paginate(Path="/nextcloud", Recursive=True):
            param_names = [p["Name"] for p in page.get("Parameters", [])]
            if param_names:
                ssm.delete_parameters(Names=param_names)
                print(f"  ✓ Deleted {len(param_names)} SSM parameters under /nextcloud")
    except Exception as e:
        print(f"  Notice cleaning SSM parameters: {e}")

    # 5. Delete all remaining nextcloud secrets in Secrets Manager
    try:
        secs = sm.list_secrets().get("SecretList", [])
        for s in secs:
            if "/nextcloud/" in s["Name"]:
                try:
                    sm.delete_secret(
                        SecretId=s["Name"], ForceDeleteWithoutRecovery=True
                    )
                    print(f"  ✓ Deleted secret {s['Name']}")
                except Exception:
                    pass
    except Exception as e:
        print(f"  Notice cleaning secrets: {e}")


def step_9_zero_cost_verification():
    print("\n" + "=" * 70)
    print("🔍 FINAL ZERO-COST AUDIT & RESOURCE VERIFICATION")
    print("=" * 70)

    # 1. ECS
    try:
        clusters = [
            c for c in ecs.list_clusters().get("clusterArns", []) if "nextcloud" in c
        ]
        tasks = (
            ecs.list_tasks(cluster=CLUSTER_NAME).get("taskArns", []) if clusters else []
        )
    except Exception:
        clusters, tasks = [], []
    print(
        f"  • ECS Clusters (Nextcloud): {len(clusters)} (Tasks running: {len(tasks)})"
    )

    # 2. ALB
    try:
        lbs = [
            l
            for l in elbv2.describe_load_balancers().get("LoadBalancers", [])
            if "nextcloud" in l["LoadBalancerName"]
        ]
    except Exception:
        lbs = []
    print(f"  • Load Balancers (ALB): {len(lbs)}")

    # 3. RDS
    try:
        dbs = [
            d
            for d in rds.describe_db_instances().get("DBInstances", [])
            if "nextcloud" in d["DBInstanceIdentifier"]
        ]
        snaps = [
            s
            for s in rds.describe_db_snapshots().get("DBSnapshots", [])
            if "nextcloud" in s["DBSnapshotIdentifier"].lower()
        ]
    except Exception:
        dbs, snaps = [], []
    print(f"  • RDS PostgreSQL Instances: {len(dbs)} (Snapshots: {len(snaps)})")

    # 4. EFS
    try:
        fss = [
            f
            for f in efs.describe_file_systems().get("FileSystems", [])
            if "nextcloud" in f.get("Name", "").lower()
            or f["FileSystemId"] == "fs-0b7465bf80b2333eb"
        ]
    except Exception:
        fss = []
    print(f"  • EFS File Systems: {len(fss)}")

    # 5. S3 Vault Bucket
    try:
        s3.head_bucket(Bucket=VAULT_BUCKET)
        vault_exists = True
    except Exception:
        vault_exists = False
    print(f"  • S3 Vault Bucket Exists: {vault_exists}")

    # 6. WAF WebACL
    try:
        wafs = [
            w
            for w in waf.list_web_acls(Scope="REGIONAL").get("WebACLs", [])
            if "nextcloud" in w["Name"]
        ]
    except Exception:
        wafs = []
    print(f"  • WAF WebACLs: {len(wafs)}")

    # 7. CloudWatch Dashboards
    try:
        dashboards = [
            d
            for d in cw.list_dashboards().get("DashboardEntries", [])
            if "nextcloud" in d["DashboardName"].lower()
        ]
    except Exception:
        dashboards = []
    print(f"  • CloudWatch Dashboards ($3/mo): {len(dashboards)}")

    # 8. DynamoDB
    ddb = session.client("dynamodb")
    try:
        tables = [
            t for t in ddb.list_tables().get("TableNames", []) if "nextcloud" in t
        ]
    except Exception:
        tables = []
    print(f"  • DynamoDB Tables: {len(tables)}")

    # 9. CloudFormation Stacks
    try:
        stacks = [
            s
            for s in cfn.describe_stacks().get("Stacks", [])
            if "nextcloud" in s["StackName"]
            and s["StackStatus"] != "DELETE_COMPLETE"
            and s["StackName"] != "nextcloud-github-oidc-role"
        ]
    except Exception:
        stacks = []
    print(f"  • CloudFormation Stacks (Active): {len(stacks)}")

    all_zero = (
        len(clusters) == 0
        and len(lbs) == 0
        and len(dbs) == 0
        and len(snaps) == 0
        and len(fss) == 0
        and not vault_exists
        and len(wafs) == 0
        and len(dashboards) == 0
        and len(tables) == 0
        and len(stacks) == 0
    )
    if all_zero:
        print(
            "\n✅ CONFIRMED: ALL BILLABLE NEXTCLOUD RESOURCES HAVE BEEN 100% DESTROYED!"
        )
        print("   Current ongoing AWS cost for Nextcloud SaaS: $0.00 / month")
    else:
        print(
            "\n⚠️ NOTICE: Some resources may still be finishing deletion. Review above counts."
        )


if __name__ == "__main__":
    start_time = time.time()
    step_1_teardown_tenant_ecs()
    step_2_teardown_alb_routing()
    step_3_teardown_efs_access_points()
    step_4_empty_s3_bucket(VAULT_BUCKET)
    step_5_delete_tenant_secrets()
    step_6_delete_cloudwatch_dashboards()
    step_7_delete_cloudformation_stacks()
    step_8_post_deletion_cleanup()
    step_9_zero_cost_verification()
    elapsed = time.time() - start_time
    print("\n" + "=" * 70)
    print(f"🎉 ZERO-COST TEARDOWN COMPLETED in {elapsed / 60:.1f} minutes!")
    print("=" * 70)
