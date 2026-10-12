# Module 01: Networking & VPC

## Overview
Deploys the foundational Multi-AZ Virtual Private Cloud (VPC) network topology for Nextcloud Multi-Tenant SaaS on AWS.

The architecture implements a **Zero-NAT Gateway** cost-optimized design:
* **Cost Efficiency:** Eliminates AWS NAT Gateway hourly fees and data processing charges (~$64+/month across 2 AZs saved).
* **Direct S3 Transfer:** Utilizes a complimentary **S3 Gateway VPC Endpoint** (`com.amazonaws.${AWS::Region}.s3`) attached to all public and private route tables, providing free, high-throughput, private access to tenant object storage.
* **Network Segmentation:** Public subnets host internet-facing ingress (ALB) and pooled compute tasks with direct internet egress, while private subnets strictly isolate database workloads.

---

## Architecture Topology

```
VPC: 10.0.0.0/16
├── Internet Gateway (IGW)
├── Public Route Table (0.0.0.0/0 -> IGW)
│   ├── Public Subnet 1 (AZ 1): 10.0.1.0/24   [ALB + ECS Fargate Tasks]
│   └── Public Subnet 2 (AZ 2): 10.0.2.0/24   [ALB + ECS Fargate Tasks]
├── Private Route Table (Isolated)
│   ├── Private Subnet 1 (AZ 1): 10.0.10.0/24  [RDS PostgreSQL 16]
│   └── Private Subnet 2 (AZ 2): 10.0.20.0/24  [RDS PostgreSQL 16]
└── S3 Gateway VPC Endpoint (Associated with Public & Private Route Tables)
```

---

## Resources Created

| Logical ID | Resource Type | Description |
|---|---|---|
| `VPC` | `AWS::EC2::VPC` | Primary VPC (`10.0.0.0/16`) with DNS support and DNS hostnames enabled |
| `InternetGateway` | `AWS::EC2::InternetGateway` | Internet Gateway for public internet traffic |
| `VPCGatewayAttachment` | `AWS::EC2::VPCGatewayAttachment` | Attaches IGW to the VPC |
| `PublicSubnet1` | `AWS::EC2::Subnet` | Public subnet in AZ 1 (`10.0.1.0/24`, MapPublicIpOnLaunch: true) |
| `PublicSubnet2` | `AWS::EC2::Subnet` | Public subnet in AZ 2 (`10.0.2.0/24`, MapPublicIpOnLaunch: true) |
| `PrivateSubnet1` | `AWS::EC2::Subnet` | Isolated private subnet in AZ 1 (`10.0.10.0/24`) |
| `PrivateSubnet2` | `AWS::EC2::Subnet` | Isolated private subnet in AZ 2 (`10.0.20.0/24`) |
| `PublicRouteTable` | `AWS::EC2::RouteTable` | Route table with `0.0.0.0/0` routed to `InternetGateway` |
| `PublicRoute` | `AWS::EC2::Route` | Default internet route for public subnets |
| `Subnet1PublicRouteTableAssociation` | `AWS::EC2::SubnetRouteTableAssociation` | Associates Public Subnet 1 with Public Route Table |
| `Subnet2PublicRouteTableAssociation` | `AWS::EC2::SubnetRouteTableAssociation` | Associates Public Subnet 2 with Public Route Table |
| `PrivateRouteTable` | `AWS::EC2::RouteTable` | Isolated route table for private subnets |
| `Subnet1PrivateRouteTableAssociation` | `AWS::EC2::SubnetRouteTableAssociation` | Associates Private Subnet 1 with Private Route Table |
| `Subnet2PrivateRouteTableAssociation` | `AWS::EC2::SubnetRouteTableAssociation` | Associates Private Subnet 2 with Private Route Table |
| `S3GatewayEndpoint` | `AWS::EC2::VPCEndpoint` | Free S3 Gateway VPC Endpoint attached to both route tables |
| `SSMVpcId` | `AWS::SSM::Parameter` | SSM export for VPC ID |
| `SSMPublicSubnets` | `AWS::SSM::Parameter` | SSM export for comma-separated Public Subnet IDs |
| `SSMPrivateSubnets` | `AWS::SSM::Parameter` | SSM export for comma-separated Private Subnet IDs |

---

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `EnvironmentName` | String | `prod` | Environment prefix (`dev`, `staging`, `prod`) |
| `VpcCidr` | String | `10.0.0.0/16` | IPv4 CIDR block for the VPC |
| `PublicSubnet1Cidr` | String | `10.0.1.0/24` | CIDR block for Public Subnet 1 (AZ 1) |
| `PublicSubnet2Cidr` | String | `10.0.2.0/24` | CIDR block for Public Subnet 2 (AZ 2) |
| `PrivateSubnet1Cidr` | String | `10.0.10.0/24` | CIDR block for Private Subnet 1 (AZ 1) |
| `PrivateSubnet2Cidr` | String | `10.0.20.0/24` | CIDR block for Private Subnet 2 (AZ 2) |

---

## Inter-Module Contract & Discovery

### SSM Parameter Store
Downstream modules discover networking resources via SSM:
* `/nextcloud/${EnvironmentName}/infra/vpc-id` ➔ Primary VPC ID
* `/nextcloud/${EnvironmentName}/infra/public-subnets` ➔ Comma-separated Public Subnet IDs (`PublicSubnet1,PublicSubnet2`)
* `/nextcloud/${EnvironmentName}/infra/private-subnets` ➔ Comma-separated Private Subnet IDs (`PrivateSubnet1,PrivateSubnet2`)

### CloudFormation Exports
* `${EnvironmentName}-nextcloud-VpcId`
* `${EnvironmentName}-nextcloud-PublicSubnet1Id`
* `${EnvironmentName}-nextcloud-PublicSubnet2Id`
* `${EnvironmentName}-nextcloud-PublicSubnetIds`
* `${EnvironmentName}-nextcloud-PrivateSubnet1Id`
* `${EnvironmentName}-nextcloud-PrivateSubnet2Id`
* `${EnvironmentName}-nextcloud-PrivateSubnetIds`

---

## Deployment CLI Example

```bash
aws cloudformation deploy \
  --template-file infra/modules/01-networking/template.yaml \
  --stack-name prod-nextcloud-01-networking \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides EnvironmentName=prod
```
