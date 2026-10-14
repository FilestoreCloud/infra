# Terratest In-Place Infrastructure Verification Suite

Automated Infrastructure as Code (IaC) verification suite using **[Terratest](https://terratest.gruntwork.io/)** (by Gruntwork) for CloudFormation modules on AWS.

---

## 1. Overview: In-Place Testing Mechanism

Unlike traditional ephemeral testing where stacks are created and destroyed twice, **In-Place Testing** evaluates live, active infrastructure that you have already deployed:

- **Single Deployment:** Deploy your infrastructure once via CI/CD or CLI (`dev`, `staging`, `prod`).
- **Zero Destruction (Non-Destructive):** Terratest connects directly to your existing CloudFormation stacks to audit and assert resource states without deleting or modifying them.
- **Graceful Skipping:** If you only deployed Module 01 (`01-networking`), the other module tests gracefully skip without failing your test run.

---

## 2. Directory Layout & Test Matrix

```
tests/terratest/
├── go.mod                          # Go 1.26 module definition with Terratest & AWS SDK v2
├── go.sum                          # Pinned dependency checksums
├── inplace_config.go               # In-Place configuration (ENV, Region, Stack Output resolver)
│
├── inplace_01_networking_test.go   # Stage 1: VPC exists, CIDR match, Public/Private routing, SSM check
├── inplace_02_security_test.go     # Stage 2: Audit Security Groups (ensure port 5432 & 2049 NEVER open to 0.0.0.0/0)
├── inplace_03_storage_test.go      # Stage 3: Audit S3 Vault (Versioning, AES256 SSE, BlockPublicAccess 100%)
├── inplace_04_database_test.go     # Stage 4: Verify RDS PostgreSQL Endpoint & Secrets Manager readiness
├── inplace_05_compute_test.go      # Stage 5: Verify ECS Service, ALB Target Health, and Nextcloud HTTP 200
├── inplace_06_superadmin_test.go   # Stage 6: Verify DynamoDB Tenant Registry status ACTIVE & Admin URLs
├── inplace_07_observability_test.go# Stage 7: Verify CloudWatch Dashboard, SNS alerts, and Metric Alarms
│
├── Makefile                        # Single-command stage runner (make test-all, make test-stage STAGE=01)
├── helpers.go                      # Helpers for optional ephemeral PR sandbox tests
├── networking_module_test.go       # (Optional) Ephemeral sandbox test for PR validation
├── storage_module_test.go          # (Optional) Ephemeral sandbox test for PR validation
├── compute_e2e_test.go             # (Optional) Ephemeral sandbox test for PR validation
└── README.md                       # This guide
```

---

## 3. Running In-Place Tests

### Prerequisites

Configure your AWS credentials or assume role:

```bash
export AWS_REGION="ap-southeast-1"
export ENV="dev" # or "staging", "prod"
```

### Run All In-Place Tests on Current Environment

```bash
cd tests/terratest
go test -v -run "TestInPlace" -timeout 15m
```

### Run In-Place Test on a Specific Module (Stage-by-Stage)

#### 1. Test Module 01 (Networking)

Verifies `${ENV}-nextcloud-01-networking` (VPC CIDR, Multi-AZ Subnets, IGW route, SSM):

```bash
go test -v -run TestInPlaceNetworking
```

#### 2. Test Module 02 (Security)

Audits `${ENV}-nextcloud-02-security` (Restricted ingress on DB/EFS, no public leak):

```bash
go test -v -run TestInPlaceSecurity
```

#### 3. Test Module 03 (Storage)

Audits `${ENV}-nextcloud-03-storage` (S3 Vault encryption, versioning, EFS file system):

```bash
go test -v -run TestInPlaceStorage
```

#### 4. Test Module 04 (Database)

Audits `${ENV}-nextcloud-04-database` (RDS endpoint, Secrets Manager credentials):

```bash
go test -v -run TestInPlaceDatabase
```

#### 5. Test Module 05 (Compute & App Health)

Audits `${ENV}-nextcloud-05-compute` (ECS Fargate running count, ALB Target Group health, `/status.php` HTTP 200):

```bash
go test -v -run TestInPlaceCompute
```

#### 6. Test Module 06 (SuperAdmin & Registry)

Audits `${ENV}-nextcloud-06-superadmin` (DynamoDB table `ACTIVE`, Admin Web URL):

```bash
go test -v -run TestInPlaceSuperAdmin
```

#### 7. Test Module 07 (Observability & Monitoring)

Audits `${ENV}-nextcloud-07-observability` (Central CloudWatch Dashboard, SNS Alert Topic, Metric Alarms):

```bash
go test -v -run TestInPlaceObservability
```

#### 8. Test Module 08 (Chaos & Self-Healing Resilience)

Simulates active Fargate container termination (crash/OOM) and verifies auto-healing MTTR:

```bash
go test -v -run TestInPlaceResilience
```

### Or Use Makefile Shortcuts (Easiest)

```bash
# Run all audit stages
make test-all

# Run specific stage by number or name
make test-stage STAGE=01
make test-stage STAGE=05
make test-stage STAGE=07
make test-stage STAGE=08

# Or trigger chaos resilience test directly
make test-resilience
```

---

## 4. GitHub Actions CI/CD Pipeline

The in-place suite runs right after CloudFormation deployment in `.github/workflows/deploy.yml`:

```yaml
- name: Setup Go for Terratest
  uses: actions/setup-go@v5
  with:
    go-version: "1.26"
    cache-dependency-path: tests/terratest/go.sum

- name: Run Terratest In-Place Verification
  env:
    ENV: ${{ inputs.environment }}
    AWS_REGION: ${{ vars.AWS_REGION || 'ap-southeast-1' }}
  run: |
    cd tests/terratest
    go test -v -run "TestInPlace" -timeout 15m
```
