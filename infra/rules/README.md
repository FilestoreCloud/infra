# CloudFormation Guard Policy-as-Code Rules

This directory contains declarative compliance and security policies written in **AWS CloudFormation Guard DSL (`.guard`)** to enforce security baselines across all modular CloudFormation templates.

---

## Rule Sets

| Rule File                                                          | Resource Types Checked                             | Enforced Security Controls                                                                                                                                                                                       |
| ------------------------------------------------------------------ | -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`s3_encryption_and_access.guard`](s3_encryption_and_access.guard) | `AWS::S3::Bucket`                                  | - Mandatory Server-Side Encryption (`BucketEncryption.ServerSideEncryptionConfiguration`)<br>- All 4 `PublicAccessBlockConfiguration` controls enabled                                                           |
| [`rds_security.guard`](rds_security.guard)                         | `AWS::RDS::DBInstance`                             | - Mandatory Storage Encryption (`StorageEncrypted == true`)<br>- Private accessibility only (`PubliclyAccessible == false`)<br>- Snapshot/Retain deletion policy                                                 |
| [`security_groups.guard`](security_groups.guard)                   | `AWS::EC2::SecurityGroup`                          | - Disallows unrestricted ingress (`0.0.0.0/0`) on port 22 (SSH)<br>- Disallows unrestricted ingress on port 5432 (PostgreSQL)<br>- Disallows unrestricted ingress on port 2049 (NFS/EFS)                         |
| [`compute.guard`](compute.guard)                                   | `AWS::ECS::TaskDefinition`, `AWS::ECR::Repository` | - ECS Tasks must use `awsvpc` network mode and require `FARGATE`<br>- Tasks must define explicit CPU and Memory allocations<br>- Containers must have `LogConfiguration`<br>- ECR repos must enable `ScanOnPush` |
| [`observability.guard`](observability.guard)                       | `AWS::Logs::LogGroup`                              | - CloudWatch Log Groups must have explicit `RetentionInDays` configured                                                                                                                                          |
| [`dynamodb.guard`](dynamodb.guard)                                 | `AWS::DynamoDB::Table`                             | - DynamoDB tables must have Point-in-Time Recovery enabled (`PointInTimeRecoveryEnabled == true`)                                                                                                                |

---

## Local Execution

Run compliance validation using the AWS `cfn-guard` CLI:

```bash
cfn-guard validate \
  --rules infra/rules/ \
  --data infra/modules/01-networking/template.yaml \
  --data infra/modules/02-security/template.yaml \
  --data infra/modules/03-storage/template.yaml \
  --data infra/modules/04-database/template.yaml \
  --data infra/modules/05-compute/template.yaml \
  --data infra/modules/06-superadmin/template.yaml \
  --data infra/modules/07-observability/template.yaml \
  --data infra/root.yaml \
  --show-summary fail
```
