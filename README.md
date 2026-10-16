<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/storix-logo-white.png">
    <img alt="Storix Logo" src="docs/images/storix-logo.png" width="360">
  </picture>
</p>

# Storix Infrastructure & Operations

<p align="center">
  <a href="#test-status--verification-matrix"><img src="https://img.shields.io/badge/CI%2FCD-Quality%20Gate%20Passing-brightgreen?style=flat-square&logo=githubactions" alt="CI Quality Gate"></a>
  <a href="#test-status--verification-matrix"><img src="https://img.shields.io/badge/Tests-195%2F195%20Passed%20(100%25)-brightgreen?style=flat-square&logo=pytest" alt="Tests Passed"></a>
  <a href="#test-status--verification-matrix"><img src="https://img.shields.io/badge/Type%20Safety-Mypy%20Strict-blue?style=flat-square&logo=python" alt="Mypy Strict"></a>
  <a href="#test-status--verification-matrix"><img src="https://img.shields.io/badge/Security-Checkov%20CIS%20AWS-brightgreen?style=flat-square&logo=checkov" alt="Checkov Compliant"></a>
  <a href="#test-status--verification-matrix"><img src="https://img.shields.io/badge/Hypothesis-Property%20Fuzzing-purple?style=flat-square" alt="Hypothesis Fuzzing"></a>
  <a href="#test-status--verification-matrix"><img src="https://img.shields.io/badge/Moto-In--Memory%20AWS-orange?style=flat-square" alt="Moto AWS Mock"></a>
  <a href="#test-status--verification-matrix"><img src="https://img.shields.io/badge/Concurrency-46.8k%20ops%2Fsec%20(p99%205.5ms)-blue?style=flat-square" alt="Concurrency Benchmark"></a>
</p>

Modular CloudFormation Infrastructure as Code (IaC) and operational automation for the Storix enterprise multi-tenant platform on AWS.

---

## Test Status & Verification Matrix

