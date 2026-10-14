# Test Suite & Quality Assurance

Automated integration, end-to-end (E2E), and lifecycle test suite for Nextcloud Multi-Tenant SaaS on AWS.

---

## 1. Test Overview

The test suite validates:

- **Control Panel Web Application:** Verifies HTTP 200 responses, complete HTML5 DOM rendering, Chart.js telemetry integration, and JSON API payloads.
- **Tenant Lifecycle Operations:** Performs automated end-to-end verification of tenant state transitions:
  1. `PROVISION` ➔ Confirms DynamoDB registration (`status: ACTIVE`) and initial metric publishing.
  2. `SUSPEND` ➔ Confirms transition to `status: SUSPENDED` and metric suppression.
  3. `RESUME` ➔ Confirms restoration to `status: ACTIVE`.
  4. `DEPROVISION` ➔ Confirms removal from DynamoDB registry.
- **AWS CloudWatch Telemetry:** Verifies metric emission to the `Nextcloud/SaaS` namespace (`TenantStorageUsedMB`, `TenantActiveStatus`).

---

## 2. Test Files

| Test File                                          | Description                                                                                                     |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| [`test_control_panel.py`](test_control_panel.py)   | Comprehensive E2E tests for the Control Panel UI, REST API, DynamoDB state transitions, and CloudWatch metrics  |
| [`test_fleet_rollout.py`](test_fleet_rollout.py)   | Canary phased fleet rollout unit & dry-run tests                                                                |
| [`test_tenant_storage.py`](test_tenant_storage.py) | WebDAV storage & WAF size exclusion integration tests                                                           |
| [`features/`](features/)                           | **Nextcloud Official Feature Acceptance Suite:** Core status, WebDAV CRUD, OCS Sharing, User Quotas, Bedrock AI |
| [`e2e/`](e2e/)                                     | **Nextcloud Official Playwright UI Suite:** Browser E2E automation for Auth, Files, Sharing, and Navigation     |

---

## 3. Running Tests

### Prerequisites

Install test dependencies:

```bash
pip install pytest requests boto3
```

Ensure AWS credentials or environment variables are configured:

```bash
export AWS_REGION="ap-southeast-1"
# Defaults to https://admin.png261.dev; optionally override for local/staging:
# export CONTROL_PANEL_URL="http://localhost:8080"
```

### Execute Tests

```bash
# Run backend & API feature acceptance tests
pytest tests/ -v

# Run specific Nextcloud feature suite for tenant
TENANT_ID="acme" pytest tests/features/ -v

# Run browser E2E Playwright tests (headless)
cd tests/e2e
npm install
npx playwright test

# Run Playwright tests with interactive UI
npx playwright test --ui
```

---

## 4. Test Evidence & Reports

Full execution logs, evidence screenshots, and verified live test results are documented in:

- **Architecture & E2E Test Report:** [`../reports/2026-10-05/report.md`](../reports/2026-10-05/report.md)
- **Test Screenshots Gallery:** [`../reports/2026-10-05/imgs/evidence/`](../reports/2026-10-05/imgs/evidence/)
