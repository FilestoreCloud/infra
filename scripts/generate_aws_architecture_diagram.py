#!/usr/bin/env python3
"""
Nextcloud Multi-Tenant SaaS on AWS — Architecture as Code Diagram Generator
Using the official Python 'diagrams' (AWS Mingrammer) library.

Architecture Components:
- Edge & Perimeter Security: Route 53 (DNS Alias), AWS WAFv2 (WebACL), ACM (Wildcard TLS 1.3)
- Ingress: Multi-AZ Application Load Balancer with Host-Header Priority Routing
- Compute Tier: ECS Fargate Containers per Tenant (service-acme, service-marvel + LiteLLM sidecar)
- Storage Tier: Amazon EFS Access Points (POSIX 33:33) + Amazon S3 Vault with S3 Gateway Endpoint
- Database Tier: Isolated Amazon RDS PostgreSQL 16.10 catalogs (nc_acme, nc_marvel)
- AI Tier: Amazon Bedrock AI Hub (Claude 3.5 Sonnet / Titan v2) with SigV4 IAM Task Role
- Control Plane: SaaS Super Admin Control Panel Lambda, SSM Runbook, DynamoDB Registry, CloudWatch Telemetry
"""

import os
import shutil
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.network import Route53, ALB, Endpoint
from diagrams.aws.security import WAF, CertificateManager
from diagrams.aws.compute import Fargate, Lambda
from diagrams.aws.storage import EFS, S3
from diagrams.aws.database import RDS, Dynamodb
from diagrams.aws.management import SystemsManager, Cloudwatch
from diagrams.aws.ml import Bedrock
from diagrams.onprem.client import Users

