# Storix Multi-Tenant SaaS — Infrastructure as Code

Modular CloudFormation architecture for enterprise Storix Multi-Tenant SaaS on AWS. Built with AWS Well-Architected Framework principles, automated CI/CD pipelines, and zero-NAT cost optimization.

---

## 1. Architecture Overview

![Storix Multi-Tenant AWS Architecture](../docs/images/nextcloud_architecture.png)

The infrastructure delivers:

- **Independent Tenant Compute Tier (Container-per-Tenant Isolation):** Every tenant operates in a dedicated, isolated Amazon ECS Fargate container (`service-<tenant_id>`) with its own runtime lifecycle. Suspending a tenant scales `desiredCount: 0` for instant FinOps zero compute cost while retaining all configuration and data.
- **AWS Graviton ARM64 Compute:** Supported natively in CloudFormation (`CpuArchitecture: ARM64` / `X86_64`), reducing ECS compute costs by 20%.
- **Amazon RDS Proxy Connection Pooling:** Dedicated connection pool layer between Fargate tasks and RDS PostgreSQL cluster to prevent connection saturation during scale-out events.
- **Dedicated Background Cron Runner:** EventBridge Scheduler (`AWS::Events::Rule`) periodically triggers background Nextcloud cron jobs (`rate(5 minutes)`), decoupling heavy async tasks from Web request workers.
- **Host-Header Dynamic Routing:** Traffic is routed at the Application Load Balancer via Host-Header routing rules (`<tenant_id>.domain.com` ➔ `tg-<tenant_id>` ➔ `service-<tenant_id>`).
- **Dual-Container Task:** Nextcloud 30 Apache paired with a local LiteLLM Bedrock Bridge sidecar proxying Claude 3.5 Sonnet foundation models on Amazon Bedrock.
- **3-Tier Storage & Data Tier:**
  - **Amazon EFS:** Encrypted shared persistent config volume mounting dedicated per-tenant Access Points (`/tenants/<tenant_id>/config` to `/var/www/html/config`, NFS 2049, POSIX UID/GID 33 `www-data`), with automated transitions to IA (30 days) and Archive (90 days).
  - **Amazon S3:** Multi-Tenant Vault Bucket for tenant files with isolated prefixes (`tenants/<tenant_id>/`) and lifecycle transition rules to S3 Intelligent-Tiering and 180-day Glacier Instant Retrieval.
  - **Amazon RDS PostgreSQL 16:** AWS Graviton cluster with dedicated per-tenant physical databases (`nc_<tenant_id>`) accessed via RDS Proxy.
- **Zero-NAT Lean Networking:** 2-AZ VPC with public subnets for ingress/compute and private subnets for database. Direct S3 access is routed through a complimentary S3 Gateway VPC Endpoint.
- **Native Control Plane:** Step Functions SAGAs, Amazon DynamoDB Tenant Registry, SuperAdmin API, and Async OCC Engine.
- **24/7 Synthetics Canaries:** Automated probes validating endpoint latency and response content round-the-clock.

---

## 2. Directory Structure

```
infra/
├── modules/
│   ├── 01-networking/          # VPC, 2 Public & 2 Private Subnets, Route Tables, S3 Gateway Endpoint
│   ├── 02-security/            # ALB, ECS Fargate, RDS PostgreSQL, and EFS Security Groups
│   ├── 03-storage/             # S3 Multi-Tenant Vault Bucket & Amazon EFS (30d IA · 90d Archive)
│   ├── 04-database/            # RDS PostgreSQL 16 & RDS Proxy Connection Pooler
│   ├── 05-compute/             # ALB Host Ingress, ECS Fargate (Graviton ARM64), Dedicated Cron Rule
│   ├── 06-superadmin/          # Step Functions SAGAs, DynamoDB Registry, Async OCC, SuperAdmin API
│   └── 07-observability/       # CloudWatch Synthetics Canary (24/7 SLA), Telemetry Dashboard & Alarms
├── environments/               # Per-environment parameter overrides
│   ├── dev.json
│   ├── staging.json
│   └── prod.json
├── rules/                      # AWS CloudFormation Guard policy-as-code rules (.guard)
└── root.yaml                   # Root Nested Stack orchestrator for 1-command bootstrap
```

---

## 3. Modular Architecture Breakdown

The infrastructure is decoupled into **7 autonomous modules** organized by lifecycle and change frequency:

| Layer  | Module | Key Resources | Lifecycle / Change Frequency |
|---|---|---|---|
| **01** | [`01-networking`](modules/01-networking/README.md) | VPC, 2 Public Subnets, 2 Private Subnets, IGW, S3 Gateway Endpoint | Low (Infrequent updates) |
| **02** | [`02-security`](modules/02-security/README.md) | ALB SG, ECS SG, RDS SG, EFS SG, RDS Proxy SG (defense-in-depth chaining) | Low (Security policy changes) |
| **03** | [`03-storage`](modules/03-storage/README.md) | S3 Vault Bucket (Intelligent-Tiering, Glacier) & Amazon EFS (30d IA, 90d Archive) | Very Low (Retain on delete) |
| **04** | [`04-database`](modules/04-database/README.md) | RDS PostgreSQL 16 (`db.t4g.micro`), RDS Proxy Connection Pooler, Secrets Manager | Low (Snapshot on delete) |
| **05** | [`05-compute`](modules/05-compute/README.md) | ALB, ECS Fargate (Graviton ARM64), Nextcloud + LiteLLM sidecar, EventBridge Cron | High (App deployments & scaling) |
| **06** | [`06-superadmin`](modules/06-superadmin/README.md) | Step Functions SAGAs, DynamoDB Registry, Async OCC Engine, Web Hosting (S3/CF) | Medium (Operations & admin) |
| **07** | [`07-observability`](modules/07-observability/README.md) | CloudWatch Synthetics Canary (24/7 SLA), Telemetry Dashboard, Metric Alarms | Low (Monitoring & alerts) |

---

## 4. Linting & Validation

```bash
# CloudFormation template linter
cfn-lint --config-file .devsecops/.cfnlintrc.yaml modules/*/template.yaml root.yaml
```
