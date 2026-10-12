import json
import os
import sys
import time
import boto3

tenant = sys.argv[1] if len(sys.argv) > 1 else "acme"

session = boto3.Session(
    profile_name=os.getenv("AWS_PROFILE"),
    region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
)
ecs = session.client("ecs")
sm = session.client("secretsmanager")
logs = session.client("logs")

secret_name = f"/nextcloud/prod/tenants/{tenant}/admin-credentials"
sec_str = sm.get_secret_value(SecretId=secret_name)["SecretString"]
creds = json.loads(sec_str)
admin_user = creds.get("username", "admin")
admin_pass = creds.get("password")

print("============================================================")
print(f"🔑 RESETTING NEXTCLOUD ADMIN PASSWORD FOR TENANT '{tenant}'")
print(f"Target User: {admin_user}")
print("Target Password: [CONFIGURED IN SECRETS MANAGER]")
print("============================================================")

# Command to ensure /var/www/html is populated and execute occ
cmd = (
    "cp -rn /usr/src/nextcloud/. /var/www/html/ && "
    "chown -R www-data:www-data /var/www/html && "
    f"su -s /bin/sh www-data -c 'php /var/www/html/occ status && "
    f'export OC_PASS="{admin_pass}" && '
    f"php /var/www/html/occ user:resetpassword --password-from-env {admin_user} || "
    f'php /var/www/html/occ user:add --password-from-env --display-name="Administrator" {admin_user}\''
)

res = ecs.run_task(
    cluster="prod-nextcloud-cluster",
    taskDefinition=f"prod-nextcloud-{tenant}",
    launchType="FARGATE",
    networkConfiguration={
        "awsvpcConfiguration": {
            "subnets": ["subnet-08096079734609710", "subnet-049b7e2945e7eddce"],
            "securityGroups": ["sg-020acf11e92c99ca4"],
            "assignPublicIp": "ENABLED",
        }
    },
    overrides={
        "containerOverrides": [
            {"name": "nextcloud", "command": [cmd]},
            {"name": "litellm-sidecar", "command": ["echo", "sidecar skipped"]},
        ]
    },
)

task_arn = res["tasks"][0]["taskArn"]
task_id = task_arn.split("/")[-1]
print(f"Task launched on ECS: {task_id}")
print("Waiting for task to execute...")

waiter = ecs.get_waiter("tasks_stopped")
waiter.wait(cluster="prod-nextcloud-cluster", tasks=[task_arn])
print("Task finished. Fetching CloudWatch logs...")

time.sleep(3)
stream_prefix = f"tenant-{tenant}/nextcloud/{task_id}"
streams = logs.describe_log_streams(
    logGroupName="/ecs/prod-nextcloud", logStreamNamePrefix=stream_prefix
)["logStreams"]

if streams:
    events = logs.get_log_events(
        logGroupName="/ecs/prod-nextcloud",
        logStreamName=streams[0]["logStreamName"],
        startFromHead=True,
    )["events"]
    print("\n--- OCC OUTPUT ---")
    for ev in events:
        print(ev["message"])
    print("-------------------\n")
else:
    print(f"No stream found for prefix {stream_prefix}")
