import os
import sys
import time
import boto3

tenant = sys.argv[1] if len(sys.argv) > 1 else "acme"
occ_cmd = sys.argv[2] if len(sys.argv) > 2 else "status"

session = boto3.Session(
    profile_name=os.getenv("AWS_PROFILE"),
    region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
)
ecs = session.client("ecs")
logs = session.client("logs")
ssm = session.client("ssm")

subnets = ssm.get_parameter(Name="/nextcloud/prod/infra/public-subnets")["Parameter"][
    "Value"
].split(",")
ecs_sg = ssm.get_parameter(Name="/nextcloud/prod/security/ecs-sg-id")["Parameter"][
    "Value"
]

cmd_string = f"su -s /bin/sh www-data -c 'php /var/www/html/occ {occ_cmd}'"
print(f"Running occ on tenant '{tenant}': {occ_cmd}")

res = ecs.run_task(
    cluster="prod-nextcloud-cluster",
    taskDefinition=f"prod-nextcloud-{tenant}",
    launchType="FARGATE",
    networkConfiguration={
        "awsvpcConfiguration": {
            "subnets": subnets,
            "securityGroups": [ecs_sg],
            "assignPublicIp": "ENABLED",
        }
    },
    overrides={
        "containerOverrides": [
            {"name": "nextcloud", "command": [cmd_string]},
        ]
    },
)

task_arn = res["tasks"][0]["taskArn"]
task_id = task_arn.split("/")[-1]
print(f"Task launched: {task_id}. Waiting for completion...")

waiter = ecs.get_waiter("tasks_stopped")
waiter.wait(cluster="prod-nextcloud-cluster", tasks=[task_arn])
print("Task stopped. Fetching logs...")

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
    for ev in events:
        print(ev["message"])
else:
    print(f"No stream found for prefix {stream_prefix}")
