# Super Admin Web Control Panel

Modern, lightweight single-page management application for SaaS Super Admins to monitor infrastructure health, manage tenant lifecycles, and view live telemetry.

---

## 1. Overview & Capabilities

- **Tenant Registry Management:** Real-time visibility into all registered tenants stored in Amazon DynamoDB (`${EnvironmentName}-nextcloud-tenant-registry`).
- **Multi-Factor Authentication (RFC 6238 TOTP):** Native two-step authentication supporting standard authenticator apps (Google Authenticator, 1Password, Authy) with zero external pip dependencies.
- **Granular Role-Based Access Control (RBAC):**
  - `SuperAdmin`: Unrestricted administrative lifecycle and system configuration.
  - `TenantOperator`: Tenant fleet provisioning, scaling, suspension, and resumption (destructive deletion forbidden).
  - `SecurityAuditor`: Read-only telemetry, tenant registry inspection, and compliance audit trail analysis (all mutations prohibited).
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

| File                       | Purpose                                                                                                                        |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| [`index.html`](index.html) | HTML5 single-page application structure, KPI stat cards, tenant data table, modal dialogs, and MFA challenge view              |
| [`app.js`](app.js)         | JavaScript controller handling DynamoDB fetching, TOTP MFA challenge resolution, RBAC UI gating, and live CloudWatch telemetry |
| [`styles.css`](styles.css) | Modern responsive dark-mode styling and authenticator input formatting                                                         |

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

### Enterprise Demo Personas (Local & Staging Evaluation)

| Persona Role        | Email                | Password               | Allowed Capabilities                                                |
| ------------------- | -------------------- | ---------------------- | ------------------------------------------------------------------- |
| **SuperAdmin**      | `admin@png261.dev`   | `AdminPassword123!`    | Full access (Provision, Suspend, Resume, Delete, Audit Logs)        |
| **TenantOperator**  | `ops@png261.dev`     | `OperatorPassword123!` | Fleet operations (Provision, Suspend, Resume); **Delete Forbidden** |
| **SecurityAuditor** | `auditor@png261.dev` | `AuditorPassword123!`  | Read-only compliance & telemetry; **All Mutations Forbidden**       |

### Local Startup (Development)

Run the server runner from the repository root:

```bash
python3 scripts/serve_control_panel.py
```

Then navigate to: **`http://localhost:8080`**
