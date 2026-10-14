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

## 2. Test Categories & Structure

The test suite is organized into distinct domain categories:

### `console-backend/` (SuperAdmin Control Plane & Operations)

| Test File                                                        | Description                                                                                                    |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| [`test_control_panel.py`](console-backend/test_control_panel.py) | Tests for SuperAdmin API Lambda backend (RBAC enforcement, MFA TOTP, DynamoDB transitions, SSM Runbooks, etc.) |

### `nextcloud/` (Nextcloud Application, APIs & End-to-End)

| Path                                                         | Description                                                                                                                                                                                                                                        |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`features/`](nextcloud/features/)                           | **Nextcloud Deep Filestore & Permissions Suite:** WebDAV CRUD, Granular Cross-User Permissions (Bitmask 1-31), File Drop (Upload-only), Password/Expiry Shares, RFC 4918 File Locking, Trashbin, Quota Hard Enforcement (HTTP 507), and Bedrock AI |
| [`e2e/`](nextcloud/e2e/)                                     | **Nextcloud Playwright UI Suite:** Browser E2E automation for Auth, Files, Sharing, and Navigation                                                                                                                                                 |
| [`test_tenant_storage.py`](nextcloud/test_tenant_storage.py) | WebDAV tenant storage & WAF size exclusion integration tests                                                                                                                                                                                       |

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
# Run all tests across categories
pytest tests/ -v

# Run SuperAdmin control plane backend tests only
pytest tests/console-backend/ -v

# Run Nextcloud feature acceptance tests
TENANT_ID="acme" pytest tests/nextcloud/features/ -v

# Run browser E2E Playwright tests (headless)
cd tests/nextcloud/e2e
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
