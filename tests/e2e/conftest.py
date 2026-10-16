"""Shared fixtures and path configuration for Storix E2E Test Suite."""

from pathlib import Path

# Infrastructure repo root
INFRA_DIR = Path(__file__).resolve().parents[2]
# Workspace / parent root
PROJECT_ROOT = INFRA_DIR.parent

# Component roots
RUNTIME_DIR = PROJECT_ROOT / "runtime"
CONSOLE_DIR = PROJECT_ROOT / "console"
INFRA_MODULES_DIR = INFRA_DIR / "infra" / "modules"
if not INFRA_MODULES_DIR.exists():
    INFRA_MODULES_DIR = INFRA_DIR / "modules"

# Key file paths
DOCKERFILE_PATH = RUNTIME_DIR / "Dockerfile"
HOOK_SCRIPT_PATH = RUNTIME_DIR / "hooks" / "01-setup-ai.sh"
OPCACHE_INI_PATH = RUNTIME_DIR / "config" / "opcache.ini"
NEXTCLOUD_CONFIG_PATH = RUNTIME_DIR / "config" / "nextcloud.config.php"

ROOT_TEMPLATE_PATH = INFRA_DIR / "infra" / "root.yaml"
NETWORKING_TEMPLATE_PATH = INFRA_MODULES_DIR / "01-networking" / "template.yaml"
SECURITY_TEMPLATE_PATH = INFRA_MODULES_DIR / "02-security" / "template.yaml"
STORAGE_TEMPLATE_PATH = INFRA_MODULES_DIR / "03-storage" / "template.yaml"
DATABASE_TEMPLATE_PATH = INFRA_MODULES_DIR / "04-database" / "template.yaml"
COMPUTE_TEMPLATE_PATH = INFRA_MODULES_DIR / "05-compute" / "template.yaml"
SUPERADMIN_TEMPLATE_PATH = INFRA_MODULES_DIR / "06-superadmin" / "template.yaml"
LAMBDA_SRC_PATH = INFRA_MODULES_DIR / "06-superadmin" / "tenant_operator_lambda.py"
PACKAGE_LAMBDA_SCRIPT_PATH = INFRA_DIR / "scripts" / "package_lambda.py"

TENANT_SHOW_PATH = CONSOLE_DIR / "src" / "pages" / "tenants" / "show.tsx"
TENANT_TABS_DIR = CONSOLE_DIR / "src" / "pages" / "tenants" / "tabs"
TENANT_LIST_PATH = CONSOLE_DIR / "src" / "pages" / "tenants" / "list.tsx"
DATA_PROVIDER_PATH = CONSOLE_DIR / "src" / "providers" / "dataProvider.ts"
AUTH_PROVIDER_PATH = CONSOLE_DIR / "src" / "providers" / "authProvider.ts"
ACCESS_CONTROL_PATH = CONSOLE_DIR / "src" / "providers" / "accessControlProvider.ts"
WEBHOOKS_PATH = CONSOLE_DIR / "src" / "pages" / "settings" / "webhooks.tsx"
LOGIN_PAGE_PATH = CONSOLE_DIR / "src" / "pages" / "login" / "index.tsx"
