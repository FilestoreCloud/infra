# Module 02: Security & Network Access Control

## Overview

Deploys defense-in-depth AWS Security Groups enforcing the principle of least privilege and zero-trust segmentation across the multi-tenant SaaS architecture.

Traffic is strictly chained across tiers:

1. **Public Ingress (ALB):** Accepts public web traffic on ports 80 (HTTP) and 443 (HTTPS).
2. **Compute Tier (ECS Fargate):** Inbound traffic on port 80 is strictly locked to the ALB Security Group. All public internet direct access is blocked. Outbound access allows direct communication with AWS APIs (Bedrock, ECR, CloudWatch, Secrets Manager) and external federated Nextcloud servers.
3. **Storage Tier (Amazon EFS):** Inbound NFS traffic on port 2049 is strictly locked to the ECS Security Group. External access to the shared configuration file system is blocked.
4. **Data Tier (RDS PostgreSQL):** Inbound traffic on port 5432 is strictly locked to the ECS Security Group. Direct external access to the database is blocked.

---

## Security Group Chaining Matrix

```
┌─────────────────────────────────┐
│     Internet / Client Traffic   │
└────────────────┬────────────────┘
                 │ TCP 80 / 443 (Public)
                 ▼
┌─────────────────────────────────┐
│       ALBSecurityGroup          │
└────────────────┬────────────────┘
                 │ TCP 80 (Source: ALBSecurityGroup only)
                 ▼
┌─────────────────────────────────┐
│       ECSSecurityGroup          │
└────────┬───────────────┬────────┘
         │               │
         │ TCP 2049      │ TCP 5432
         │ (NFS)         │ (PostgreSQL)
         ▼               ▼
┌─────────────────┐  ┌─────────────────┐
│ EFSSecurityGroup│  │ DBSecurityGroup │
└─────────────────┘  └─────────────────┘
```

---

## Resources Created

| Logical ID            | Resource Type             | Description                                                                     |
| --------------------- | ------------------------- | ------------------------------------------------------------------------------- |
| `ALBSecurityGroup`    | `AWS::EC2::SecurityGroup` | Inbound HTTP (80) & HTTPS (443) from `0.0.0.0/0`, all egress                    |
| `ECSSecurityGroup`    | `AWS::EC2::SecurityGroup` | Inbound HTTP (80) restricted strictly to `ALBSecurityGroup`, all egress         |
| `EFSSecurityGroup`    | `AWS::EC2::SecurityGroup` | Inbound NFS (2049) restricted strictly to `ECSSecurityGroup`, all egress        |
| `DBSecurityGroup`     | `AWS::EC2::SecurityGroup` | Inbound PostgreSQL (5432) restricted strictly to `ECSSecurityGroup`, all egress |
| `SSMALBSecurityGroup` | `AWS::SSM::Parameter`     | SSM parameter storing ALB Security Group ID                                     |
| `SSMECSSecurityGroup` | `AWS::SSM::Parameter`     | SSM parameter storing ECS Security Group ID                                     |
| `SSMEFSSecurityGroup` | `AWS::SSM::Parameter`     | SSM parameter storing EFS Security Group ID                                     |
| `SSMDBSecurityGroup`  | `AWS::SSM::Parameter`     | SSM parameter storing RDS DB Security Group ID                                  |

---

## Parameters

| Parameter         | Type                | Default | Description                                   |
| ----------------- | ------------------- | ------- | --------------------------------------------- |
| `EnvironmentName` | String              | `prod`  | Environment prefix (`dev`, `staging`, `prod`) |
| `VpcId`           | `AWS::EC2::VPC::Id` | -       | Primary VPC ID (obtained from Module 01)      |

---

## Inter-Module Contract & Discovery

### SSM Parameter Store

Downstream modules discover security groups via SSM:

- `/nextcloud/${EnvironmentName}/security/alb-sg-id` ➔ ALB Security Group ID (used by Module 05)
- `/nextcloud/${EnvironmentName}/security/ecs-sg-id` ➔ ECS Fargate Security Group ID (used by Module 05)
- `/nextcloud/${EnvironmentName}/security/efs-sg-id` ➔ EFS Security Group ID (used by Module 03)
- `/nextcloud/${EnvironmentName}/security/db-sg-id` ➔ RDS PostgreSQL Security Group ID (used by Module 04)

### CloudFormation Exports

- `${EnvironmentName}-nextcloud-ALBSecurityGroupId`
- `${EnvironmentName}-nextcloud-ECSSecurityGroupId`
- `${EnvironmentName}-nextcloud-EFSSecurityGroupId`
- `${EnvironmentName}-nextcloud-DBSecurityGroupId`

---

## Deployment CLI Example

```bash
VPC_ID=$(aws ssm get-parameter --name "/nextcloud/prod/infra/vpc-id" --query "Parameter.Value" --output text)

aws cloudformation deploy \
  --template-file infra/modules/02-security/template.yaml \
  --stack-name prod-nextcloud-02-security \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
      EnvironmentName=prod \
      VpcId="${VPC_ID}"
```