def generate_diagram(output_path="/tmp/aws_cloud_architecture"):
    graph_attr = {
        "fontsize": "24",
        "bgcolor": "white",
        "pad": "0.6",
        "splines": "ortho",
        "nodesep": "0.7",
        "ranksep": "0.9",
        "compound": "true",
    }

    node_attr = {
        "fontsize": "10.5",
        "fontname": "Helvetica",
    }

    edge_attr = {
        "fontsize": "9.5",
        "fontname": "Helvetica",
    }

    with Diagram(
        "Nextcloud Multi-Tenant SaaS — AWS Production Architecture (Diagram as Code)",
        show=False,
        direction="TB",
        filename=output_path,
        graph_attr=graph_attr,
        node_attr=node_attr,
        edge_attr=edge_attr,
    ):
        with Cluster("Internet Clients & Custom Domains"):
            users_acme = Users("Tenant 1: Acme Users\nacme.png261.dev\n(Web, Desktop Sync, WebDAV)")
            users_marvel = Users("Tenant 2: Marvel Users\nmarvel.png261.dev\n(Web, Desktop Sync, WebDAV)")
            admin_user = Users("SaaS Super Admin\nadmin.png261.dev\n(Fleet Ops & Telemetry)")

        with Cluster("Edge Ingress & Perimeter Security (DNS, SSL/TLS, WAF)"):
            dns = Route53("Amazon Route 53 (DNS)\nHosted Zone: png261.dev\nWildcard *.png261.dev ALIAS")
            acm = CertificateManager("AWS ACM (TLS 1.3)\nWildcard *.png261.dev\nAuto DNS Validation")
            waf = WAF("AWS WAFv2 (WebACL)\nScope: Regional (ALB)\n1. OWASP Top 10 CommonRuleSet\n2. BadInputs (PROPFIND allowed)\n3. SQLi Protection\n4. IP Rate Limit: 2000 req / 5 min")

        with Cluster("AWS Cloud: ap-southeast-1 (Singapore Region)"):
            with Cluster("VPC: 10.0.0.0/16 (Lean Zero-NAT Multi-AZ Architecture)"):
                with Cluster("Public Subnets AZ-a & AZ-b (Ingress & Zero-NAT Egress)"):
                    alb = ALB("Application Load Balancer (ALB)\nDual-AZ Ingress · Port 80 (301) & 443\nWildcard TLS 1.3 · Host-Header Priority Routing\nHealth Check: /status.php (200 OK)")

                with Cluster("Independent Tenant Compute Tier (ECS Fargate Containers)"):
                    with Cluster("Tenant 1: Acme Dedicated Compute"):
                        fargate_acme = Fargate("ECS Task: service-acme\n(1–4 Auto-scaled Tasks)\nNextcloud 30 Hub · CPU > 70%")
                        efs_acme = EFS("Amazon EFS AP\n/tenants/acme/config\nPOSIX UID 33:33")

                    with Cluster("Tenant 2: Marvel Dedicated Compute"):
                        fargate_marvel = Fargate("ECS Task: service-marvel\n(1–4 Auto-scaled Tasks)\nLiteLLM Bedrock Bridge (127.0.0.1:4000)")
                        efs_marvel = EFS("Amazon EFS AP\n/tenants/marvel/config\nPOSIX UID 33:33")

                    s3_gw = Endpoint("S3 Gateway Endpoint (Module 01)\nZero-NAT Private Route (Free)\nPrefix List: pl-6fa54006")

                with Cluster("Private Database Tier (Amazon RDS PostgreSQL 16.10)"):
                    rds = RDS("Amazon RDS PostgreSQL 16.10\n(db.t4g.micro Graviton2, 20GB gp3)\nInbound 5432 Locked to ECS SG\nnc_acme & nc_marvel Isolated Catalogs")

            with Cluster("Managed Services & SaaS Control Plane (Modules 03 & 06)"):
                cp_lambda = Lambda("Super Admin Control Panel\nhttps://admin.png261.dev\nFastAPI / Lambda (Priority 5 Target)\nSigned JWT Sessions")
                bedrock = Bedrock("Amazon Bedrock AI Hub\nClaude 3.5 Sonnet / Titan v2\nZero-Data-Retention Engine\nSigV4 IAM Task Role Policy")
                s3_vault = S3("Amazon S3 Vault Bucket (Module 03)\ns3://prod-nextcloud-vault-.../\ntenants/acme/*, marvel/*\nStandard → IA → Glacier")
                ddb = Dynamodb("DynamoDB Tenant Registry\nprod-nextcloud-tenant-registry\nPay-per-Request On-Demand\nState: ACTIVE, SUSPENDED")
                ssm = SystemsManager("AWS Systems Manager (SSM)\nprod-Tenant-Lifecycle-Operator\nAutomated Lifecycle Runbook")
                cw = Cloudwatch("Amazon CloudWatch Observability\nNextcloud-SaaS-Control-Plane\nReal-time Telemetry (15s pulse)\nECS CPU/Mem & ALB Metrics")

        # Ingress Traffic Routing
        users_acme >> Edge(label="DNS Query: acme.png261.dev", color="#2E86C1") >> dns
        users_marvel >> Edge(label="DNS Query: marvel.png261.dev", color="#2E86C1") >> dns
        admin_user >> Edge(label="DNS Query: admin.png261.dev", color="#E74C3C") >> dns

        dns >> Edge(label="A-Record Alias (*.png261.dev → ALB)", color="#8C4FFF", style="dashed") >> waf
        acm >> Edge(label="Wildcard TLS 1.3 Cert", color="#DD344C", style="dashed") >> waf
        waf >> Edge(label="HTTPS Filtered by WAFv2", color="#DD344C", penwidth="2.5") >> alb

        # Host-Header Priority Routing
        alb >> Edge(label="Priority 10: Host=acme.*", color="#27AE60", penwidth="2.0") >> fargate_acme
        alb >> Edge(label="Priority 20: Host=marvel.*", color="#1ABC9C", penwidth="2.0") >> fargate_marvel
        alb >> Edge(label="Priority 5: Host=admin.*", color="#E74C3C", penwidth="2.0") >> cp_lambda

        # Storage & Persistence Connections
        fargate_acme >> Edge(label="NFS 2049", color="#277A16", penwidth="1.8") >> efs_acme
        fargate_marvel >> Edge(label="NFS 2049", color="#277A16", penwidth="1.8") >> efs_marvel

        fargate_acme >> Edge(label="Direct S3 Route", color="#7AA116") >> s3_gw
        fargate_marvel >> Edge(label="Direct S3 Route", color="#7AA116") >> s3_gw
        s3_gw >> Edge(label="Zero-NAT Private Route (s3://vault/tenants/*)", color="#7AA116", penwidth="2.2") >> s3_vault

        # Database Connections
        fargate_acme >> Edge(label="nc_acme (Port 5432)", color="#8E44AD", penwidth="1.8") >> rds
        fargate_marvel >> Edge(label="nc_marvel (Port 5432)", color="#8E44AD", penwidth="1.8") >> rds

        # Bedrock AI Connection (SigV4 IAM)
        fargate_marvel >> Edge(label="boto3 SigV4 / Zero-Retention", color="#01A88D", penwidth="2.0") >> bedrock

        # Control Plane Operations
        cp_lambda >> Edge(label="Trigger Lifecycle Runbook", color="#E74C3C", penwidth="1.8") >> ssm
        ssm >> Edge(label="State Saga (PROVISION/SUSPEND)", color="#E7157B", style="dashed") >> ddb
        cw >> Edge(label="Telemetry API (GetMetricData)", color="#E7157B", style="dashed") >> cp_lambda

    print(f"Generated AWS Architecture Diagram at {output_path}.png")
    return f"{output_path}.png"

if __name__ == "__main__":
    generated_png = generate_diagram("/tmp/aws_cloud_architecture")
    
    # Copy to destination paths
    targets = [
        "reports/2026-10-05/imgs/diagrams/aws_cloud_architecture.png",
        "docs/images/nextcloud_architecture.png",
        "reports/2026-10-05/imgs/diagrams/nextcloud_architecture.png"
    ]
    for target in targets:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(generated_png, target)
        print(f"Copied to {target}")
