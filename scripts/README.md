# Operational & Fleet Rollout Tooling

Fleet deployment and operational utilities for Nextcloud Multi-Tenant SaaS on AWS.

> [!NOTE]
> All infrastructure provisioning, tenant instances, and full teardowns are managed strictly via **Native GitHub Actions CI/CD workflows** and **CloudFormation IaC templates**:
>
> - Full Infrastructure Deploy: [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)
> - Tenant CloudFormation Provisioning: [`.github/workflows/provision.yml`](../.github/workflows/provision.yml) (using [`infra/modules/tenant-instance/template.yaml`](../infra/modules/tenant-instance/template.yaml))
> - Full Infrastructure Destruction: [`.github/workflows/destroy.yml`](../.github/workflows/destroy.yml)
> - Fleet Rollout Automation: [`.github/workflows/fleet-rollout.yml`](../.github/workflows/fleet-rollout.yml)

---

## 1. Fleet Rollout Engine (`rollout_tenant_image.py`)

Automates phased / canary / blue-green rollouts of new golden container images across all dedicated tenant ECS services.

```bash
python3 scripts/rollout_tenant_image.py \
  --image "<account-id>.dkr.ecr.<region>.amazonaws.com/nextcloud:30.0.6-production" \
  --strategy phased \
  --env prod
```

---

## 2. Developer & Environment Tooling

- **`setup-hooks.sh`**: Installs pre-commit hygiene and Conventional Commits git hooks locally.

> [!TIP]
> Architecture diagrams are maintained as code via **[AWS Diagram as Code (`awsdac`)](https://github.com/awslabs/diagram-as-code)** definitions in [`infra/diagrams/`](../infra/diagrams/).
