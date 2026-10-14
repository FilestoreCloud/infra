# Operational & Fleet Rollout Tooling

Fleet deployment and operational utilities for Nextcloud Multi-Tenant SaaS on AWS.

> [!NOTE]
> All infrastructure provisioning and teardowns are managed strictly via **Native GitHub Actions CI/CD workflows**:
>
> - Full Infrastructure Deploy: [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)
> - Full Infrastructure Destruction: [`.github/workflows/destroy.yml`](../.github/workflows/destroy.yml)
> - Fleet Rollout Automation: [`.github/workflows/fleet-rollout.yml`](../.github/workflows/fleet-rollout.yml)
>
> Tenant instances are provisioned and managed dynamically through the **Super Admin Console** via the Control Plane Lambda & SSM Automation Runbook.

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
