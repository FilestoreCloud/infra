# Module 05: Compute & Application Layer

## Overview

Deploys the core scalable ingress and compute platform for Nextcloud Multi-Tenant SaaS on AWS:

- **Amazon ECS Fargate Cluster:** Serverless container cluster hosting the default platform service as well as independent dedicated tenant containers provisioned dynamically via the Super Admin Console and Control Plane.
- **Dual-Container Task Architecture:** Runs Nextcloud 30 Apache alongside a local LiteLLM Bedrock Bridge sidecar proxying Claude 3.5 Sonnet on Amazon Bedrock.
- **Private Subnet Placement:** ECS tasks are placed in private subnets with `AssignPublicIp: DISABLED` and access AWS services (ECR, CloudWatch, Secrets Manager, EFS) via VPC Interface Endpoints without requiring public IP assignments or internet gateways.
- **Amazon ECR Golden Image Repository:** Provisions `${EnvironmentName}-nextcloud-enterprise` with automated vulnerability scanning on push.
- **SSM Parameter Store Ingress Exports:** Automatically exports `alb-https-listener-arn`, `alb-dns-name`, `ecs-cluster-name`, and IAM execution role ARNs to enable independent tenant container deployment without stack lock-in.

---

## Task Definition: Dual-Container Architecture & EFS Mount

```
┌─────────────────────────────────────────────────────────────────┐
│                 AWS Fargate Task (awsvpc network)               │
│                                                                 │
│   ┌───────────────────────────┐     ┌─────────────────────────┐ │
│   │   Nextcloud Core App      │     │  LiteLLM Sidecar Proxy  │ │
│   │   (Port 80)               │────▶│  (Port 4000)            │ │
│   │   - Apache / PHP 8.2      │     │  - OpenAI Bridge        │ │
│   │   - EFS Config (/config)  │     │  - AWS SigV4 Auth       │ │
│   │   - S3 Primary ObjectStore│     └────────────┬────────────┘ │
│   │   - APCu Local Cache      │                  │              │
│   └──────┬─────────────┬──────┘                  │              │
└──────────┼─────────────┼─────────────────────────┼──────────────┘
           │             │                         │
           │ NFS 2049    │ (PostgreSQL 5432)       │ (boto3 / SigV4)
           ▼             ▼                         ▼
      Amazon EFS    RDS PostgreSQL 16       Amazon Bedrock
      (/config)
```

1. **`nextcloud` Container:**
   - Image: `ContainerImage` parameter (defaults to official image or your ECR Golden Image).
   - EFS Mount: `/var/www/html/config` mounted from Amazon EFS via Access Point (`/tenants/default/config`, POSIX UID/GID 33:33).
   - Health Check: `curl -f http://localhost/status.php` (Interval: 30s, Retries: 5).
   - Credentials: Automatically pulled from AWS Secrets Manager (`DBSecret`, `AdminSecret`, `LiteLLMSecret`).
2. **`litellm-sidecar` Container:**
   - Image: `ghcr.io/berriai/litellm:main-v1.49.5`.
   - Health Check: `curl -f http://localhost:4000/health/liveliness`.
   - Role: Translates OpenAI-compatible requests from the Nextcloud Assistant app into Amazon Bedrock SigV4 invocations.

---

## Resources Created

