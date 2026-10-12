# Git Hooks (`.githook`)

This directory contains version-controlled, team-shared Git hooks for the **Nextcloud Multi-Tenant SaaS on AWS** repository.

By storing hooks in `.githook` rather than `.git/hooks`, the hooks are versioned with git, tracked across team members, and easily maintained.

---

## Directory Structure

```
.githook/
├── commit-msg                 # Validates Conventional Commits (feat, fix, docs, etc.)
├── pre-commit                 # Protected branch check, secret scan & pre-commit suite
├── pre-push                   # Guards main/production branches before push
├── prepare-commit-msg         # Pre-fills ticket ID from branch name if present
├── post-merge                 # Reminds to update pip dependencies & alerts infra changes
├── setup.sh                   # One-step activation script (git config core.hooksPath .githook)
├── README.md                  # This documentation
└── helpers/                   # Modular helper scripts
    ├── colors.sh              # Terminal ANSI color formatting and logger
    ├── commit-validator.sh    # Conventional Commits regex and rule parser
    ├── git-env.sh             # Branch detection and staging introspection
    └── security-guard.sh      # Accidental secret and merge marker detector
```

---

## Quick Setup

Run the setup script from repository root:

```bash
./.githook/setup.sh
```

Or configure manually using Git:

```bash
git config core.hooksPath .githook
chmod +x .githook/* .githook/helpers/*.sh
```

To verify the configuration:

```bash
git config --get core.hooksPath
# Expected output: .githook
```

---

## Included Hooks

### 1. `pre-commit`

- **Branch Protection:** Prevents direct commits onto protected branches (`main`, `master`).
- **Security & Hygiene Guard:** Blocks commits if private keys (`.pem`, `.key`, `id_rsa`), environment secrets (`.env`), credentials, or unresolved Git merge conflict markers (`<<<<<<<`) are staged.
- **Code Quality:** Triggers the project's existing `.pre-commit-config.yaml` suite (Ruff, Black, Ferret Scan, cfn-lint, licensecheck, eslint, prettier) if `pre-commit` is installed.

### 2. `commit-msg`

- Enforces [Conventional Commits](https://www.conventionalcommits.org/):
  - Formats: `<type>(<scope>): <description>` or `<type>: <description>`
  - Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`
  - Allows standard Git merge commits (`Merge branch...`) and automated git operations.

### 3. `pre-push`

- Checks the destination remote and branch before pushing.
- Warns developers when pushing to protected branches so they double-check CI and review status.

### 4. `prepare-commit-msg`

- Extracts issue/ticket tags from the branch name (e.g. `feat/NC-101-alb` -> `[NC-101]`) and prepends it to the commit message template.

### 5. `post-merge`

- Detects if `requirements.txt` was modified during `git pull` / `git merge` and alerts to run `pip install -r requirements.txt`.
- Alerts when CloudFormation infrastructure templates in `infra/` were updated.

---

## Bypassing Hooks (Emergency Only)

In emergency or automated maintenance scenarios, checks can be bypassed:

| Scenario                           | Bypass Flag                                          |
| ---------------------------------- | ---------------------------------------------------- |
| Bypass all hooks for single commit | `git commit --no-verify -m "..."`                    |
| Allow direct commit to main        | `ALLOW_DIRECT_MAIN=1 git commit -m "..."`            |
| Skip commit-msg format check       | `SKIP_COMMIT_MSG_CHECK=1 git commit -m "..."`        |
| Skip pre-commit linter checks      | `SKIP_PRE_COMMIT=1 git commit -m "..."`              |
| Skip pre-push checks               | `SKIP_PRE_PUSH=1 git push` or `git push --no-verify` |
