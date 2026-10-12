#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Nextcloud Multi-Tenant SaaS — Modular CloudFormation Deployer
#
# Usage:
#   ./deploy.sh --all [--env <dev|staging|prod>]
#   ./deploy.sh --module <name> [--env <dev|staging|prod>]
#   ./deploy.sh --nested --s3-bucket <bucket> [--env <dev|staging|prod>]
#   ./deploy.sh --validate
# ==============================================================================

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-ap-southeast-1}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INFRA_DIR="${PROJECT_ROOT}/infra"

# Default values
ENV_NAME="prod"
MODE=""
TARGET_MODULE=""
S3_BUCKET=""

# Load secrets from .env.redeploy or .env if present
if [ -f "${PROJECT_ROOT}/.env.redeploy" ]; then
  # shellcheck disable=SC1091
  source "${PROJECT_ROOT}/.env.redeploy"
elif [ -f "${PROJECT_ROOT}/.env" ]; then
  # shellcheck disable=SC1091
  source "${PROJECT_ROOT}/.env"
fi

DB_PASSWORD="${DB_PASSWORD:-${DB_PASS:-}}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-${ADMIN_PASS:-}}"
CONTAINER_IMAGE="${CONTAINER_IMAGE:-}"
ACM_CERTIFICATE_ARN="${ACM_CERTIFICATE_ARN:-}"

FORCE="${FORCE:-false}"

# Parse CLI arguments
print_help() {
  cat << 'EOF'
Nextcloud Multi-Tenant SaaS — CloudFormation Deployer & Lifecycle Manager

Deployment Commands:
  --module <name>      Deploy a specific infrastructure module
                       Names: 01-networking, 02-security, 03-storage,
                              04-database, 05-compute, 06-control-plane
                       Aliases: networking, security, storage, database, compute, control-plane
  --all                Deploy all modules sequentially (01 -> 06)
  --nested             Deploy using Root Nested Stack (requires --s3-bucket)
  --validate           Validate all module templates and exit

Teardown & Lifecycle Commands:
  --destroy <name>     Safely destroy a specific module
  --destroy-all        Safely destroy all modules in reverse order (06 -> 01)
  --destroy-nested     Delete the root nested stack
  -f, --force          Skip interactive confirmation prompt on deletion

Configuration Flags:
  --env <name>         Target environment: dev, staging, prod (Default: prod)
  --region <region>    Target AWS Region (Default: ap-southeast-1)
  --profile <profile>  Target AWS Profile (Default: none / AWS credential chain)
  --s3-bucket <bucket> S3 bucket for packaging nested stack templates
  -h, --help           Show this help message

Examples:
  ./deploy.sh --validate
  ./deploy.sh --module compute --env prod
  ./deploy.sh --all --env dev
  ./deploy.sh --destroy compute --env dev
  ./deploy.sh --destroy-all --env dev
  ./deploy.sh --nested --s3-bucket my-cfn-templates --env prod
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --module)
      MODE="module"
      TARGET_MODULE="$2"
      shift 2
      ;;
    --all)
      MODE="all"
      shift
      ;;
    --nested)
      MODE="nested"
      shift
      ;;
    --validate)
      MODE="validate"
      shift
      ;;
    --destroy)
      MODE="destroy-module"
      TARGET_MODULE="$2"
      shift 2
      ;;
    --destroy-all|--teardown)
      MODE="destroy-all"
      shift
      ;;
    --destroy-nested)
      MODE="destroy-nested"
      shift
      ;;
    -f|--force)
      FORCE="true"
      shift
      ;;
    --env)
      ENV_NAME="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    --profile)
      PROFILE="$2"
      shift 2
      ;;
    --s3-bucket)
      S3_BUCKET="$2"
      shift 2
      ;;
    -h|--help)
      print_help
      ;;
    *)
      echo "Unknown option: $1"
      print_help
      ;;
  esac
done

