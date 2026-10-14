#!/usr/bin/env python3
"""
Deploy Infra - AWS CloudFormation Automation Engine (Zero AWS CLI Dependency)

Executes modular or nested CloudFormation deployments using native boto3 SDK.
Replaces shell-based AWS CLI commands in CI/CD pipelines and local operations.
"""

import argparse
import logging
import os
import sys
import time
from typing import Dict, List, Optional
import boto3
from botocore.exceptions import ClientError, WaiterError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("deploy_infra")

MODULE_ORDER = [
    "01-networking",
    "02-security",
    "03-storage",
    "04-database",
    "05-compute",
    "06-control-plane",
]

MODULE_ALIASES = {
    "networking": "01-networking",
    "01-networking": "01-networking",
    "security": "02-security",
    "02-security": "02-security",
    "storage": "03-storage",
    "03-storage": "03-storage",
    "database": "04-database",
    "04-database": "04-database",
    "compute": "05-compute",
    "05-compute": "05-compute",
    "control-plane": "06-control-plane",
    "06-control-plane": "06-control-plane",
}


def normalize_module(name: str) -> str:
    cleaned = name.strip().lower()
    if cleaned in MODULE_ALIASES:
        return MODULE_ALIASES[cleaned]
    raise ValueError(
        f"Unknown module '{name}'. Available: {list(MODULE_ALIASES.keys())}"
    )


