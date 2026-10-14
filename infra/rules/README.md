# CloudFormation Guard Policy-as-Code (AWS Best Practices)

This directory contains enterprise compliance and security policies written in **AWS CloudFormation Guard DSL (`.guard`)**, directly adapted from the official [AWS Guard Rules Registry](https://github.com/aws-cloudformation/aws-guard-rules-registry).

---

## Official AWS Rule Sets

| Rule Identifier                              | Rule File                                                                                          | Target Resource            | Description & Best Practice                                                                                                                                         |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `S3_BUCKET_LEVEL_PUBLIC_ACCESS_PROHIBITED`   | [`s3_bucket_level_public_access_prohibited.guard`](s3_bucket_level_public_access_prohibited.guard) | `AWS::S3::Bucket`          | Bắt buộc kích hoạt toàn bộ 4 thuộc tính của `PublicAccessBlockConfiguration` (`BlockPublicAcls`, `BlockPublicPolicy`, `IgnorePublicAcls`, `RestrictPublicBuckets`). |
| `S3_BUCKET_SERVER_SIDE_ENCRYPTION_ENABLED`   | [`s3_bucket_server_side_encryption_enabled.guard`](s3_bucket_server_side_encryption_enabled.guard) | `AWS::S3::Bucket`          | Bắt buộc mã hóa mặc định Server-Side Encryption (`AES256` hoặc `aws:kms`).                                                                                          |
| `RDS_STORAGE_ENCRYPTED`                      | [`rds_storage_encrypted.guard`](rds_storage_encrypted.guard)                                       | `AWS::RDS::DBInstance`     | Bắt buộc mã hóa ổ đĩa lưu trữ (`StorageEncrypted: true`) cho cơ sở dữ liệu.                                                                                         |
| `RDS_INSTANCE_PUBLIC_ACCESS_CHECK`           | [`rds_instance_public_access_check.guard`](rds_instance_public_access_check.guard)                 | `AWS::RDS::DBInstance`     | Ngăn chặn truy cập Internet công khai (`PubliclyAccessible: false`).                                                                                                |
| `INCOMING_SSH_DISABLED`                      | [`restricted_ssh.guard`](restricted_ssh.guard)                                                     | `AWS::EC2::SecurityGroup`  | Cấm mở cổng SSH (`22`) trực tiếp ra toàn thế giới (`0.0.0.0/0`).                                                                                                    |
| `RESTRICTED_INCOMING_TRAFFIC`                | [`restricted_common_ports.guard`](restricted_common_ports.guard)                                   | `AWS::EC2::SecurityGroup`  | Cấm mở lưu lượng inbound từ `0.0.0.0/0` tới các cổng nhạy cảm `[20, 21, 3389, 3306, 4333]`.                                                                         |
| `DYNAMODB_PITR_ENABLED`                      | [`dynamodb_pitr_enabled.guard`](dynamodb_pitr_enabled.guard)                                       | `AWS::DynamoDB::Table`     | Bắt buộc kích hoạt Point-in-Time Recovery cho bảng dữ liệu DynamoDB.                                                                                                |
| `ECS_TASK_FARGATE_AND_AWSVPC`                | [`ecs_fargate_task_definition.guard`](ecs_fargate_task_definition.guard)                           | `AWS::ECS::TaskDefinition` | Bắt buộc task ECS Fargate dùng mạng `awsvpc`, định mức CPU/Memory và có log driver.                                                                                 |
| `CLOUDWATCH_LOGGROUP_RETENTION_PERIOD_CHECK` | [`cloudwatch_log_group_retention.guard`](cloudwatch_log_group_retention.guard)                     | `AWS::Logs::LogGroup`      | Bắt buộc log group CloudWatch có thời gian lưu trữ hữu hạn để kiểm soát chi phí.                                                                                    |

---

## Rule Suppression Standard

Toàn bộ quy tắc tuân theo chuẩn **AWS Metadata Suppression**:

```yaml
Resources:
  MyResource:
    Type: AWS::S3::Bucket
    Metadata:
      guard:
        SuppressedRules:
          - S3_BUCKET_LEVEL_PUBLIC_ACCESS_PROHIBITED
```

---

## Local Validation

```bash
cfn-guard validate \
  --rules infra/rules/ \
  --data infra/modules/*/template.yaml \
  --data infra/root.yaml \
  --show-summary fail
```
