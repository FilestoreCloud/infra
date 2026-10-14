# AGENTS.md

> Universal AI Agent Instructions & Operating Guidelines for FilestoreCloud Infrastructure & Operations.
> Stewarded under the open [AGENTS.md](https://agents.md) standard (Linux Foundation / AAIF).

---

## 1. Project Overview & Architecture

Enterprise multi-tenant cloud platform deployed on AWS using a **Zero-Code-Modification**, fully AWS-native modular CloudFormation architecture.

### Key Architecture Boundaries

- **Container-per-Tenant Isolation:** Dedicated Amazon ECS Fargate container (`service-<tenant_id>`) per tenant. Suspending a tenant scales `desiredCount: 0` for FinOps zero compute cost.
- **Dynamic Routing:** Host-Header routing at Application Load Balancer (`<tenant_id>.domain.com` ➔ `tg-<tenant_id>` ➔ `service-<tenant_id>`).
- **3-Tier Storage & Data Separation:**
  - **Persistent Config Store (Amazon EFS):** `/tenants/<tenant_id>/config` mounted to `/var/www/html/config` (POSIX UID/GID 33 `www-data`).
  - **Object Storage Vault (Amazon S3):** Isolated prefixes `s3://<vault>/tenants/<tenant_id>/...`.
  - **Database (Amazon RDS PostgreSQL 16):** Dedicated physical database (`nc_<tenant_id>`) per tenant.
- **Control Plane & Registry:** DynamoDB Tenant Registry, SSM Lifecycle Operator runbook (`Tenant-Lifecycle-Operator`), and CloudWatch Alarms.
- **Multi-Repo Federation:**
  - `FilestoreCloud/infra` (This repo): CloudFormation IaC, CI/CD pipelines, test suite.
  - `FilestoreCloud/runtime`: Golden Docker image & Amazon Bedrock sidecar.
  - `FilestoreCloud/console`: Super Admin web portal (React + Refine + Ant Design).

### Directory Layout

```
├── infra/            # Modular CloudFormation IaC (modules 01-07, root.yaml)
├── tests/            # Automated integration & unit test suite (pytest)
├── .github/          # CI/CD deployment and destruction workflows
├── .githook/         # Git hooks (Conventional Commits, branch protection, DevSecOps)
└── .devsecops/       # AWS Labs DevSecOps configurations (Ferret Scan, ESLint Security)
```

---

## 2. Essential Commands

### Testing & Verification

```bash
# Run unit & integration test suite
pytest tests/ -v

# Run specific test file
pytest tests/console-backend/test_control_panel.py -v
```

### Linters & DevSecOps Static Analysis (AWS Labs Template)

```bash
# CloudFormation template linting (matching CI)
cfn-lint infra/modules/*/template.yaml infra/root.yaml -i W3002 W2001 W1011 W3005

# CloudFormation Guard policy-as-code compliance
cfn-guard validate --rules infra/rules/ --data infra/modules/*/template.yaml --data infra/root.yaml --show-summary fail

# Run complete AWS Labs DevSecOps pre-commit suite
pre-commit run --all-files

# Python linting & formatting (Ruff)
ruff check .
ruff format .
```

### Infrastructure Deployment & Linting

```bash
# Validate CloudFormation templates
cfn-lint infra/modules/*/template.yaml infra/root.yaml -i W3002 W2001 W1011 W3005

# Deploy or destroy infrastructure:
# Done via GitHub Actions CI/CD (.github/workflows/deploy.yml / destroy.yml)

# Provision a dedicated tenant:
# Done dynamically via Super Admin Console (/api/tenants with action PROVISION)
```

---

## 3. Branching Strategy & Boundaries ("Never" Rules)

1. **NEVER Commit Directly to `main`:**
   - `main` is strictly protected. The pre-commit and pre-push hooks will reject direct commits or pushes.
   - Always commit to `dev` or feature branches (`feat/...`, `fix/...`). Merging to `main` is only allowed via Pull Request from `dev`.
2. **MANDATORY Conventional Commits:**
   - Validated by `.githook/commit-msg`.
   - Allowed prefixes: `feat:`, `fix:`, `docs:`, `style:`, `refactor:`, `perf:`, `test:`, `build:`, `ci:`, `chore:`.
3. **NEVER Commit Hardcoded Secrets or Credentials:**
   - Validated by AWS Labs Ferret Scan and pre-commit checks.
   - Use AWS Secrets Manager, SSM Parameter Store, or environment variables.
4. **NEVER Run Destructive Teardown Autonomously:**
   - Destruction workflows delete live AWS stacks, EFS filesystems, and databases. Never trigger `.github/workflows/destroy.yml` without explicit user confirmation.
5. **Preserve Multi-Tenant Isolation:**
   - Keep isolated S3 prefixes (`s3://.../tenants/<tenant_id>/`) and dedicated database names (`nc_<tenant_id>`).

---

## 4. Definition of Done (Verification Checklist)

Before concluding any implementation or opening a PR:

1. [ ] **Pre-commit:** `pre-commit run --all-files` passes cleanly with zero errors.
2. [ ] **Tests:** `pytest tests/ -v` passes.
3. [ ] **IaC Lint & Policy:** `cfn-lint` and `cfn-guard validate` pass cleanly.
4. [ ] **Git:** Staged changes committed to `dev` with Conventional Commit message.