| Test Suite | Framework / Tool | Tests | Scope & Assertions | Status |
|---|---|---|---|---|
| **E2E Invariants (Tiers 1–4)** | `pytest` / `unittest` | **167** | Cross-feature CloudFormation contracts, Step Functions SAGAs, private subnet isolation, zero unbound wildcard domains | ![Passing](https://img.shields.io/badge/167%20passed-brightgreen?style=flat-square) |
| **Control Plane Unit** | `unittest` | **11** | RBAC SuperAdmin vs Viewer, MFA TOTP SHA256 challenge tokens, CloudWatch metrics, fail-closed signing keys | ![Passing](https://img.shields.io/badge/11%20passed-brightgreen?style=flat-square) |
| **AWS In-Memory Integration** | `moto` | **4** | DynamoDB Optimistic Concurrency Control (OCC), SecretsManager retrieval, CloudWatch put_metric_data | ![Passing](https://img.shields.io/badge/4%20passed-brightgreen?style=flat-square) |
| **Property-Based Security** | `hypothesis` | **5** | 100 iterations each: Host-header injection, corrupted tokens, signature tampering, TOTP arbitrary input resilience | ![Passing](https://img.shields.io/badge/5%20passed-brightgreen?style=flat-square) |
| **Data Contract Schemas** | `pydantic v2` | **6** | TenantRecord, AuditLogEvent, SessionTokenClaims, negative quota rejection, strict tenant ID regex | ![Passing](https://img.shields.io/badge/6%20passed-brightgreen?style=flat-square) |
| **Static Type Safety** | `mypy --strict` | **1** | Enforces 100% type annotations across Control Plane & Schemas (0 missing annotations) | ![Passing](https://img.shields.io/badge/0%20errors-brightgreen?style=flat-square) |
| **Security Policy Compliance** | `checkov 3.2` | **1** | Validates CIS AWS Foundations benchmarks and security group least-privilege egress rules | ![Passing](https://img.shields.io/badge/CIS%20Compliant-brightgreen?style=flat-square) |
| **Concurrency Load Benchmark** | In-Memory Runner | **1** | 1,000 tasks / 20 workers: **46,896 ops/sec**, p50=0.01ms, p95=1.4ms, **p99=5.5ms** | ![Passing](https://img.shields.io/badge/sub--15ms%20p99-brightgreen?style=flat-square) |
| **Total Infra Tests** | **Full Suite** | **195 / 195 (100%)** | **Fully Autonomous Self-Contained Testing** | ![Passing](https://img.shields.io/badge/100%25%20Passing-brightgreen?style=flat-square) |

---

## 1. Architecture Overview

![Storix Multi-Tenant AWS Architecture](docs/images/nextcloud_architecture.png)

Storix utilizes a zero-code-modification, fully AWS-native modular CloudFormation architecture with container-per-tenant isolation on Amazon ECS Fargate.

### Key Architectural Boundaries

- **Container-per-Tenant Isolation:** Dedicated Amazon ECS Fargate task (`service-<tenant_id>`) per tenant. Suspending a tenant scales `desiredCount: 0` for FinOps zero compute cost.
- **Dynamic Routing:** Host-Header routing at Application Load Balancer (`<tenant_id>.domain.com` ➔ `tg-<tenant_id>` ➔ `service-<tenant_id>`).
- **3-Tier Storage & Data Separation:**
  - **Persistent Config Store (Amazon EFS):** `/tenants/<tenant_id>/config` mounted to `/var/www/html/config`.
  - **Object Storage Vault (Amazon S3):** Isolated prefixes `s3://<vault>/tenants/<tenant_id>/...`.
  - **Database (Amazon RDS PostgreSQL 16):** Dedicated physical database (`nc_<tenant_id>`) per tenant.
- **Observability & Security:** AWS Secrets Manager encryption, CloudWatch Logs & Container Insights, Amazon Bedrock Claude 3.5 Sonnet sidecar integration.

---

## 2. Directory Layout

```
.
├── docs/
│   └── images/                # Architecture diagrams (compiled with awsdac)
├── infra/
│   ├── diagrams/              # Diagram-as-Code specifications (awslabs/diagram-as-code)
│   ├── modules/
│   │   ├── 01-networking/     # VPC, Subnets, Route Tables, NAT / VPC Endpoints
│   │   ├── 02-security/       # Security Groups, KMS Keys, IAM Roles
│   │   ├── 03-storage/        # Amazon EFS & S3 Vault
│   │   ├── 04-database/       # Amazon RDS PostgreSQL 16 Cluster
│   │   ├── 05-compute/        # Amazon ECS Fargate Cluster & ALB
│   │   ├── 06-superadmin/     # DynamoDB Tenant Registry, SuperAdmin API, SSM Operator
│   │   └── 07-observability/  # CloudWatch Dashboard, Metric Alarms, SNS Alerts
│   ├── environments/          # Environment parameters (dev.json, staging.json, prod.json)
│   └── root.yaml              # Root nested stack orchestrator
├── tests/                     # Automated test suite (pytest)
└── .github/workflows/         # Native GitHub Actions CI/CD deployment & destruction pipelines
```

---

## 3. Deployment & Quick Start

### Validate Templates Locally

```bash
cfn-lint --config-file .devsecops/.cfnlintrc.yaml infra/modules/*/template.yaml infra/root.yaml
```

### Deploy Full Infrastructure Stack

All infrastructure deployments and destructions are executed via **Native GitHub Actions CI/CD**:

- **Deploy**: Trigger workflow [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) (on push to `main` or via `workflow_dispatch`).
- **Destroy**: Trigger workflow [`.github/workflows/destroy.yml`](.github/workflows/destroy.yml) (with required `CONFIRM_DESTROY: DESTROY` confirmation).

### Provision a Dedicated Tenant

Tenant provisioning is managed dynamically through the **Super Admin Console**:

- Use the Web Console UI ([`Storix/console`](https://github.com/Storix/console)) or API Gateway endpoint (`/api/tenants` with action `PROVISION`) to create, configure, suspend, or delete tenants.

---

## 4. Testing & Verification

```bash
# Run unit & integration test suite
pytest tests/ -v

# Run CloudFormation linter
cfn-lint --config-file .devsecops/.cfnlintrc.yaml infra/modules/*/template.yaml infra/root.yaml
```

---

## 5. Architecture Diagrams as Code

The architecture diagrams are maintained as code using [AWS Diagram as Code (`awsdac`)](https://github.com/awslabs/diagram-as-code):

```bash
# Rebuild Nextcloud infrastructure architecture diagram
awsdac infra/diagrams/nextcloud_architecture.yaml -o docs/images/nextcloud_architecture.png -f

# Rebuild Super Admin Console architecture diagram
awsdac infra/diagrams/console_architecture.yaml -o docs/images/console_architecture.png -f
```

---

## 6. Related Repositories

- [**`Storix/runtime`**](https://github.com/Storix/runtime): Docker Golden Image & Bedrock AI Sidecar.
- [**`Storix/console`**](https://github.com/Storix/console): Super Admin Web Console (React 18 + Refine + Ant Design).

---

## License

Licensed under the [Apache License, Version 2.0](LICENSE).

