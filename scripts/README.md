# Scripts & Automation Tooling

Operational, deployment, and tenant provisioning utilities for Nextcloud Multi-Tenant SaaS on AWS.

---

## 1. Unified Deployment CLI (`deploy.sh`)

[`deploy.sh`](deploy.sh) is a comprehensive Bash CLI runner for orchestrating CloudFormation stack deployments, template validations, and lifecycle teardowns.

### Usage
```bash
./scripts/deploy.sh [OPTIONS]
```

### Options & Flags

| Option | Description |
|---|---|
| `--validate` | Validates all CloudFormation module templates and exits |
| `--module <name>` | Deploys a single isolated module (`networking`, `security`, `storage`, `database`, `compute`, `control-plane`) |
| `--all` | Sequentially deploys all 6 modules from 01 to 06 |
| `--nested` | Packages and deploys the Root Nested Stack (`infra/root.yaml`) |
| `--destroy-module <name>` | Tears down an isolated module stack |
| `--destroy-all` | Safely destroys all modules in reverse dependency order (`06 -> 05 -> 04 -> 03 -> 02 -> 01`) |
| `--env <env>` | Target environment name (`prod`, `staging`, `dev`; default: `prod`) |
| `--region <region>` | AWS Region (default: `ap-southeast-1`) |
| `--s3-bucket <bucket>` | S3 bucket used for packaging nested stack templates |

### Common Examples
```bash
# Validate templates
./scripts/deploy.sh --validate

# Deploy only the compute module to dev
./scripts/deploy.sh --module compute --env dev

# Deploy all 6 modules sequentially to prod
./scripts/deploy.sh --all --env prod

# 1-Click Bootstrap using Nested Stacks
./scripts/deploy.sh --nested --s3-bucket my-cfn-templates-bucket --env prod

# Destroy development environment
./scripts/deploy.sh --destroy-all --env dev
```

---

## 2. Dedicated Tenant Provisioning Automation (`provision_dedicated_tenant.py`)

[`provision_dedicated_tenant.py`](provision_dedicated_tenant.py) is an automated Python engine for bootstrapping dedicated Nextcloud tenants with isolated resources.

### What It Orchestrates:
1. **Dynamic Parameter Discovery:** Queries AWS SSM Parameter Store (`/nextcloud/${ENV}/...`) to automatically resolve RDS endpoints, S3 bucket names, ALB URLs, and ECS cluster details.
2. **Dedicated PostgreSQL Database:** Connects to PostgreSQL using credentials fetched from AWS Secrets Manager and creates a dedicated database/schema (`nc_<tenant_id>`).
3. **S3 Prefix Isolation:** Creates dedicated tenant directories and vault storage policies (`s3://<vault>/<tenant_id>/`).
4. **Nextcloud OCC Setup:** Executes Nextcloud CLI automation commands to configure administrative credentials, data paths, and database bindings.
5. **ECS Capacity & Safe Scaling:** Inspects running ECS Fargate tasks and performs auto-scaling checks with safe exception handling.
6. **DynamoDB Audit Trail:** Registers the tenant in `${EnvironmentName}-nextcloud-tenant-registry` with `ACTIVE` status and quota allocations.

### Usage
```bash
python3 scripts/provision_dedicated_tenant.py \
  --tenant-id "acme-corp" \
  --tenant-name "Acme Corporation" \
  --admin-user "admin" \
  --admin-email "admin@acme.com" \
  --quota "100 GB" \
  --env prod
```
