# Module 03: Storage (Amazon S3 Multi-Tenant Vault & Amazon EFS)

## Overview
Deploys the dual-tier storage architecture for Nextcloud Multi-Tenant SaaS on AWS:
1. **Amazon EFS Persistent Config Store:** An encrypted, elastic Amazon Elastic File System (EFS) providing shared POSIX storage for Nextcloud's system configuration (`/var/www/html/config`). Mounted simultaneously across all pooled Fargate container replicas via an EFS Access Point (`/tenants/default/config`, POSIX UID/GID 33 `www-data`), preserving runtime state, installed apps, secrets, and server configuration across container restarts.
2. **Amazon S3 Multi-Tenant Object Storage Vault:** An encrypted, versioned, lifecycle-optimized S3 bucket serving as Nextcloud's Primary ObjectStore (`s3://<bucket>/<tenant_id>/...`). Accessed privately via the complimentary S3 Gateway VPC Endpoint deployed in Module 01 ($0/mo, zero egress fees).

---

## Storage Architecture Breakdown

```
┌───────────────────────────────────────────────────────────┐
│              Nextcloud Pooled Fargate Tasks               │
└───────────────┬───────────────────────────┬───────────────┘
                │                           │
                │ NFS Port 2049             │ HTTPS (S3 Gateway Endpoint)
                │ (/var/www/html/config)    │ (s3://<vault>/<tenant>/...)
                ▼                           ▼
┌───────────────────────────────┐ ┌───────────────────────────────┐
│          Amazon EFS           │ │           Amazon S3           │
│   (Persistent Config Store)   │ │    (Multi-Tenant Data Vault)  │
│ - Elastic Throughput          │ │ - AES-256 Server Encryption   │
│ - Encrypted at Rest           │ │ - Versioning Enabled          │
│ - Access Point: POSIX 33:33   │ │ - Standard-IA & Glacier Rules │
│ - 30-Day Infrequent Access    │ │ - Strict TLS Enforce Policy   │
└───────────────────────────────┘ └───────────────────────────────┘
```

---

## Security Policies & Compliance
* **Amazon EFS:**
  * Transit Encryption (TLS) enforced via ECS Fargate volume mounts.
  * Encrypted at Rest using AWS KMS default key.
  * Access Point isolation restricts file access strictly to POSIX UID `33` / GID `33` (`www-data`).
  * Inbound NFS traffic on port 2049 restricted strictly to `ECSSecurityGroup`.
* **Amazon S3 Vault:**
  * Server-Side Encryption: AES-256 default encryption (`SSEAlgorithm: AES256`).
  * Object Versioning: Enabled to support file recovery and compliance audits.
  * Public Access Block: All 4 S3 block public access controls enabled.
  * Transport Encryption (TLS): Bucket policy denies all non-TLS requests (`aws:SecureTransport: false`).
  * Disaster Protection: Protected with `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain`.

---

## FinOps Lifecycle Optimization Rules
* **EFS Lifecycle Management:** Automatically transitions inactive config files to EFS Infrequent Access (IA) after 30 days (~92% cost savings on cold storage).
* **S3 Multipart Upload Cleanup:** Aborts incomplete multipart uploads after 7 days.
* **S3 Standard-IA Tiering:** Moves noncurrent file versions to S3 Standard-IA after 30 days (~40% cost reduction).
* **S3 Glacier Archive:** Transitions noncurrent file versions to S3 Glacier Flexible Archive after 90 days (~80% cost reduction).
* **S3 Expiration:** Permanently deletes noncurrent versions after 365 days.

---

## Resources Created