| Logical ID                 | Resource Type                                 | Description                                                                  |
| -------------------------- | --------------------------------------------- | ---------------------------------------------------------------------------- |
| `NextcloudECRRepository`   | `AWS::ECR::Repository`                        | Container image repository with Scan-on-Push enabled                         |
| `ApplicationLoadBalancer`  | `AWS::ElasticLoadBalancingV2::LoadBalancer`   | Public Application Load Balancer across Public Subnets 1 & 2                 |
| `ALBTargetGroup`           | `AWS::ElasticLoadBalancingV2::TargetGroup`    | Target group (port 80, IP target type, stickiness enabled, `/status.php`)    |
| `ALBListener`              | `AWS::ElasticLoadBalancingV2::Listener`       | Port 80 HTTP listener redirecting 301 to HTTPS 443                           |
| `ALBHTTPSListener`         | `AWS::ElasticLoadBalancingV2::Listener`       | Port 443 HTTPS listener with TLS 1.3 policy and ACM certificate              |
| `DevTenantHTTPSRoutingRule` | `AWS::ElasticLoadBalancingV2::ListenerRule`   | Dedicated Host header routing rule forwarding dev-tenant to target group      |
| `DevTenantHTTPRoutingRule`  | `AWS::ElasticLoadBalancingV2::ListenerRule`   | Fallback HTTP routing rule forwarding dev-tenant when TLS is not enabled     |
| `ECSCluster`               | `AWS::ECS::Cluster`                           | Amazon ECS cluster with Container Insights enabled                           |
| `CloudWatchLogGroup`       | `AWS::Logs::LogGroup`                         | Log group `/ecs/${EnvironmentName}-nextcloud` (30-day retention)             |
| `AdminSecret`              | `AWS::SecretsManager::Secret`                 | Stores Nextcloud super-admin credentials                                     |
| `LiteLLMSecret`            | `AWS::SecretsManager::Secret`                 | Generates rotatable 32-character internal API token for LiteLLM              |
| `ECSTaskExecutionRole`     | `AWS::IAM::Role`                              | Execution role for ECR image pull, CloudWatch logs, and Secrets Manager read |
| `ECSTaskRole`              | `AWS::IAM::Role`                              | Task role granting S3 Vault access and Amazon Bedrock model invocation       |
| `NextcloudTaskDefinition`  | `AWS::ECS::TaskDefinition`                    | Fargate dual-container task definition (Nextcloud + LiteLLM sidecar)         |
| `ECSService`               | `AWS::ECS::Service`                           | ECS service with circuit breaker rollback and 1–6 task capacity              |
| `ECSAutoScalingTarget`     | `AWS::ApplicationAutoScaling::ScalableTarget` | Auto-scaling target for ECS service (Min: 1, Max: 6)                         |
| `ECSAutoScalingPolicyCPU`  | `AWS::ApplicationAutoScaling::ScalingPolicy`  | Target tracking scaling policy maintaining 70% average CPU                   |

---

## Parameters

| Parameter                 | Type                          | Default                    | Description                                                |
| ------------------------- | ----------------------------- | -------------------------- | ---------------------------------------------------------- |
| `EnvironmentName`         | String                        | `prod`                     | Environment prefix (`dev`, `staging`, `prod`)              |
| `VpcId`                   | `AWS::EC2::VPC::Id`           | -                          | Primary VPC ID (from Module 01)                            |
| `PublicSubnet1Id`         | `AWS::EC2::Subnet::Id`        | -                          | Public Subnet 1 ID (from Module 01)                        |
| `PublicSubnet2Id`         | `AWS::EC2::Subnet::Id`        | -                          | Public Subnet 2 ID (from Module 01)                        |
| `ALBSecurityGroupId`      | `AWS::EC2::SecurityGroup::Id` | -                          | ALB Security Group ID (from Module 02)                     |
| `ECSSecurityGroupId`      | `AWS::EC2::SecurityGroup::Id` | -                          | ECS Security Group ID (from Module 02)                     |
| `S3VaultBucketName`       | String                        | -                          | S3 Vault Bucket Name (from Module 03)                      |
| `S3VaultBucketArn`        | String                        | -                          | S3 Vault Bucket ARN (from Module 03)                       |
| `DatabaseEndpoint`        | String                        | -                          | RDS PostgreSQL Endpoint (from Module 04)                   |
| `DBSecretArn`             | String                        | -                          | Database Credentials Secret ARN (from Module 04)           |
| `AdminPassword`           | String                        | _(NoEcho)_                 | Initial super-admin password for Nextcloud                 |
| `TaskCpu`                 | String                        | `1024`                     | Fargate vCPU allocation (`512`, `1024`, `2048`, `4096`)    |
| `TaskMemory`              | String                        | `2048`                     | Fargate Memory allocation (`1024`, `2048`, `4096`, `8192`) |
| `DesiredCount`            | Number                        | `1`                        | Desired running task count                                 |
| `MaxCount`                | Number                        | `6`                        | Maximum tasks for auto-scaling                             |
| `EnableAIEngine`          | String                        | `true`                     | Enable Bedrock AI & Nextcloud Assistant                    |
| `ContainerImage`          | String                        | `nextcloud:30.0.17-apache` | Docker image URI                                           |
| `ACMCertificateArn`       | String                        | -                          | ACM TLS Certificate ARN for HTTPS listener                 |
| `EFSFileSystemId`         | String                        | `""`                       | EFS File System ID for Persistent Config (from Module 03)  |
| `EFSFileSystemArn`        | String                        | `""`                       | EFS File System ARN for IAM Role (from Module 03)          |
| `DefaultEFSAccessPointId` | String                        | `""`                       | EFS Access Point ID for Default Tenant (from Module 03)    |

---

## Inter-Module Contract & Discovery

