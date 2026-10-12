# FilestoreCloud Infrastructure & Operations

Modular CloudFormation Infrastructure as Code (IaC) and operational automation for the FilestoreCloud enterprise multi-tenant platform on AWS.

---

## 1. Architecture Overview

FilestoreCloud utilizes a zero-code-modification, fully AWS-native modular CloudFormation architecture with container-per-tenant isolation on Amazon ECS Fargate.

### Key Architectural Boundaries

- **Container-per-Tenant Isolation:** Dedicated Amazon ECS Fargate task (`service-<tenant_id>`) per tenant. Suspending a tenant scales `desiredCount: 0` for FinOps zero compute cost.
- **Dynamic Routing:** Host-Header routing at Application Load Balancer (`<tenant_id>.domain.com` ➔ `tg-<tenant_id>` ➔ `service-<tenant_id>`).
- **3-Tier Storage & Data Separation:**
  - **Persistent Config Store (Amazon EFS):** `/tenants/<tenant_id>/config` mounted to `/var/www/html/config`.
  - **Object Storage Vault (Amazon S3):** Isolated prefixes `s3://<vault>/tenants/<tenant_id>/...`.
  - **Database (Amazon RDS PostgreSQL 16):** Dedicated physical database (`nc_<tenant_id>`) per tenant.
- **Control Plane & Registry:** Amazon DynamoDB Tenant Registry, SSM Lifecycle Operator runbooks, and CloudWatch operational dashboard.

---

## 2. Directory Layout

```
.
├── infra/
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
├── scripts/                   # Operational automation (deploy.sh, provisioning, rollout, OCC)
├── tests/                     # Automated test suite (pytest)
└── .github/workflows/         # CI/CD deployment & validation pipelines
```

---

## 3. Deployment & Quick Start

### Validate Templates

```bash
./scripts/deploy.sh --validate
```

### Deploy Full Infrastructure Stack

```bash
# Deploy all modules sequentially (01 -> 06)
./scripts/deploy.sh --all --env prod

# Or deploy a specific module
./scripts/deploy.sh --module compute --env prod
```

### Provision a Dedicated Tenant

```bash
python3 scripts/provision_dedicated_tenant.py \
  --tenant acme \
  --domain acme.filestorecloud.com \
  --quota 50GB \
  --env prod
```

---

## 4. Testing & Verification

```bash
# Run unit & integration test suite
pytest tests/ -v

# Run CloudFormation linter
cfn-lint infra/modules/*/template.yaml infra/root.yaml -i W3002 W2001 W1011 W3005
```

---

## 5. Related Repositories

- [**`FilestoreCloud/runtime`**](https://github.com/FilestoreCloud/runtime): Docker Golden Image & Bedrock AI Sidecar.
- [**`FilestoreCloud/console`**](https://github.com/FilestoreCloud/console): Super Admin Web Console (React 18 + Refine + Ant Design).
