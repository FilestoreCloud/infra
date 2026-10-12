# Module 04: Database & Amazon RDS PostgreSQL

## Overview
Deploys the managed Amazon RDS PostgreSQL 16 relational database tier and its corresponding AWS Secrets Manager credential store.

The database is isolated inside the private subnets created in Module 01, accessible only to the ECS Fargate compute tasks in Module 05 via the Security Group rules deployed in Module 02.

---

## Multi-Tenancy Data Isolation Model

The platform uses a **Dedicated Database Catalog Isolation** model:
* A shared PostgreSQL cluster hosts dedicated physical databases per tenant (`nc_<tenant_id>`).
* Each tenant has dedicated table structures, isolated row data, and independent schema lifecycles.
* This delivers enterprise-grade data isolation without the cost and resource overhead of provisioning separate RDS instances per tenant.

---

## Resources Created

| Logical ID | Resource Type | Description |
|---|---|---|
| `DBSubnetGroup` | `AWS::RDS::DBSubnetGroup` | Subnet group across Private Subnet 1 and Private Subnet 2 |
| `DBParameterGroup` | `AWS::RDS::DBParameterGroup` | Parameter group configured for PostgreSQL 16 (`postgres16` family) |
| `RDSInstance` | `AWS::RDS::DBInstance` | PostgreSQL 16.10 on AWS Graviton2 (`db.t4g.micro`), 20 GB gp3 storage |
| `DBSecret` | `AWS::SecretsManager::Secret` | Stores database connection JSON credentials in AWS Secrets Manager |
| `SSMDBEndpoint` | `AWS::SSM::Parameter` | SSM parameter storing RDS PostgreSQL private DNS endpoint |
| `SSMDBSecretArn` | `AWS::SSM::Parameter` | SSM parameter storing Secrets Manager secret ARN |

---

## Security & Reliability Configuration
* **Network Isolation:** `PubliclyAccessible: false`, bound strictly to private subnets.
* **Security Group:** Inbound TCP 5432 restricted solely to `ECSSecurityGroup`.
* **Disaster Protection:** `DeletionPolicy: Snapshot` and `UpdateReplacePolicy: Snapshot` ensure automated final DB snapshots before any stack deletion or replacement.
* **Secrets Management:** Credentials are automatically generated and stored as JSON under `/nextcloud/${EnvironmentName}/secrets/db-credentials`:
  ```json
  {
    "engine": "postgres",
    "host": "<rds-endpoint>",
    "port": 5432,
    "username": "nextcloud",
    "password": "<secure-password>",
    "dbname": "nextcloud"
  }
  ```

---

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `EnvironmentName` | String | `prod` | Environment prefix (`dev`, `staging`, `prod`) |
| `PrivateSubnet1Id` | `AWS::EC2::Subnet::Id` | - | Private Subnet 1 ID (from Module 01) |
| `PrivateSubnet2Id` | `AWS::EC2::Subnet::Id` | - | Private Subnet 2 ID (from Module 01) |
| `DBSecurityGroupId` | `AWS::EC2::SecurityGroup::Id` | - | RDS Security Group ID (from Module 02) |
| `DBInstanceClass` | String | `db.t4g.micro` | RDS instance class (AWS Graviton2) |
| `DBAllocatedStorage` | String | `20` | Storage capacity in GB (gp3) |
| `DBName` | String | `nextcloud` | Default master database name |
| `DBMasterUsername` | String | `nextcloud` | Master username for PostgreSQL |
| `DBPassword` | String | *(NoEcho)* | Master password for PostgreSQL |

---

## Inter-Module Contract & Discovery

### SSM Parameter Store
Downstream modules discover database connection details via SSM:
* `/nextcloud/${EnvironmentName}/infra/db-endpoint` ➔ Private RDS endpoint address (used by Module 05 for task definitions)
* `/nextcloud/${EnvironmentName}/infra/db-secret-arn` ➔ Secrets Manager ARN (used by Module 05 for task definition secrets injection)

### CloudFormation Exports
* `${EnvironmentName}-nextcloud-DatabaseEndpoint`
* `${EnvironmentName}-nextcloud-DBSecretArn`
* `${EnvironmentName}-nextcloud-RDSInstanceIdentifier`

---

## Deployment CLI Example

```bash
SUB_1=$(aws ssm get-parameter --name "/nextcloud/prod/infra/private-subnets" --query "Parameter.Value" --output text | cut -d',' -f1)
SUB_2=$(aws ssm get-parameter --name "/nextcloud/prod/infra/private-subnets" --query "Parameter.Value" --output text | cut -d',' -f2)
DB_SG=$(aws ssm get-parameter --name "/nextcloud/prod/security/db-sg-id" --query "Parameter.Value" --output text)

aws cloudformation deploy \
  --template-file infra/modules/04-database/template.yaml \
  --stack-name prod-nextcloud-04-database \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
      EnvironmentName=prod \
      PrivateSubnet1Id="${SUB_1}" \
      PrivateSubnet2Id="${SUB_2}" \
      DBSecurityGroupId="${DB_SG}" \
      DBPassword="YourStrongPassword123!"
```
