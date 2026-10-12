import os
import boto3

session = boto3.Session(
    profile_name=os.getenv("AWS_PROFILE"),
    region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
)
ecs = session.client("ecs")

CLUSTER_NAME = "prod-nextcloud-cluster"
TENANTS = ["acme", "marvel"]
AWS_REGION = "ap-southeast-1"

s3_vars = [
    {"name": "OBJECTSTORE_S3_REGION", "value": AWS_REGION},
    {"name": "OBJECTSTORE_S3_AUTOCREATE", "value": "false"},
    {"name": "OBJECTSTORE_S3_USEPATH_STYLE", "value": "false"},
    {"name": "OBJECTSTORE_S3_SSL", "value": "true"},
]

for tenant in TENANTS:
    family = f"prod-nextcloud-{tenant}"
    service_name = f"service-{tenant}"
    print("\n=======================================================")
    print(f"🚀 Updating Task Definition & Service for {tenant}...")
    print("=======================================================")

    # 1. Fetch current task definition
    td_resp = ecs.describe_task_definition(taskDefinition=family)
    td = td_resp["taskDefinition"]

    # Clean td for re-registration
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

    # Update environment variables in 'nextcloud' container
    for c in td["containerDefinitions"]:
        if c["name"] == "nextcloud":
            env_map = {e["name"]: e["value"] for e in c.get("environment", [])}
            for v in s3_vars:
                env_map[v["name"]] = v["value"]
            c["environment"] = [{"name": k, "value": v} for k, v in env_map.items()]
            print(f"  ✅ Added S3 configuration variables to container '{c['name']}'")

    # Register new revision
    new_td_resp = ecs.register_task_definition(**td)
    new_td_arn = new_td_resp["taskDefinition"]["taskDefinitionArn"]
    rev = new_td_resp["taskDefinition"]["revision"]
    print(f"  ✅ Registered new Task Definition: {family}:{rev} ({new_td_arn})")

    # Update ECS Service
    print(f"  ⚡ Updating ECS service {service_name} with {family}:{rev}...")
    ecs.update_service(
        cluster=CLUSTER_NAME,
        service=service_name,
        taskDefinition=new_td_arn,
        forceNewDeployment=True,
    )
    print(
        f"  ✅ Updated {service_name} to {family}:{rev} (force-new-deployment initiated)"
    )

print("\nAll tenant services updated!")
