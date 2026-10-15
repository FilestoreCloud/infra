# Super Admin Web Control Panel

Modern, lightweight single-page management application for SaaS Super Admins to monitor infrastructure health, manage tenant lifecycles, and view live telemetry.

---

## 1. Overview & Capabilities

- **Tenant Registry Management:** Real-time visibility into all registered tenants stored in Amazon DynamoDB (`${EnvironmentName}-nextcloud-tenant-registry`).
- **Multi-Factor Authentication (RFC 6238 TOTP):** Native two-step authentication supporting standard authenticator apps (Google Authenticator, 1Password, Authy) with zero external pip dependencies.
- **Role-Based Access Control (RBAC):**
  - `SuperAdmin`: Unrestricted administrative lifecycle, fleet operations, incident management, and system configuration.
- **Immutable Cloud Audit Trail:**
  - Chronological ledger stored in Amazon DynamoDB (`${EnvironmentName}-nextcloud-audit-logs`) with 1-year compliance TTL.
  - Structured JSON audit streaming to Amazon CloudWatch Logs (`/aws/audit/${EnvironmentName}-nextcloud-control-plane`) with 365-day retention.
- **Interactive Lifecycle Transitions:** Direct actions for `PROVISION`, `SUSPEND`, `RESUME`, and `DELETE` triggering native AWS Systems Manager (SSM) Automation runbooks and ECS task updates.
- **Live CloudWatch Telemetry Streaming:** Embedded Chart.js time-series charts displaying:
  - Tenant Storage Utilization (auto-discovered via CloudWatch SEARCH).
  - Tenant Lifecycle Status (Active / Suspended).
  - Application Load Balancer Request Rate & Target Latency.
  - ECS Fargate CPU & Memory consumption.
- **Zero-Bastion Direct Management:** Operates entirely through AWS SDK / HTTPS endpoints without requiring SSH or bastion hosts.

---

## 2. Directory Contents

| File                                                     | Purpose                                                                                                                   |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| [`template.yaml`](template.yaml)                         | CloudFormation template defining the 6 AWS Step Functions State Machines, DynamoDB registries, Cognito, and web hosting |
| [`tenant_operator_lambda.py`](tenant_operator_lambda.py) | Control Plane REST API Lambda backend and micro-task worker for Step Functions executions                                |

> [!NOTE]
> **Web Console Application:**
> The Super Admin Web Console frontend source code has moved to the dedicated **`console`** repository (built with React 18, Refine, Ant Design 5, and Vite). This module provisions the hosting infrastructure (S3 bucket and CloudFront distribution) and the backend API Lambda.

---

### Production Cloud Access

The Super Admin Web Control Panel is hosted on AWS using a decoupled **Amazon S3 + Amazon CloudFront** architecture for optimal performance, global low latency, and zero cold starts:

- **Frontend SPA Hosting:** Amazon S3 bucket (`${EnvironmentName}-nextcloud-admin-web-${AWS::AccountId}`) protected by CloudFront Origin Access Control (OAC).
- **Content Delivery & Edge Caching:** Amazon CloudFront Distribution with HTTP/2 & HTTP/3, custom error response SPA fallbacks (403/404 -> `/index.html`), and path-based routing:
  - Default behavior (`/*`) routes to S3 with gzip/brotli compression and optimized caching.
  - API behavior (`/api*`) routes to the backend operational API (`tenant_operator_lambda` / ALB) with dynamic pass-through and caching disabled.
- **Enterprise Identity & MFA:**
  - Password hashing: PBKDF2-HMAC-SHA256 with 100,000 iterations.
  - Second-Factor: RFC 6238 TOTP with ±30s drift window tolerance.
  - Session Tokens: Signed HMAC-SHA256 tokens with embedded user persona and RBAC claims.

### Enterprise Demo Persona (Local & Staging Evaluation)

| Persona Role   | Email              | Password            | Allowed Capabilities                                         |
| -------------- | ------------------ | ------------------- | ------------------------------------------------------------ |
| **SuperAdmin** | `admin@png261.dev` | `AdminPassword123!` | Full access (Provision, Suspend, Resume, Delete, Audit Logs) |

### Web Console Development

The Super Admin Web Console is decoupled and maintained in the dedicated repository:
👉 [**`FilestoreCloud/console`**](https://github.com/FilestoreCloud/console)

```bash
cd control-panel
npm install
npm run dev
```