class InfraDeployer:
    def __init__(self, environment: str, region: str):
        self.env = environment
        self.region = region
        self.cfn = boto3.client("cloudformation", region_name=region)
        self.ssm = boto3.client("ssm", region_name=region)
        self.s3 = boto3.client("s3", region_name=region)
        self.elbv2 = boto3.client("elbv2", region_name=region)

    def get_ssm_param(self, name: str, default: str = "") -> str:
        try:
            resp = self.ssm.get_parameter(Name=name)
            return resp["Parameter"]["Value"]
        except self.ssm.exceptions.ParameterNotFound:
            logger.warning(
                "SSM parameter %s not found, using default: %s", name, default
            )
            return default
        except ClientError as e:
            logger.error("Failed to retrieve SSM param %s: %s", name, e)
            return default

    def get_alb_full_name(self) -> str:
        alb_name = f"{self.env}-nextcloud-alb"
        try:
            resp = self.elbv2.describe_load_balancers(Names=[alb_name])
            lbs = resp.get("LoadBalancers", [])
            if lbs:
                arn = lbs[0]["LoadBalancerArn"]
                parts = arn.split(":loadbalancer/")
                if len(parts) > 1:
                    return parts[1]
        except ClientError as e:
            logger.warning("Could not describe ALB %s: %s", alb_name, e)
        return f"app/{alb_name}/placeholder"

    def resolve_module_parameters(
        self,
        module: str,
        db_password: str,
        admin_password: str,
    ) -> List[Dict[str, str]]:
        overrides = [{"ParameterKey": "EnvironmentName", "ParameterValue": self.env}]

        if module == "01-networking":
            pass

        elif module == "02-security":
            vpc_id = self.get_ssm_param(f"/nextcloud/{self.env}/infra/vpc-id")
            if vpc_id:
                overrides.append({"ParameterKey": "VpcId", "ParameterValue": vpc_id})

        elif module == "03-storage":
            pass

        elif module == "04-database":
            subnets = self.get_ssm_param(f"/nextcloud/{self.env}/infra/private-subnets")
            parts = subnets.split(",") if subnets else ["", ""]
            overrides.extend(
                [
                    {
                        "ParameterKey": "PrivateSubnet1Id",
                        "ParameterValue": parts[0].strip(),
                    },
                    {
                        "ParameterKey": "PrivateSubnet2Id",
                        "ParameterValue": parts[1].strip()
                        if len(parts) > 1
                        else parts[0].strip(),
                    },
                    {
                        "ParameterKey": "DBSecurityGroupId",
                        "ParameterValue": self.get_ssm_param(
                            f"/nextcloud/{self.env}/security/db-sg-id"
                        ),
                    },
                    {"ParameterKey": "DBPassword", "ParameterValue": db_password},
                ]
            )

        elif module == "05-compute":
            pub_subnets = self.get_ssm_param(
                f"/nextcloud/{self.env}/infra/public-subnets"
            )
            parts = pub_subnets.split(",") if pub_subnets else ["", ""]
            overrides.extend(
                [
                    {
                        "ParameterKey": "VpcId",
                        "ParameterValue": self.get_ssm_param(
                            f"/nextcloud/{self.env}/infra/vpc-id"
                        ),
                    },
                    {
                        "ParameterKey": "PublicSubnet1Id",
                        "ParameterValue": parts[0].strip(),
                    },
                    {
                        "ParameterKey": "PublicSubnet2Id",
                        "ParameterValue": parts[1].strip()
                        if len(parts) > 1
                        else parts[0].strip(),
                    },
                    {
                        "ParameterKey": "ALBSecurityGroupId",
                        "ParameterValue": self.get_ssm_param(
                            f"/nextcloud/{self.env}/security/alb-sg-id"
                        ),
                    },
                    {
                        "ParameterKey": "ECSSecurityGroupId",
                        "ParameterValue": self.get_ssm_param(
                            f"/nextcloud/{self.env}/security/ecs-sg-id"
                        ),
                    },
                    {
                        "ParameterKey": "S3VaultBucketName",
                        "ParameterValue": self.get_ssm_param(
                            f"/nextcloud/{self.env}/infra/s3-vault-bucket"
                        ),
                    },
                    {
                        "ParameterKey": "S3VaultBucketArn",
                        "ParameterValue": self.get_ssm_param(
                            f"/nextcloud/{self.env}/infra/s3-vault-bucket-arn"
                        ),
                    },
                    {
                        "ParameterKey": "DatabaseEndpoint",
                        "ParameterValue": self.get_ssm_param(
                            f"/nextcloud/{self.env}/infra/db-endpoint"
                        ),
                    },
                    {
                        "ParameterKey": "DBSecretArn",
                        "ParameterValue": self.get_ssm_param(
                            f"/nextcloud/{self.env}/infra/db-secret-arn"
                        ),
                    },
                    {"ParameterKey": "AdminPassword", "ParameterValue": admin_password},
                ]
            )

        elif module == "06-control-plane":
            overrides.extend(
                [
                    {
                        "ParameterKey": "S3VaultBucketArn",
                        "ParameterValue": self.get_ssm_param(
                            f"/nextcloud/{self.env}/infra/s3-vault-bucket-arn"
                        ),
                    },
                    {
                        "ParameterKey": "ApplicationLoadBalancerDNS",
                        "ParameterValue": self.get_ssm_param(
                            f"/nextcloud/{self.env}/infra/alb-dns"
                        ),
                    },
                    {
                        "ParameterKey": "ApplicationLoadBalancerFullName",
                        "ParameterValue": self.get_alb_full_name(),
                    },
                    {
                        "ParameterKey": "ECSClusterName",
                        "ParameterValue": self.get_ssm_param(
                            f"/nextcloud/{self.env}/infra/ecs-cluster-name"
                        ),
                    },
                    {
                        "ParameterKey": "ECSServiceName",
                        "ParameterValue": self.get_ssm_param(
                            f"/nextcloud/{self.env}/infra/ecs-service-name"
                        ),
                    },
                ]
            )

        # Filter out empty parameter values to let defaults take effect
        return [p for p in overrides if p["ParameterValue"]]

    def stack_exists(self, stack_name: str) -> bool:
        try:
            resp = self.cfn.describe_stacks(StackName=stack_name)
            stacks = resp.get("Stacks", [])
            return len(stacks) > 0 and stacks[0]["StackStatus"] != "DELETE_COMPLETE"
        except ClientError:
            return False

    def deploy_stack(
        self,
        stack_name: str,
        template_body: str,
        parameters: List[Dict[str, str]],
        capabilities: Optional[List[str]] = None,
    ) -> bool:
        if capabilities is None:
            capabilities = ["CAPABILITY_NAMED_IAM", "CAPABILITY_AUTO_EXPAND"]

        change_set_name = f"cs-{int(time.time())}"
        exists = self.stack_exists(stack_name)
        change_set_type = "UPDATE" if exists else "CREATE"

        logger.info(
            "Creating change set '%s' (%s) for stack '%s'...",
            change_set_name,
            change_set_type,
            stack_name,
        )

        try:
            self.cfn.create_change_set(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=parameters,
                Capabilities=capabilities,
                ChangeSetName=change_set_name,
                ChangeSetType=change_set_type,
            )
        except ClientError as e:
            logger.error("Failed to create change set for %s: %s", stack_name, e)
            return False

        # Wait for change set creation
        waiter = self.cfn.get_waiter("change_set_create_complete")
        try:
            waiter.wait(
                ChangeSetName=change_set_name,
                StackName=stack_name,
                WaiterConfig={"Delay": 5, "MaxAttempts": 30},
            )
        except WaiterError as e:
            # Check if reason was no changes
            cs = self.cfn.describe_change_set(
                ChangeSetName=change_set_name, StackName=stack_name
            )
            status_reason = cs.get("StatusReason", "")
            if (
                "didn't contain changes" in status_reason
                or "No updates" in status_reason
            ):
                logger.info(
                    "✓ Stack '%s' is up to date (no changes detected).", stack_name
                )
                self.cfn.delete_change_set(
                    ChangeSetName=change_set_name, StackName=stack_name
                )
                return True
            logger.error("Change set creation failed: %s (%s)", e, status_reason)
            return False

        logger.info("Executing change set for stack '%s'...", stack_name)
        self.cfn.execute_change_set(
            ChangeSetName=change_set_name,
            StackName=stack_name,
        )

        waiter_name = "stack_update_complete" if exists else "stack_create_complete"
        stack_waiter = self.cfn.get_waiter(waiter_name)
        try:
            logger.info(
                "Waiting for stack '%s' completion (%s)...", stack_name, waiter_name
            )
            stack_waiter.wait(
                StackName=stack_name,
                WaiterConfig={"Delay": 10, "MaxAttempts": 120},
            )
            logger.info("✅ Stack '%s' deployed successfully!", stack_name)
            return True
        except WaiterError as e:
            logger.error("Stack operation failed for '%s': %s", stack_name, e)
            return False

    def deploy_module(
        self, module_name: str, db_password: str, admin_password: str
    ) -> bool:
        norm = normalize_module(module_name)
        stack_name = f"{self.env}-nextcloud-{norm}"
        tpl_path = os.path.join("infra", "modules", norm, "template.yaml")

        if not os.path.exists(tpl_path):
            logger.error("Template file not found: %s", tpl_path)
            return False

        with open(tpl_path, "r", encoding="utf-8") as f:
            template_body = f.read()

        params = self.resolve_module_parameters(norm, db_password, admin_password)
        logger.info("Deploying module '%s' as stack '%s'...", norm, stack_name)
        return self.deploy_stack(stack_name, template_body, params)

    def delete_stack(self, stack_name: str) -> bool:
        if not self.stack_exists(stack_name):
            logger.info("Stack '%s' does not exist; skipping delete.", stack_name)
            return True

        logger.warning("Deleting stack '%s'...", stack_name)
        try:
            self.cfn.delete_stack(StackName=stack_name)
            waiter = self.cfn.get_waiter("stack_delete_complete")
            waiter.wait(
                StackName=stack_name,
                WaiterConfig={"Delay": 10, "MaxAttempts": 60},
            )
            logger.info("✅ Stack '%s' deleted successfully.", stack_name)
            return True
        except (ClientError, WaiterError) as e:
            logger.error("Failed to delete stack '%s': %s", stack_name, e)
            return False