| Logical ID | Resource Type | Description |
|---|---|---|
| `S3VaultBucket` | `AWS::S3::Bucket` | Primary Multi-Tenant S3 Vault with encryption, versioning, and lifecycle policies |
| `S3VaultBucketPolicy` | `AWS::S3::BucketPolicy` | Enforces TLS-only data transfer (`aws:SecureTransport: false` Deny) |
| `NextcloudEFS` | `AWS::EFS::FileSystem` | Encrypted, elastic EFS file system with 30-day IA lifecycle policy |
| `EFSMountTarget1` | `AWS::EFS::MountTarget` | Mount target in Public Subnet 1 bound to `EFSSecurityGroup` |
| `EFSMountTarget2` | `AWS::EFS::MountTarget` | Mount target in Public Subnet 2 bound to `EFSSecurityGroup` |
| `DefaultEFSAccessPoint` | `AWS::EFS::AccessPoint` | Access point targeting `/tenants/default/config` with POSIX UID/GID 33 |
| `SSMS3VaultBucket` | `AWS::SSM::Parameter` | SSM parameter storing S3 Vault bucket name |
| `SSMS3VaultBucketArn` | `AWS::SSM::Parameter` | SSM parameter storing S3 Vault bucket ARN |
| `SSMEFSFileSystemId` | `AWS::SSM::Parameter` | SSM parameter storing EFS File System ID |
| `SSMDefaultAccessPointId` | `AWS::SSM::Parameter` | SSM parameter storing EFS Access Point ID |

---

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `EnvironmentName` | String | `prod` | Environment prefix (`dev`, `staging`, `prod`) |
| `PublicSubnet1Id` | `AWS::EC2::Subnet::Id` | - | Public Subnet 1 ID for EFS Mount Target |
| `PublicSubnet2Id` | `AWS::EC2::Subnet::Id` | - | Public Subnet 2 ID for EFS Mount Target |
| `EFSSecurityGroupId` | `AWS::EC2::SecurityGroup::Id` | - | EFS Security Group ID (from Module 02) |
| `TransitionToIADays` | Number | `30` | Days before transitioning noncurrent S3 versions to S3 Standard-IA |
| `TransitionToGlacierDays` | Number | `90` | Days before transitioning noncurrent S3 versions to S3 Glacier |
| `NoncurrentVersionExpirationDays` | Number | `365` | Days before permanently deleting noncurrent S3 versions |

---

## Inter-Module Contract & Discovery

### SSM Parameter Store
* `/nextcloud/${EnvironmentName}/infra/s3-vault-bucket` ➔ S3 Bucket name
* `/nextcloud/${EnvironmentName}/infra/s3-vault-bucket-arn` ➔ S3 Bucket ARN
* `/nextcloud/${EnvironmentName}/infra/efs-id` ➔ EFS File System ID
* `/nextcloud/${EnvironmentName}/infra/default-access-point-id` ➔ EFS Access Point ID

### CloudFormation Exports
* `${EnvironmentName}-nextcloud-S3VaultBucketName`
* `${EnvironmentName}-nextcloud-S3VaultBucketArn`
* `${EnvironmentName}-nextcloud-EFSFileSystemId`
* `${EnvironmentName}-nextcloud-EFSFileSystemArn`
* `${EnvironmentName}-nextcloud-DefaultEFSAccessPointId`

---

## Deployment CLI Example

```bash
SUB_1=$(aws ssm get-parameter --name "/nextcloud/prod/infra/public-subnets" --query "Parameter.Value" --output text | cut -d',' -f1)
SUB_2=$(aws ssm get-parameter --name "/nextcloud/prod/infra/public-subnets" --query "Parameter.Value" --output text | cut -d',' -f2)
EFS_SG=$(aws ssm get-parameter --name "/nextcloud/prod/security/efs-sg-id" --query "Parameter.Value" --output text)

aws cloudformation deploy \
  --template-file infra/modules/03-storage/template.yaml \
  --stack-name prod-nextcloud-03-storage \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
      EnvironmentName=prod \
      PublicSubnet1Id="${SUB_1}" \
      PublicSubnet2Id="${SUB_2}" \
      EFSSecurityGroupId="${EFS_SG}"
```
