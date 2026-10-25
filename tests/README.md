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

### `terratest/` (Infrastructure as Code & Control Plane Verification)

| Path                                                                             | Description                                                                                                                               |
| -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| [`inplace_01_networking_test.go`](terratest/inplace_01_networking_test.go)       | **Stage 1 (Networking):** Validates VPC CIDR, Multi-AZ subnets, Public/Private routing, and SSM exports                                   |
| [`inplace_02_security_test.go`](terratest/inplace_02_security_test.go)           | **Stage 2 (Security):** Audits Security Groups; verifies DB (5432) & EFS (2049) are strictly restricted and never open to 0.0.0.0/0       |
| [`inplace_03_storage_test.go`](terratest/inplace_03_storage_test.go)             | **Stage 3 (Storage):** Audits S3 Vault (Versioning, AES-256 SSE, 100% BlockPublicAccess) & EFS file system                                |
| [`inplace_04_database_test.go`](terratest/inplace_04_database_test.go)           | **Stage 4 (Database):** Audits RDS PostgreSQL private endpoint and Secrets Manager active credential secret                               |
| [`inplace_05_compute_test.go`](terratest/inplace_05_compute_test.go)             | **Stage 5 (Compute & ALB):** Verifies ECS Fargate tasks running, ALB Target Group healthy, and `/status.php` HTTP 200                     |
| [`inplace_06_superadmin_test.go`](terratest/inplace_06_superadmin_test.go)       | **Stage 6 (SuperAdmin & Lambda):** Audits DynamoDB table, invokes Lambda (CORS, mutations), probes Function URL, CloudWatch & SSM Runbook |
| [`inplace_07_observability_test.go`](terratest/inplace_07_observability_test.go) | **Stage 7 (Observability):** Audits CloudWatch Dashboard, SNS alerts topic, and CloudWatch Metric Alarms                                  |

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
# Python & Node test dependencies for Nextcloud App/E2E
pip install pytest requests boto3
cd tests/nextcloud/e2e && npm install && cd ../..

# Go 1.25+ for Terratest
go version
```

Ensure AWS credentials or environment variables are configured:

```bash
export AWS_REGION="ap-southeast-1"
export ENV="dev" # or "staging", "prod"
```

### Execute Tests

```bash
# 1. Run Terratest In-Place Infrastructure & Control Plane Suite
cd tests/terratest
go test -v -run "TestInPlace" -timeout 15m
cd ../..

# 2. Run Nextcloud feature acceptance tests
TENANT_ID="acme" pytest tests/nextcloud/features/ -v

# 3. Run browser E2E Playwright tests (headless)
cd tests/nextcloud/e2e
npx playwright test

# Run Playwright tests with interactive UI
npx playwright test --ui
```

---

## 4. Test Evidence & Reports

Full execution logs, evidence screenshots, and verified live test results are documented in:

- **Architecture & E2E Test Report:** [2026-10-05 Sprint Report](https://github.com/FilestoreCloud/reports/blob/main/2026-10-05/report.md)
- **Test Screenshots Gallery:** [Evidence Screenshots](https://github.com/FilestoreCloud/reports/tree/main/2026-10-05/imgs/evidence/)
