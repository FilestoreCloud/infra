# Operational Automation Tooling

Operational, tenant provisioning, and maintenance utilities for Nextcloud Multi-Tenant SaaS on AWS.

> [!NOTE]
> All infrastructure provisioning, deployments, and full teardowns are managed strictly via **Native GitHub Actions CI/CD workflows**:
>
> - Deployment: [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)
> - Destruction: [`.github/workflows/destroy.yml`](../.github/workflows/destroy.yml)
> - Fleet Rollout: [`.github/workflows/fleet-rollout.yml`](../.github/workflows/fleet-rollout.yml)
> - Tenant Provisioning: [`.github/workflows/provision.yml`](../.github/workflows/provision.yml)

---

## 1. Dedicated Tenant Provisioning Automation (`provision_dedicated_tenant.py`)

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

---

## 2. Fleet Rollout Engine (`rollout_tenant_image.py`)

Automates phased / canary / blue-green rollouts of new golden container images across all dedicated tenant ECS services.

```bash
python3 scripts/rollout_tenant_image.py \
  --image "<account-id>.dkr.ecr.<region>.amazonaws.com/nextcloud:30.0.6-production" \
  --strategy phased \
  --env prod
```

---

## 3. Developer & Environment Tooling

- **`setup-hooks.sh`**: Installs pre-commit hygiene and Conventional Commits git hooks locally.

> [!TIP]
> Architecture diagrams are maintained as code via **[AWS Diagram as Code (`awsdac`)](https://github.com/awslabs/diagram-as-code)** definitions in [`infra/diagrams/`](../infra/diagrams/).
