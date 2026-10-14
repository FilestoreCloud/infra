# FilestoreCloud Infrastructure & Operations

Modular CloudFormation Infrastructure as Code (IaC) and operational automation for the FilestoreCloud enterprise multi-tenant platform on AWS.

---

## 1. Architecture Overview

![FilestoreCloud Multi-Tenant AWS Architecture](docs/images/nextcloud_architecture.png)

FilestoreCloud utilizes a zero-code-modification, fully AWS-native modular CloudFormation architecture with container-per-tenant isolation on Amazon ECS Fargate.

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
│   │   ├── 06-observability/  # CloudWatch Alarms & Operational Dashboards
│   │   ├── 06-control-plane/  # DynamoDB Tenant Registry & SSM Operator
│   │   └── tenant-instance/   # Per-tenant CloudFormation stack template
│   ├── environments/          # Environment parameters (dev.yaml, staging.yaml, prod.yaml)
│   └── root.yaml              # Root nested stack orchestrator
├── scripts/                   # Operational automation (provisioning, rollout, OCC, utilities)
├── tests/                     # Automated test suite (pytest)
└── .github/workflows/         # Native GitHub Actions CI/CD deployment & destruction pipelines
```

---

## 3. Deployment & Quick Start

### Validate Templates Locally

```bash
cfn-lint infra/modules/*/template.yaml infra/root.yaml -i W3002 W2001 W1011 W3005
```

### Deploy Full Infrastructure Stack

All infrastructure deployments and destructions are executed via **Native GitHub Actions CI/CD**:

- **Deploy**: Trigger workflow [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) (on push to `main` or via `workflow_dispatch`).
- **Destroy**: Trigger workflow [`.github/workflows/destroy.yml`](.github/workflows/destroy.yml) (with required `CONFIRM_DESTROY: DESTROY` confirmation).

### Provision a Dedicated Tenant

Tenant provisioning is managed via:

1. **GitHub Actions Workflow**: Trigger [`.github/workflows/provision.yml`](.github/workflows/provision.yml) with parameters (`tenant_id`, `tenant_domain`).
2. **Super Admin Console**: Use the Web Console UI or API Gateway endpoint (`/api/tenants` with action `PROVISION`).

---

## 4. Testing & Verification

```bash
# Run unit & integration test suite
pytest tests/ -v

# Run CloudFormation linter
cfn-lint infra/modules/*/template.yaml infra/root.yaml -i W3002 W2001 W1011 W3005
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

- [**`FilestoreCloud/runtime`**](https://github.com/FilestoreCloud/runtime): Docker Golden Image & Bedrock AI Sidecar.
- [**`FilestoreCloud/console`**](https://github.com/FilestoreCloud/console): Super Admin Web Console (React 18 + Refine + Ant Design).