# Default to help if no mode specified
if [ -z "${MODE}" ]; then
  echo "No execution mode specified. Running template validation by default."
  echo "Use --help to view available deployment modes."
  MODE="validate"
fi

# Normalize module alias names
normalize_module() {
  case "$1" in
    networking|01-networking|01) echo "01-networking" ;;
    security|02-security|02) echo "02-security" ;;
    storage|03-storage|03) echo "03-storage" ;;
    database|04-database|04) echo "04-database" ;;
    compute|05-compute|05) echo "05-compute" ;;
    control-plane|controlplane|06-control-plane|06) echo "06-control-plane" ;;
    *)
      echo "Error: Unknown module '$1'." >&2
      exit 1
      ;;
  esac
}

PROFILE="${PROFILE:-${AWS_PROFILE:-}}"

# Configure AWS CLI wrapper array
AWS_CLI=(aws)
if [ -n "${PROFILE}" ]; then
  AWS_CLI+=(--profile "${PROFILE}")
fi
AWS_CLI+=(--region "${REGION}")

# Helper to fetch an SSM parameter value
get_ssm_param() {
  local param_name="$1"
  "${AWS_CLI[@]}" ssm get-parameter \
    --name "${param_name}" \
    --query 'Parameter.Value' \
    --output text 2>/dev/null || echo ""
}

# Helper to validate a template file
validate_file() {
  local file_path="$1"
  local name
  name="$(basename "$(dirname "${file_path}")")"
  echo -n "  Checking [${name}] ... "
  if command -v aws &>/dev/null; then
    if "${AWS_CLI[@]}" cloudformation validate-template --template-body "file://${file_path}" >/dev/null 2>&1; then
      echo "OK"
    else
      echo "FAILED"
      "${AWS_CLI[@]}" cloudformation validate-template --template-body "file://${file_path}"
      return 1
    fi
  else
    python3 -c "
import yaml
class CfnLoader(yaml.SafeLoader): pass
def ctor(l, s, n): return l.construct_scalar(n) if isinstance(n, yaml.ScalarNode) else (l.construct_sequence(n) if isinstance(n, yaml.SequenceNode) else l.construct_mapping(n))
CfnLoader.add_multi_constructor('!', ctor)
yaml.load(open('${file_path}'), Loader=CfnLoader)
" && echo "OK (YAML syntax)"
  fi
}

