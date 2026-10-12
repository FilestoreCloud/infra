# AGENTS.md

> Universal AI Agent Instructions & Operating Guidelines for Nextcloud Multi-Tenant SaaS on AWS.
> Stewarded under the open [AGENTS.md](https://agents.md) standard (Linux Foundation / AAIF).

---

## 1. Project Overview & Architecture

Enterprise multi-tenant Nextcloud platform deployed on AWS using a **Zero-Code-Modification**, fully AWS-native modular CloudFormation architecture.

### Key Architecture Boundaries

- **Container-per-Tenant Isolation:** Dedicated Amazon ECS Fargate container (`service-<tenant_id>`) per tenant. Suspending a tenant scales `desiredCount: 0` for FinOps zero compute cost.
- **Dynamic Routing:** Host-Header routing at Application Load Balancer (`<tenant_id>.domain.com` ➔ `tg-<tenant_id>` ➔ `service-<tenant_id>`).
- **Dual-Container Task:** Nextcloud 30 (Apache) + LiteLLM Bedrock Bridge sidecar (`127.0.0.1:4000`) proxying Claude 3.5 Sonnet on Amazon Bedrock.
- **3-Tier Storage & Data Separation:**
  - **Persistent Config Store (Amazon EFS):** `/tenants/<tenant_id>/config` mounted to `/var/www/html/config` (POSIX UID/GID 33 `www-data`).
  - **Object Storage Vault (Amazon S3):** Isolated prefixes `s3://<vault>/tenants/<tenant_id>/...`.
  - **Database (Amazon RDS PostgreSQL 16):** Dedicated physical database (`nc_<tenant_id>`) per tenant.
- **Control Plane:** DynamoDB Tenant Registry, SSM Lifecycle Operator runbook (`Tenant-Lifecycle-Operator`), CloudWatch Dashboard, and Super Admin Portal (`control-panel/`).

### Directory Layout

```
├── infra/            # Modular CloudFormation IaC (modules 01-06, tenant-instance, root.yaml)
├── control-panel/    # Super Admin Web Console (Vite + React 18 + Refine + Ant Design)
├── scripts/          # Operational CLI automation (provisioning, deploy, OCC runners)
├── docker/           # Golden container image (Nextcloud 30 + Bedrock AI integration)
├── tests/            # Automated integration & unit test suite (pytest)
├── .githook/         # Git hooks (Conventional Commits, branch protection, DevSecOps)
└── docs/             # Technical documentation & architecture specs
```

---

## 2. Essential Commands

### Testing & Verification

```bash
# Run unit & integration test suite (DO NOT run bare `pytest`)
pytest tests/ -v

# Run specific test file
pytest tests/test_control_panel.py -v
```

> [!WARNING]
> **Do NOT run bare `pytest` across the root directory.** Live verification scripts located in `scripts/test_*.py` make live network/AWS calls against provisioned domains and require active AWS credentials. Always target `pytest tests/ -v`.

### Control Panel (Web Admin Console)

```bash
cd control-panel

# Install dependencies
npm install

# Start development server (http://localhost:5173)
npm run dev

# Build production bundle (outputs to control-panel/dist)
npm run build

# Preview build
npm run preview
```

### Local API & Server

```bash
# Serve local control plane API & UI (http://localhost:8080)
python3 scripts/serve_control_panel.py

# Or via shortcut
python3 control-panel/start.py
```

### Linters & Static Analysis

```bash
# CloudFormation template linting (matching CI)
cfn-lint infra/modules/*/template.yaml infra/root.yaml -i W3002 W2001 W1011 W3005

# YAML syntax & structure validation
yamllint -d "{extends: relaxed, rules: {line-length: {max: 240}, indentation: {spaces: 2}}}" \
  infra/modules/ infra/root.yaml infra/environments/

# Python linting & formatting (Ruff)
ruff check .
ruff format --check .

# Dockerfile linting (Hadolint)
hadolint docker/Dockerfile --config .hadolint.yaml

# Pre-commit all hooks validation
pre-commit run --all-files
```

---

## 3. Coding Standards & Conventions

### Python (`scripts/`, `tests/`)

- Target **Python 3.11+**.
- Format with **Ruff / Black** (line-length 88 or 100 as per repo config).
- Always use type annotations for function signatures where practical.
- Use explicit AWS boto3 error handling (`ClientError`, `botocore.exceptions`).
- Never perform silent error swallowing (`except: pass`). Log or re-raise with informative context.

### TypeScript / React (`control-panel/`)

- Target **React 18** + **TypeScript 5 (strict mode)**.
- Use **Refine** framework with **Ant Design 5** UI components.
- Do not introduce `any` types; define clear interfaces for tenant records, metrics, and API payloads.
- Ensure all builds pass without compiler warnings (`npm run build`).

### CloudFormation IaC (`infra/`)

- Maintain modular structure under `infra/modules/<number>-<name>/template.yaml`.
- Export contract outputs cleanly (`${AWS::StackName}-<OutputName>`) and consume via `Fn::ImportValue`.
- Adhere to least privilege IAM permissions. Never use wildcards (`"Resource": "*"`) unless mandated by AWS service APIs.
- Keep parameter overrides in `infra/environments/{dev,staging,prod}.yaml`.

### Shell Scripts (`scripts/`, `.githook/`)

- Always start with `#!/usr/bin/env bash` and `set -euo pipefail`.
- Quote all variables (`"$VAR"`).
- Keep scripts idempotent and safe for repeated execution.

---

## 4. Boundaries & Guardrails ("Never" Rules)

1. **NEVER Hardcode Secrets or Credentials:**
   - Never commit AWS access keys, database passwords, session tokens, or private keys.
   - Use AWS Secrets Manager, IAM task roles, or environment variables.
2. **NEVER Commit Directly to Protected Branches:**
   - `main` and `master` branches are protected. The pre-commit hook will reject direct commits.
   - Always branch off `dev` or create a feature branch (`feat/...`, `fix/...`).
3. **MANDATORY Conventional Commits:**
   - Commit messages are validated by `.githook/commit-msg`.
   - Allowed prefixes: `feat:`, `fix:`, `docs:`, `style:`, `refactor:`, `perf:`, `test:`, `build:`, `ci:`, `chore:`, `revert:`.
   - Example: `feat(control-panel): add tenant quota visualization widget`
4. **NEVER Run Destructive Teardown Autonomously:**
   - Scripts such as `scripts/teardown_all.py` delete live AWS stacks, EFS filesystems, and RDS databases. Never execute these without explicit, unambiguous user confirmation.
5. **Preserve Multi-Tenant Isolation Boundaries:**
   - Never mix tenant S3 paths or allow cross-tenant EFS mount points.
   - Each tenant MUST retain dedicated prefixes: `s3://.../tenants/<tenant_id>/` and `nc_<tenant_id>` database names.

---

## 5. Definition of Done (Verification Checklist)

Before concluding any implementation or opening a PR, ensure:

1. [ ] **Tests:** `pytest tests/ -v` passes with zero regressions.
2. [ ] **Frontend:** `npm run build` succeeds inside `control-panel/` (if UI modified).
3. [ ] **IaC:** `cfn-lint infra/modules/*/template.yaml infra/root.yaml -i W3002 W2001 W1011 W3005` passes cleanly (if templates modified).
4. [ ] **Lint & Format:** `ruff check .` passes with no unresolved issues.
5. [ ] **Git Hooks:** All staged changes pass `.githook/pre-commit` hygiene checks and commit messages follow Conventional Commits.
