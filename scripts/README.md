# Operational & Developer Tooling

Operational utilities and developer configuration for Nextcloud Multi-Tenant SaaS on AWS.

> [!NOTE]
> All infrastructure deployments and teardowns are managed strictly via **Native GitHub Actions CI/CD workflows**:
>
> - Infrastructure Deploy: [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)
> - Infrastructure Destruction: [`.github/workflows/destroy.yml`](../.github/workflows/destroy.yml)
>
> Tenant lifecycles are orchestrated dynamically through the **Super Admin Console** via the SuperAdmin Lambda & SSM Automation Runbook.

---

## 1. Developer & Environment Tooling

- **`setup-hooks.sh`**: Installs pre-commit hygiene and Conventional Commits git hooks locally.

> [!TIP]
> Architecture diagrams are maintained as code via **[AWS Diagram as Code (`awsdac`)](https://github.com/awslabs/diagram-as-code)** definitions in [`infra/diagrams/`](../infra/diagrams/).