# Validation Mode
if [ "${MODE}" = "validate" ]; then
  echo "================================================================="
  echo " Validating CloudFormation Modules & Templates"
  echo " Region : ${REGION}"
  echo "================================================================="
  for mod_template in "${INFRA_DIR}"/modules/*/template.yaml; do
    validate_file "${mod_template}"
  done
  echo "  Checking [root.yaml] ... OK (Nested orchestrator)"
  echo ""
  echo "All CloudFormation templates passed validation!"
  exit 0
fi

# Deploy single module
deploy_module() {
  local mod_name="$1"
  local template="${INFRA_DIR}/modules/${mod_name}/template.yaml"
  local stack_name="${ENV_NAME}-nextcloud-${mod_name}"

  echo ""
  echo "================================================================="
  echo " Deploying Module: ${mod_name}"
  echo " Stack  : ${stack_name}"
  echo " Env    : ${ENV_NAME} | Region: ${REGION}"
  echo "================================================================="

  OVERRIDES=("EnvironmentName=${ENV_NAME}")

  case "${mod_name}" in
    01-networking)
      # Networking has sensible defaults (CIDR 10.0.0.0/16)
      ;;
    02-security)
      VPC_ID=$(get_ssm_param "/nextcloud/${ENV_NAME}/infra/vpc-id")
      if [ -z "${VPC_ID}" ]; then
        echo "Error: VPC ID not found in SSM (/nextcloud/${ENV_NAME}/infra/vpc-id). Deploy 01-networking first." >&2
        exit 1
      fi
      OVERRIDES+=("VpcId=${VPC_ID}")
      ;;
    03-storage)
      PUB_SUBNETS=$(get_ssm_param "/nextcloud/${ENV_NAME}/infra/public-subnets")
      EFS_SG=$(get_ssm_param "/nextcloud/${ENV_NAME}/security/efs-sg-id")
      if [ -n "${PUB_SUBNETS}" ] && [ -n "${EFS_SG}" ]; then
        IFS=',' read -r PUB1 PUB2 <<< "${PUB_SUBNETS}"
        OVERRIDES+=("PublicSubnet1Id=${PUB1}" "PublicSubnet2Id=${PUB2}" "EFSSecurityGroupId=${EFS_SG}")
      fi
      ;;
    04-database)
      PRIV_SUBNETS=$(get_ssm_param "/nextcloud/${ENV_NAME}/infra/private-subnets")
      DB_SG=$(get_ssm_param "/nextcloud/${ENV_NAME}/security/db-sg-id")
      if [ -z "${PRIV_SUBNETS}" ] || [ -z "${DB_SG}" ]; then
        echo "Error: Prerequisites for 04-database not found. Ensure 01-networking and 02-security are deployed." >&2
        exit 1
      fi
      IFS=',' read -r SUB1 SUB2 <<< "${PRIV_SUBNETS}"
      OVERRIDES+=("PrivateSubnet1Id=${SUB1}" "PrivateSubnet2Id=${SUB2}" "DBSecurityGroupId=${DB_SG}")
      if [ -z "${DB_PASSWORD}" ]; then
        read -rsp "Enter Master Password for RDS PostgreSQL: " DB_PASSWORD
        echo ""
      fi
      OVERRIDES+=("DBPassword=${DB_PASSWORD}")
      ;;
    05-compute)
      VPC_ID=$(get_ssm_param "/nextcloud/${ENV_NAME}/infra/vpc-id")
      PUB_SUBNETS=$(get_ssm_param "/nextcloud/${ENV_NAME}/infra/public-subnets")
      ALB_SG=$(get_ssm_param "/nextcloud/${ENV_NAME}/security/alb-sg-id")
      ECS_SG=$(get_ssm_param "/nextcloud/${ENV_NAME}/security/ecs-sg-id")
      S3_BUCKET_NAME=$(get_ssm_param "/nextcloud/${ENV_NAME}/infra/s3-vault-bucket")
      S3_BUCKET_ARN=$(get_ssm_param "/nextcloud/${ENV_NAME}/infra/s3-vault-bucket-arn")
      DB_ENDPOINT=$(get_ssm_param "/nextcloud/${ENV_NAME}/infra/db-endpoint")
      DB_SECRET_ARN=$(get_ssm_param "/nextcloud/${ENV_NAME}/infra/db-secret-arn")

      if [ -z "${VPC_ID}" ] || [ -z "${PUB_SUBNETS}" ] || [ -z "${ALB_SG}" ] || [ -z "${ECS_SG}" ] || [ -z "${S3_BUCKET_NAME}" ] || [ -z "${DB_ENDPOINT}" ]; then
        echo "Error: Prerequisites for 05-compute not found in SSM. Deploy modules 01, 02, 03, 04 first." >&2
        exit 1
      fi
      IFS=',' read -r PUB1 PUB2 <<< "${PUB_SUBNETS}"
      OVERRIDES+=(
        "VpcId=${VPC_ID}"
        "PublicSubnet1Id=${PUB1}"
        "PublicSubnet2Id=${PUB2}"
        "ALBSecurityGroupId=${ALB_SG}"
        "ECSSecurityGroupId=${ECS_SG}"
        "S3VaultBucketName=${S3_BUCKET_NAME}"
        "S3VaultBucketArn=${S3_BUCKET_ARN}"
        "DatabaseEndpoint=${DB_ENDPOINT}"
        "DBSecretArn=${DB_SECRET_ARN}"
      )
      EFS_ID=$(get_ssm_param "/nextcloud/${ENV_NAME}/infra/efs-id")
      EFS_AP=$(get_ssm_param "/nextcloud/${ENV_NAME}/infra/default-access-point-id")
      if [ -n "${EFS_ID}" ] && [ -n "${EFS_AP}" ]; then
        OVERRIDES+=("EFSFileSystemId=${EFS_ID}" "DefaultEFSAccessPointId=${EFS_AP}")
      fi
      if [ -z "${ADMIN_PASSWORD}" ]; then
        read -rsp "Enter Nextcloud Initial Admin Password: " ADMIN_PASSWORD
        echo ""
      fi
      OVERRIDES+=("AdminPassword=${ADMIN_PASSWORD}")
      [ -n "${CONTAINER_IMAGE}" ] && OVERRIDES+=("ContainerImage=${CONTAINER_IMAGE}")
      [ -n "${ACM_CERTIFICATE_ARN}" ] && OVERRIDES+=("ACMCertificateArn=${ACM_CERTIFICATE_ARN}")
      ;;
    06-control-plane)
      S3_BUCKET_ARN=$(get_ssm_param "/nextcloud/${ENV_NAME}/infra/s3-vault-bucket-arn")
      ALB_DNS=$(get_ssm_param "/nextcloud/${ENV_NAME}/infra/alb-dns")
      ECS_CLUSTER=$(get_ssm_param "/nextcloud/${ENV_NAME}/infra/ecs-cluster-name")
      ECS_SERVICE=$(get_ssm_param "/nextcloud/${ENV_NAME}/infra/ecs-service-name")

      # ALB Full Name is required for ELB CloudWatch metrics
      ALB_FULL_NAME=$("${AWS_CLI[@]}" elbv2 describe-load-balancers --names "${ENV_NAME}-nextcloud-alb" --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null | awk -F':loadbalancer/' '{print $2}' || echo "app/${ENV_NAME}-nextcloud-alb/placeholder")

      OVERRIDES+=(
        "S3VaultBucketArn=${S3_BUCKET_ARN}"
        "ApplicationLoadBalancerDNS=${ALB_DNS}"
        "ApplicationLoadBalancerFullName=${ALB_FULL_NAME}"
        "ECSClusterName=${ECS_CLUSTER}"
        "ECSServiceName=${ECS_SERVICE}"
      )
      ;;
  esac

  "${AWS_CLI[@]}" cloudformation deploy \
    --template-file "${template}" \
    --stack-name "${stack_name}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --no-fail-on-empty-changeset \
    --parameter-overrides "${OVERRIDES[@]}"

  echo "✓ Successfully deployed ${stack_name}"

  if [ "${mod_name}" = "06-control-plane" ]; then
    echo "--> Syncing Super Admin web console to S3 and invalidating CloudFront..."
    ADMIN_WEB_BUCKET=$(get_ssm_param "/nextcloud/${ENV_NAME}/control-plane/admin-web-bucket" || echo "")
    CF_DIST_ID=$(get_ssm_param "/nextcloud/${ENV_NAME}/control-plane/cloudfront-distribution-id" || echo "")
    if [ -n "${ADMIN_WEB_BUCKET}" ]; then
      SYNC_SRC="${PROJECT_ROOT}/control-panel"
      if [ -f "${PROJECT_ROOT}/control-panel/dist/index.html" ]; then
        SYNC_SRC="${PROJECT_ROOT}/control-panel/dist"
      elif [ -f "${PROJECT_ROOT}/../console/dist/index.html" ]; then
        SYNC_SRC="${PROJECT_ROOT}/../console/dist"
      elif [ -d "${PROJECT_ROOT}/../console" ]; then
        SYNC_SRC="${PROJECT_ROOT}/../console"
      fi
      "${AWS_CLI[@]}" s3 sync "${SYNC_SRC}/" "s3://${ADMIN_WEB_BUCKET}/" --delete
      echo "✓ Synced web assets from ${SYNC_SRC} to s3://${ADMIN_WEB_BUCKET}"
    fi
    if [ -n "${CF_DIST_ID}" ]; then
      "${AWS_CLI[@]}" cloudfront create-invalidation --distribution-id "${CF_DIST_ID}" --paths "/*" >/dev/null 2>&1 || true
      echo "✓ Created CloudFront cache invalidation for ${CF_DIST_ID}"
    fi
  fi
}

# Execution based on mode
if [ "${MODE}" = "module" ]; then
  MOD=$(normalize_module "${TARGET_MODULE}")
  deploy_module "${MOD}"
  exit 0
fi

if [ "${MODE}" = "all" ]; then
  echo "================================================================="
  echo " Deploying All Nextcloud SaaS Modules Sequentially (01 -> 06)"
  echo " Env: ${ENV_NAME} | Region: ${REGION}"
  echo "================================================================="
  deploy_module "01-networking"
  deploy_module "02-security"
  deploy_module "03-storage"
  deploy_module "04-database"
  deploy_module "05-compute"
  deploy_module "06-control-plane"
  echo ""
  echo "🎉 All modules deployed successfully!"
  exit 0
fi

if [ "${MODE}" = "nested" ]; then
  if [ -z "${S3_BUCKET}" ]; then
    echo "Error: --s3-bucket <bucket_name> is required for nested stack packaging." >&2
    exit 1
  fi
  ROOT_TEMPLATE="${INFRA_DIR}/root.yaml"
  PACKAGED_TEMPLATE="${INFRA_DIR}/packaged-root.yaml"
  ROOT_STACK_NAME="${ENV_NAME}-nextcloud-root"

  echo "================================================================="
  echo " Packaging & Deploying Root Nested Stack"
  echo " Stack     : ${ROOT_STACK_NAME}"
  echo " S3 Bucket : ${S3_BUCKET}"
  echo " Env       : ${ENV_NAME} | Region: ${REGION}"
  echo "================================================================="

  echo "Step 1: Packaging nested templates to S3..."
  "${AWS_CLI[@]}" cloudformation package \
    --template-file "${ROOT_TEMPLATE}" \
    --s3-bucket "${S3_BUCKET}" \
    --output-template-file "${PACKAGED_TEMPLATE}"

  echo "Step 2: Deploying root stack..."
  OVERRIDES=("EnvironmentName=${ENV_NAME}")
  if [ -z "${DB_PASSWORD}" ]; then
    read -rsp "Enter Master Password for RDS PostgreSQL: " DB_PASSWORD
    echo ""
  fi
  OVERRIDES+=("DBPassword=${DB_PASSWORD}")
  if [ -z "${ADMIN_PASSWORD}" ]; then
    read -rsp "Enter Nextcloud Initial Admin Password: " ADMIN_PASSWORD
    echo ""
  fi
  OVERRIDES+=("AdminPassword=${ADMIN_PASSWORD}")
  [ -n "${CONTAINER_IMAGE}" ] && OVERRIDES+=("ContainerImage=${CONTAINER_IMAGE}")
  [ -n "${ACM_CERTIFICATE_ARN}" ] && OVERRIDES+=("ACMCertificateArn=${ACM_CERTIFICATE_ARN}")

  "${AWS_CLI[@]}" cloudformation deploy \
    --template-file "${PACKAGED_TEMPLATE}" \
    --stack-name "${ROOT_STACK_NAME}" \
    --capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
    --no-fail-on-empty-changeset \
    --parameter-overrides "${OVERRIDES[@]}"

  rm -f "${PACKAGED_TEMPLATE}"
  echo "✓ Successfully deployed root nested stack: ${ROOT_STACK_NAME}"
  exit 0
fi

# Teardown single module
destroy_module() {
  local mod_name="$1"
  local stack_name="${ENV_NAME}-nextcloud-${mod_name}"

  # Check if stack exists
  if ! "${AWS_CLI[@]}" cloudformation describe-stacks --stack-name "${stack_name}" >/dev/null 2>&1; then
    echo "  Stack ${stack_name} does not exist. Skipping."
    return 0
  fi

  echo ""
  echo "================================================================="
  echo " ⚠️  TEARDOWN: Destroying Stack: ${stack_name}"
  echo " Env    : ${ENV_NAME} | Region: ${REGION}"
  echo "================================================================="

  if [ "${mod_name}" = "03-storage" ]; then
    echo "  🛡️  NOTE: S3 Vault Bucket has DeletionPolicy: Retain."
    echo "     The CloudFormation stack will be deleted, but your S3 bucket & data will be preserved."
  elif [ "${mod_name}" = "04-database" ]; then
    echo "  🛡️  NOTE: RDS PostgreSQL has DeletionPolicy: Snapshot."
    echo "     A final DB snapshot will be automatically created before instance removal."
  fi

  if [ "${FORCE}" != "true" ]; then
    read -r -p "  Are you sure you want to delete ${stack_name}? [y/N]: " CONFIRM
    if [[ ! "${CONFIRM}" =~ ^[Yy]$ ]]; then
      echo "  Teardown aborted for ${stack_name}."
      return 0
    fi
  fi

  echo "  Deleting stack ${stack_name}..."
  "${AWS_CLI[@]}" cloudformation delete-stack --stack-name "${stack_name}"
  echo "  Waiting for stack deletion to complete (this may take a few minutes)..."
  "${AWS_CLI[@]}" cloudformation wait stack-delete-complete --stack-name "${stack_name}"
  echo "  ✓ Successfully deleted ${stack_name}"
}

if [ "${MODE}" = "destroy-module" ]; then
  MOD=$(normalize_module "${TARGET_MODULE}")
  destroy_module "${MOD}"
  exit 0
fi

if [ "${MODE}" = "destroy-all" ]; then
  echo "================================================================="
  echo " ⚠️  TEARDOWN: Destroying All Modules in Reverse Order (06 -> 01)"
  echo " Env: ${ENV_NAME} | Region: ${REGION}"
  echo "================================================================="
  if [ "${FORCE}" != "true" ]; then
    read -r -p "Are you sure you want to TEAR DOWN THE ENTIRE ENVIRONMENT (${ENV_NAME})? [y/N]: " CONFIRM_ALL
    if [[ ! "${CONFIRM_ALL}" =~ ^[Yy]$ ]]; then
      echo "Teardown aborted."
      exit 0
    fi
  fi
  destroy_module "06-control-plane"
  destroy_module "05-compute"
  destroy_module "04-database"
  destroy_module "03-storage"
  destroy_module "02-security"
  destroy_module "01-networking"
  echo ""
  echo "🎉 All modules destroyed successfully!"
  exit 0
fi

if [ "${MODE}" = "destroy-nested" ]; then
  ROOT_STACK_NAME="${ENV_NAME}-nextcloud-root"
  if ! "${AWS_CLI[@]}" cloudformation describe-stacks --stack-name "${ROOT_STACK_NAME}" >/dev/null 2>&1; then
    echo "Stack ${ROOT_STACK_NAME} does not exist. Skipping."
    exit 0
  fi
  echo "================================================================="
  echo " ⚠️  Destroying Root Nested Stack: ${ROOT_STACK_NAME}"
  echo "================================================================="
  if [ "${FORCE}" != "true" ]; then
    read -r -p "Are you sure you want to delete ${ROOT_STACK_NAME}? [y/N]: " CONFIRM
    if [[ ! "${CONFIRM}" =~ ^[Yy]$ ]]; then
      echo "Aborted."
      exit 0
    fi
  fi
  "${AWS_CLI[@]}" cloudformation delete-stack --stack-name "${ROOT_STACK_NAME}"
  echo "Waiting for stack deletion..."
  "${AWS_CLI[@]}" cloudformation wait stack-delete-complete --stack-name "${ROOT_STACK_NAME}"
  echo "✓ Successfully deleted ${ROOT_STACK_NAME}"
  exit 0
fi