### SSM Parameter Store

Published parameters:

- `/nextcloud/${EnvironmentName}/infra/alb-dns` ➔ ALB Public DNS address
- `/nextcloud/${EnvironmentName}/infra/ecs-cluster-name` ➔ ECS Cluster name
- `/nextcloud/${EnvironmentName}/infra/ecs-service-name` ➔ ECS Service name
- `/nextcloud/${EnvironmentName}/infra/ecs-task-role-arn` ➔ ECS Task Role ARN
- `/nextcloud/${EnvironmentName}/infra/ecs-task-execution-role-arn` ➔ Task Execution Role ARN
- `/nextcloud/${EnvironmentName}/app/admin-user` ➔ Initial Nextcloud admin username (`admin`)
- `/nextcloud/${EnvironmentName}/app/trusted-domains` ➔ Auto-configured trusted domains list
- `/nextcloud/${EnvironmentName}/ai/enabled` ➔ AI integration toggle status
- `/nextcloud/${EnvironmentName}/ai/bedrock-model-id` ➔ AWS Bedrock model identifier

### CloudFormation Exports

- `${EnvironmentName}-nextcloud-LoadBalancerURL`
- `${EnvironmentName}-nextcloud-LoadBalancerDNS`
- `${EnvironmentName}-nextcloud-LoadBalancerFullName`
- `${EnvironmentName}-nextcloud-TargetGroupFullName`
- `${EnvironmentName}-nextcloud-ALBHTTPSListenerArn`
- `${EnvironmentName}-nextcloud-ECSClusterName`
- `${EnvironmentName}-nextcloud-ECSServiceName`
- `${EnvironmentName}-nextcloud-ECSTaskExecutionRoleArn`
- `${EnvironmentName}-nextcloud-ECSTaskRoleArn`
- `${EnvironmentName}-nextcloud-ECRRepositoryUri`
- `${EnvironmentName}-nextcloud-AdminSecretArn`
- `${EnvironmentName}-nextcloud-LiteLLMSecretArn`

---

## Deployment CLI Example

```bash
aws cloudformation deploy \
  --template-file infra/modules/05-compute/template.yaml \
  --stack-name prod-nextcloud-05-compute \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
      EnvironmentName=prod \
      VpcId=$(aws ssm get-parameter --name "/nextcloud/prod/infra/vpc-id" --query "Parameter.Value" --output text) \
      PublicSubnet1Id=$(aws ssm get-parameter --name "/nextcloud/prod/infra/public-subnets" --query "Parameter.Value" --output text | cut -d',' -f1) \
      PublicSubnet2Id=$(aws ssm get-parameter --name "/nextcloud/prod/infra/public-subnets" --query "Parameter.Value" --output text | cut -d',' -f2) \
      ALBSecurityGroupId=$(aws ssm get-parameter --name "/nextcloud/prod/security/alb-sg-id" --query "Parameter.Value" --output text) \
      ECSSecurityGroupId=$(aws ssm get-parameter --name "/nextcloud/prod/security/ecs-sg-id" --query "Parameter.Value" --output text) \
      S3VaultBucketName=$(aws ssm get-parameter --name "/nextcloud/prod/infra/s3-vault-bucket" --query "Parameter.Value" --output text) \
      S3VaultBucketArn=$(aws ssm get-parameter --name "/nextcloud/prod/infra/s3-vault-bucket-arn" --query "Parameter.Value" --output text) \
      EFSFileSystemId=$(aws ssm get-parameter --name "/nextcloud/prod/infra/efs-id" --query "Parameter.Value" --output text) \
      EFSFileSystemArn=$(aws ssm get-parameter --name "/nextcloud/prod/infra/efs-id" --query "Parameter.Value" --output text | xargs -I {} aws efs describe-file-systems --file-system-id {} --query "FileSystems[0].FileSystemArn" --output text) \
      DefaultEFSAccessPointId=$(aws ssm get-parameter --name "/nextcloud/prod/infra/default-access-point-id" --query "Parameter.Value" --output text) \
      DatabaseEndpoint=$(aws ssm get-parameter --name "/nextcloud/prod/infra/db-endpoint" --query "Parameter.Value" --output text) \
      DBSecretArn=$(aws ssm get-parameter --name "/nextcloud/prod/infra/db-secret-arn" --query "Parameter.Value" --output text) \
      AdminPassword="<ADMIN_PASSWORD>" \
      ACMCertificateArn="arn:aws:acm:ap-southeast-1:123456789012:certificate/your-cert-id"
```