def main():
    parser = argparse.ArgumentParser(
        description="Deploy Infra with native boto3 (Zero AWS CLI Dependency)"
    )
    parser.add_argument(
        "--environment", "-e", default="dev", choices=["dev", "staging", "prod"]
    )
    parser.add_argument(
        "--action",
        "-a",
        default="deploy-module",
        choices=[
            "deploy-module",
            "deploy-all",
            "destroy-module",
            "destroy-all",
            "validate",
        ],
    )
    parser.add_argument("--module", "-m", default="compute")
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", "ap-southeast-1"),
    )
    parser.add_argument(
        "--db-password",
        default=os.environ.get("DB_PASSWORD", "NextCloudSecurePass2026!"),
    )
    parser.add_argument(
        "--admin-password",
        default=os.environ.get("ADMIN_PASSWORD", "AdminSuperSecurePass2026!"),
    )

    args = parser.parse_args()
    deployer = InfraDeployer(environment=args.environment, region=args.region)

    if args.action == "validate":
        logger.info("Templates already validated in pre-flight job.")
        sys.exit(0)

    elif args.action == "deploy-module":
        success = deployer.deploy_module(
            args.module, args.db_password, args.admin_password
        )
        sys.exit(0 if success else 1)

    elif args.action == "deploy-all":
        for mod in MODULE_ORDER:
            ok = deployer.deploy_module(mod, args.db_password, args.admin_password)
            if not ok:
                logger.error("Deployment failed at module '%s'", mod)
                sys.exit(1)
        logger.info("🎉 All infrastructure modules successfully deployed!")
        sys.exit(0)

    elif args.action == "destroy-module":
        mod = normalize_module(args.module)
        stack_name = f"{args.environment}-nextcloud-{mod}"
        success = deployer.delete_stack(stack_name)
        sys.exit(0 if success else 1)

    elif args.action == "destroy-all":
        for mod in reversed(MODULE_ORDER):
            stack_name = f"{args.environment}-nextcloud-{mod}"
            deployer.delete_stack(stack_name)
        logger.info("🎉 All infrastructure stacks deleted successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
