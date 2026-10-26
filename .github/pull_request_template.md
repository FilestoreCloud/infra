## 📌 Description / Context
<!-- Provide a clear, detailed summary of the changes made and the problem being solved. -->


## 🔗 Related Issues / Tickets
<!-- Link any relevant issues or tickets: e.g. Fixes #123, Closes #456 -->
- Fixes #

---

## 📋 Type of Change
<!-- Please check all that apply: -->
- [ ] 🐛 **Bug Fix** (Non-breaking change that resolves an issue)
- [ ] ✨ **New Feature** (Non-breaking change adding new infrastructure or functionality)
- [ ] 💥 **Breaking Change** (Change requiring migration, stack recreation, or parameter overrides)
- [ ] 🛡️ **Security / DevSecOps** (Vulnerability mitigation, IAM hardening, compliance update)
- [ ] ⚡ **Performance / FinOps** (Cost optimization, query tuning, resource scaling)
- [ ] 🔧 **Refactoring / Maintenance** (Code cleanup without functional changes)
- [ ] 🤖 **CI/CD / Automation** (Workflow updates, testing automation, tooling)
- [ ] 📖 **Documentation** (README, architecture diagrams, inline comments)

---

## 📦 CloudFormation / Architecture Modules Affected
- [ ] `00-cicd` (OIDC Provider & IAM Roles)
- [ ] `01-networking` (VPC, Subnets, Gateways, Endpoints)
- [ ] `02-security` (KMS CMK, Security Groups)
- [ ] `03-storage` (S3 Vault Bucket, EFS Filesystem)
- [ ] `04-database` (Amazon RDS / Aurora PostgreSQL)
- [ ] `05-compute` (ECS Fargate Service, Application Load Balancer)
- [ ] `06-superadmin` (Cognito, DynamoDB, Step Functions, CloudFront)
- [ ] `07-observability` (CloudWatch Alarms, Dashboards, Canary)
- [ ] `root.yaml` (1-Click Nested Orchestrator)
- [ ] Scripts / Tooling (`scripts/manage_dns.py`, `package_lambda.py`, etc.)

---

## 🧪 Testing & Verification
<!-- Describe tests conducted to verify these changes. -->
- [ ] **cfn-lint**: CloudFormation templates validated against `.devsecops/.cfnlintrc.yaml`
- [ ] **Lambda Unit & Moto Tests**: `python3 -m unittest discover -s tests/unit` passed
- [ ] **Terratest Verification**: In-place / unit Go test suites compiled and verified
- [ ] **Playwright E2E**: End-to-end user journeys executed and passed
- [ ] **Target Environment Verified**: Tested live on `dev` or `staging` environment

---

## 🛡️ DevSecOps & Cloud Compliance Checklist
- [ ] **No Secrets**: No AWS credentials, API tokens, passwords, or private keys committed
- [ ] **Least Privilege**: IAM policies grant only minimal required permissions
- [ ] **Non-Breaking Infrastructure**: Verified that CloudFormation updates do not cause unexpected resource replacement (especially RDS, EFS, DynamoDB)
- [ ] **Clean Git History**: Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`, etc.)
- [ ] **Documentation Updated**: Architecture diagrams or docs updated if resources changed
