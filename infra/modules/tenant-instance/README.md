# Nextcloud Multi-Tenant SaaS — Module: Tenant Instance

## Overview

The `tenant-instance` CloudFormation template enables declarative, automated provisioning of a **fully isolated Nextcloud tenant runtime (Container-per-Tenant)** on top of the shared platform baseline.

## Architectural Isolation Boundaries

Each deployed tenant instance receives:

- **Dedicated Fargate Container:** Isolated ECS Task Definition and Service (`service-<tenant_id>`) with its own PHP-FPM / Apache runtime and memory space.
- **Dedicated EFS Access Point:** Mounts `/tenants/<tenant_id>/config` to `/var/www/html/config`, strictly siloing Nextcloud configuration, installed apps, and instance encryption keys.
- **Dedicated Database:** Points to `nc_<tenant_id>` on the shared RDS PostgreSQL cluster.
- **Dedicated ALB Ingress:** ALB Target Group (`tg-<tenant_id>`) mapped to the tenant's custom domain via ALB Host-Header routing rule (`<tenant_id>.yourdomain.com`).
- **FinOps Task Scaling:** Scaling `DesiredCount` between `1` (Active) and `0` (Suspended) immediately eliminates compute costs while preserving all state.

## Parameters

| Parameter              | Type   | Default    | Description                                                      |
| ---------------------- | ------ | ---------- | ---------------------------------------------------------------- |
| `TenantId`             | String | _Required_ | Lowercase alphanumeric tenant identifier (e.g. `acme`, `marvel`) |
| `TenantDomain`         | String | _Required_ | Dedicated domain/subdomain (e.g. `acme.png261.dev`)              |
| `AdminPassword`        | String | _Required_ | Initial admin password for this dedicated instance               |
| `TaskCpu`              | String | `512`      | CPU units for Fargate task (512 = 0.5 vCPU)                      |
| `TaskMemory`           | String | `1024`     | Memory in MB for Fargate task                                    |
| `DesiredCount`         | Number | `1`        | Desired tasks: 1 for active, 0 for suspended                     |
| `EnableAutoScaling`    | String | `true`     | Enable Application Auto Scaling (`true` / `false`)               |
| `MinTaskCount`         | Number | `1`        | Minimum task count for auto-scaling                              |
| `MaxTaskCount`         | Number | `4`        | Maximum task count (scales out on CPU load spikes)               |
| `TargetCPUUtilization` | Number | `70`       | Target average CPU utilization percentage (Target Tracking)      |
| `RulePriority`         | Number | `100`      | Priority on the ALB HTTPS listener                               |

## Deployment Example

```bash
aws cloudformation deploy \
  --template-file infra/modules/tenant-instance/template.yaml \
  --stack-name prod-nextcloud-tenant-acme \
  --parameter-overrides \
    TenantId=acme \
    TenantDomain=acme.png261.dev \
    AdminPassword='<ADMIN_PASSWORD>' \
    VpcId=$(aws ssm get-parameter --name /nextcloud/prod/infra/vpc-id --query Parameter.Value --output text) \
    PublicSubnet1Id=$(aws ssm get-parameter --name /nextcloud/prod/infra/public-subnets --query Parameter.Value --output text | cut -d',' -f1) \
    PublicSubnet2Id=$(aws ssm get-parameter --name /nextcloud/prod/infra/public-subnets --query Parameter.Value --output text | cut -d',' -f2) \
    ECSSecurityGroupId=$(aws ssm get-parameter --name /nextcloud/prod/security/ecs-sg-id --query Parameter.Value --output text) \
    ECSClusterName=$(aws ssm get-parameter --name /nextcloud/prod/infra/ecs-cluster-name --query Parameter.Value --output text) \
    ECSTaskRoleArn=$(aws ssm get-parameter --name /nextcloud/prod/infra/ecs-task-role-arn --query Parameter.Value --output text) \
    ECSTaskExecutionRoleArn=$(aws ssm get-parameter --name /nextcloud/prod/infra/ecs-task-execution-role-arn --query Parameter.Value --output text) \
    ALBHTTPSListenerArn=$(aws ssm get-parameter --name /nextcloud/prod/infra/alb-https-listener-arn --query Parameter.Value --output text) \
    EFSFileSystemId=$(aws ssm get-parameter --name /nextcloud/prod/infra/efs-id --query Parameter.Value --output text) \
    DatabaseEndpoint=$(aws ssm get-parameter --name /nextcloud/prod/infra/db-endpoint --query Parameter.Value --output text) \
    DBSecretArn=$(aws ssm get-parameter --name /nextcloud/prod/infra/db-secret-arn --query Parameter.Value --output text) \
    S3VaultBucketName=$(aws ssm get-parameter --name /nextcloud/prod/infra/s3-vault-bucket --query Parameter.Value --output text)
```
