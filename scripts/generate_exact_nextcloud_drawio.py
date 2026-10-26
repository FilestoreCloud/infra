import os

def generate_exact_nextcloud_drawio():
    xml = """<mxfile host="Electron" agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) draw.io/29.6.1 Chrome/142.0.7444.265 Electron/39.8.0 Safari/537.36" version="29.6.1">
  <diagram name="Nextcloud-Architecture" id="nextcloud-arch-exact">
    <mxGraphModel dx="2200" dy="1600" grid="0" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="2000" pageHeight="1800" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />

        <!-- ========================================================== -->
        <!-- TOP ROW: EXTERNAL ACTORS & CLIENTS                         -->
        <!-- ========================================================== -->
        <!-- External Guest -->
        <mxCell id="guest-icon" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#232F3D;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.client;fontFamily=Helvetica;" value="External Guest" vertex="1">
          <mxGeometry height="48" width="48" x="530" y="30" as="geometry" />
        </mxCell>

        <!-- Tenant 1 Users -->
        <mxCell id="t1-users-icon" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#232F3D;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.users;fontFamily=Helvetica;" value="Tenant 1 Users" vertex="1">
          <mxGeometry height="48" width="48" x="690" y="30" as="geometry" />
        </mxCell>

        <!-- Tenant 2 Users -->
        <mxCell id="t2-users-icon" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#232F3D;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.users;fontFamily=Helvetica;" value="Tenant 2 Users" vertex="1">
          <mxGeometry height="48" width="48" x="850" y="30" as="geometry" />
        </mxCell>

        <!-- ========================================================== -->
        <!-- AWS CLOUD BOUNDARY CONTAINER                               -->
        <!-- ========================================================== -->
        <mxCell id="aws-cloud" parent="1" style="points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=14;fontStyle=1;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_aws_cloud;strokeColor=#232F3E;fillColor=light-dark(#FFFFFF00,#FFFFFF00);verticalAlign=top;align=left;spacingLeft=30;fontColor=#232F3E;dashed=0;container=1;pointerEvents=0;collapsible=0;recursiveResize=0;fontFamily=Helvetica;" value="AWS Cloud" vertex="1">
          <mxGeometry height="1520" width="1360" x="50" y="120" as="geometry" />
        </mxCell>

        <!-- ========================================================== -->
        <!-- EDGE PERIMETER SERVICES (Centered under Actors)            -->
        <!-- ========================================================== -->
        <!-- Amazon Route 53 -->
        <mxCell id="svc-r53" parent="aws-cloud" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#8C4FFF;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.route_53;fontFamily=Helvetica;" value="Amazon Route 53" vertex="1">
          <mxGeometry height="48" width="48" x="480" y="70" as="geometry" />
        </mxCell>

        <!-- AWS Certificate Manager -->
        <mxCell id="svc-acm" parent="aws-cloud" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#DD344C;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.certificate_manager;fontFamily=Helvetica;" value="AWS Certificate Manager" vertex="1">
          <mxGeometry height="48" width="48" x="650" y="70" as="geometry" />
        </mxCell>

        <!-- AWS WAF -->
        <mxCell id="svc-waf" parent="aws-cloud" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#DD344C;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.waf;fontFamily=Helvetica;" value="AWS WAF" vertex="1">
          <mxGeometry height="48" width="48" x="810" y="70" as="geometry" />
        </mxCell>

        <!-- ========================================================== -->
        <!-- AWS REGION (ap-southeast-1) CONTAINER                      -->
        <!-- ========================================================== -->
        <mxCell id="region-group" parent="aws-cloud" style="points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=14;fontStyle=1;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_region;strokeColor=#00A4A6;fillColor=light-dark(#FFFFFF00,#FFFFFF00);verticalAlign=top;align=left;spacingLeft=30;fontColor=#00A4A6;dashed=1;container=1;pointerEvents=0;collapsible=0;recursiveResize=0;fontFamily=Helvetica;" value="AWS Region (ap-southeast-1)" vertex="1">
          <mxGeometry height="1300" width="1280" x="40" y="180" as="geometry" />
        </mxCell>

        <!-- ========================================================== -->
        <!-- AMAZON VPC (LEFT SIDE)                                     -->
        <!-- ========================================================== -->
        <mxCell id="vpc-group" parent="region-group" style="points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=14;fontStyle=1;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_vpc2;strokeColor=#8C4FFF;fillColor=light-dark(#FFFFFF00,#FFFFFF00);verticalAlign=top;align=left;spacingLeft=30;fontColor=#8C4FFF;dashed=0;container=1;pointerEvents=0;collapsible=0;recursiveResize=0;fontFamily=Helvetica;" value="Amazon VPC" vertex="1">
          <mxGeometry height="1060" width="510" x="40" y="100" as="geometry" />
        </mxCell>

        <!-- Internet Gateway on top border of VPC -->
        <mxCell id="svc-igw" parent="vpc-group" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#8C4FFF;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.internet_gateway;fontFamily=Helvetica;" value="Internet Gateway" vertex="1">
          <mxGeometry height="48" width="48" x="231" y="20" as="geometry" />
        </mxCell>

        <!-- ────────────────────────────────────────────────────────── -->
        <!-- PUBLIC SUBNETS (TOP SECTION OF VPC)                        -->
        <!-- ────────────────────────────────────────────────────────── -->
        <mxCell id="public-subnet" parent="vpc-group" style="points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=14;fontStyle=1;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_public_subnet;strokeColor=#248814;fillColor=light-dark(#FFFFFF00,#FFFFFF00);verticalAlign=top;align=left;spacingLeft=30;fontColor=#248814;dashed=0;container=1;pointerEvents=0;collapsible=0;recursiveResize=0;fontFamily=Helvetica;" value="Public Subnets" vertex="1">
          <mxGeometry height="540" width="440" x="35" y="110" as="geometry" />
        </mxCell>

        <!-- Application Load Balancer -->
        <mxCell id="svc-alb" parent="public-subnet" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#8C4FFF;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.elastic_load_balancing;fontFamily=Helvetica;" value="Application Load Balancer" vertex="1">
          <mxGeometry height="48" width="48" x="196" y="80" as="geometry" />
        </mxCell>

        <!-- Amazon ECS Sub-Container -->
        <mxCell id="ecs-group" parent="public-subnet" style="points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=14;fontStyle=1;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.ecs;strokeColor=#ED7100;fillColor=light-dark(#FFFFFF00,#FFFFFF00);verticalAlign=top;align=left;spacingLeft=30;fontColor=#232F3E;dashed=0;container=1;pointerEvents=0;collapsible=0;recursiveResize=0;fontFamily=Helvetica;" value="Amazon ECS" vertex="1">
          <mxGeometry height="180" width="370" x="35" y="190" as="geometry" />
        </mxCell>

        <!-- Task 1 (AWS Fargate) -->
        <mxCell id="svc-task1" parent="ecs-group" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#ED7100;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.fargate;fontFamily=Helvetica;" value="AWS Fargate" vertex="1">
          <mxGeometry height="48" width="48" x="80" y="80" as="geometry" />
        </mxCell>

        <!-- Task 2 (AWS Fargate) -->
        <mxCell id="svc-task2" parent="ecs-group" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#ED7100;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.fargate;fontFamily=Helvetica;" value="AWS Fargate" vertex="1">
          <mxGeometry height="48" width="48" x="240" y="80" as="geometry" />
        </mxCell>

        <!-- Amazon EFS -->
        <mxCell id="svc-efs" parent="public-subnet" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#3F8624;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.elastic_file_system;fontFamily=Helvetica;" value="Amazon EFS" vertex="1">
          <mxGeometry height="48" width="48" x="115" y="440" as="geometry" />
        </mxCell>

        <!-- S3 Gateway Endpoint -->
        <mxCell id="svc-vpce" parent="public-subnet" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#8C4FFF;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.endpoint;fontFamily=Helvetica;" value="S3 Gateway Endpoint" vertex="1">
          <mxGeometry height="48" width="48" x="275" y="440" as="geometry" />
        </mxCell>

        <!-- ────────────────────────────────────────────────────────── -->
        <!-- PRIVATE SUBNETS (BOTTOM SECTION OF VPC)                   -->
        <!-- ────────────────────────────────────────────────────────── -->
        <mxCell id="private-subnet" parent="vpc-group" style="points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=14;fontStyle=1;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_private_subnet;strokeColor=#147EBA;fillColor=light-dark(#FFFFFF00,#FFFFFF00);verticalAlign=top;align=left;spacingLeft=30;fontColor=#147EBA;dashed=0;container=1;pointerEvents=0;collapsible=0;recursiveResize=0;fontFamily=Helvetica;" value="Private Subnets" vertex="1">
          <mxGeometry height="260" width="440" x="35" y="700" as="geometry" />
        </mxCell>

        <!-- Amazon RDS Proxy -->
        <mxCell id="svc-proxy" parent="private-subnet" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#C925D1;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.rds_proxy;fontFamily=Helvetica;" value="Amazon RDS Proxy" vertex="1">
          <mxGeometry height="48" width="48" x="115" y="100" as="geometry" />
        </mxCell>

        <!-- Amazon RDS (Database instance) -->
        <mxCell id="svc-rds" parent="private-subnet" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#C925D1;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.rds_postgresql_instance;fontFamily=Helvetica;" value="Amazon RDS" vertex="1">
          <mxGeometry height="48" width="48" x="275" y="100" as="geometry" />
        </mxCell>

        <!-- ========================================================== -->
        <!-- REGIONAL SERVICES (RIGHT SIDE OF REGION)                   -->
        <!-- ========================================================== -->
        <!-- Top Row (Storage & Security) -->
        <!-- Amazon S3 -->
        <mxCell id="svc-s3" parent="region-group" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#3F8624;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.s3;fontFamily=Helvetica;" value="Amazon S3" vertex="1">
          <mxGeometry height="48" width="48" x="690" y="440" as="geometry" />
        </mxCell>

        <!-- AWS Secrets Manager -->
        <mxCell id="svc-sm" parent="region-group" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#DD344C;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.secrets_manager;fontFamily=Helvetica;" value="AWS Secrets Manager" vertex="1">
          <mxGeometry height="48" width="48" x="840" y="440" as="geometry" />
        </mxCell>

        <!-- Amazon ECR -->
        <mxCell id="svc-ecr" parent="region-group" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#ED7100;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.ecr;fontFamily=Helvetica;" value="Amazon ECR" vertex="1">
          <mxGeometry height="48" width="48" x="990" y="440" as="geometry" />
        </mxCell>

        <!-- Bottom Row (AI & Observability) -->
        <!-- Amazon Bedrock -->
        <mxCell id="svc-bedrock" parent="region-group" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#01A88D;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.bedrock;fontFamily=Helvetica;" value="Amazon Bedrock" vertex="1">
          <mxGeometry height="48" width="48" x="580" y="550" as="geometry" />
        </mxCell>

        <!-- Amazon EventBridge -->
        <mxCell id="svc-eventbridge" parent="region-group" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#E7157B;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.eventbridge;fontFamily=Helvetica;" value="Amazon EventBridge" vertex="1">
          <mxGeometry height="48" width="48" x="730" y="550" as="geometry" />
        </mxCell>

        <!-- Amazon CloudWatch Logs -->
        <mxCell id="svc-cw-logs" parent="region-group" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#E7157B;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.cloudwatch;fontFamily=Helvetica;" value="Amazon CloudWatch Logs" vertex="1">
          <mxGeometry height="48" width="48" x="880" y="550" as="geometry" />
        </mxCell>

        <!-- Amazon CloudWatch Synthetics -->
        <mxCell id="svc-synthetics" parent="region-group" style="sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#E7157B;strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.cloudwatch_synthetics;fontFamily=Helvetica;" value="Amazon CloudWatch Synthetics" vertex="1">
          <mxGeometry height="48" width="48" x="1080" y="550" as="geometry" />
        </mxCell>

        <!-- ========================================================== -->
        <!-- CONNECTION LINES & ARROWS                                  -->
        <!-- ========================================================== -->
        <!-- External Guest -> Route 53 -->
        <mxCell id="e-guest-r53" edge="1" parent="1" source="guest-icon" target="svc-r53" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- Tenant 1 Users -> Route 53 -->
        <mxCell id="e-t1-r53" edge="1" parent="1" source="t1-users-icon" target="svc-r53" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- Tenant 2 Users -> Route 53 -->
        <mxCell id="e-t2-r53" edge="1" parent="1" source="t2-users-icon" target="svc-r53" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- Route 53 -> WAF -->
        <mxCell id="e-r53-waf" edge="1" parent="aws-cloud" source="svc-r53" target="svc-waf" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry">
            <Array as="points">
              <mxPoint x="504" y="140" />
              <mxPoint x="750" y="140" />
              <mxPoint x="750" y="94" />
            </Array>
          </mxGeometry>
        </mxCell>

        <!-- ACM -> WAF -->
        <mxCell id="e-acm-waf" edge="1" parent="aws-cloud" source="svc-acm" target="svc-waf" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- WAF -> IGW -->
        <mxCell id="e-waf-igw" edge="1" parent="aws-cloud" source="svc-waf" target="svc-igw" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry">
            <Array as="points">
              <mxPoint x="834" y="150" />
              <mxPoint x="311" y="150" />
            </Array>
          </mxGeometry>
        </mxCell>

        <!-- IGW -> ALB -->
        <mxCell id="e-igw-alb" edge="1" parent="vpc-group" source="svc-igw" target="svc-alb" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- ALB -> Fargate Task 1 -->
        <mxCell id="e-alb-task1" edge="1" parent="public-subnet" source="svc-alb" target="svc-task1" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry">
            <Array as="points">
              <mxPoint x="220" y="150" />
              <mxPoint x="139" y="150" />
            </Array>
          </mxGeometry>
        </mxCell>

        <!-- ALB -> Fargate Task 2 -->
        <mxCell id="e-alb-task2" edge="1" parent="public-subnet" source="svc-alb" target="svc-task2" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry">
            <Array as="points">
              <mxPoint x="220" y="150" />
              <mxPoint x="299" y="150" />
            </Array>
          </mxGeometry>
        </mxCell>

        <!-- Task 1 -> EFS -->
        <mxCell id="e-task1-efs" edge="1" parent="public-subnet" source="svc-task1" target="svc-efs" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- Task 2 -> EFS -->
        <mxCell id="e-task2-efs" edge="1" parent="public-subnet" source="svc-task2" target="svc-efs" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry">
            <Array as="points">
              <mxPoint x="299" y="390" />
              <mxPoint x="155" y="390" />
            </Array>
          </mxGeometry>
        </mxCell>

        <!-- Task 2 -> S3 Gateway Endpoint -->
        <mxCell id="e-task2-vpce" edge="1" parent="public-subnet" source="svc-task2" target="svc-vpce" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- S3 Gateway Endpoint -> S3 Vault Bucket -->
        <mxCell id="e-vpce-s3" edge="1" parent="region-group" source="svc-vpce" target="svc-s3" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry">
            <Array as="points">
              <mxPoint x="490" y="674" />
              <mxPoint x="490" y="464" />
            </Array>
          </mxGeometry>
        </mxCell>

        <!-- Task 1 -> RDS Proxy -->
        <mxCell id="e-task1-proxy" edge="1" parent="vpc-group" source="svc-task1" target="svc-proxy" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry">
            <Array as="points">
              <mxPoint x="60" y="380" />
              <mxPoint x="60" y="770" />
              <mxPoint x="174" y="770" />
            </Array>
          </mxGeometry>
        </mxCell>

        <!-- Task 2 -> RDS Proxy -->
        <mxCell id="e-task2-proxy" edge="1" parent="vpc-group" source="svc-task2" target="svc-proxy" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry">
            <Array as="points">
              <mxPoint x="314" y="760" />
              <mxPoint x="174" y="760" />
            </Array>
          </mxGeometry>
        </mxCell>

        <!-- RDS Proxy -> RDS Instance -->
        <mxCell id="e-proxy-rds" edge="1" parent="private-subnet" source="svc-proxy" target="svc-rds" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- Task 2 -> Secrets Manager -->
        <mxCell id="e-task2-sm" edge="1" parent="region-group" source="svc-task2" target="svc-sm" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry">
            <Array as="points">
              <mxPoint x="500" y="380" />
              <mxPoint x="500" y="464" />
            </Array>
          </mxGeometry>
        </mxCell>

        <!-- Task 1 -> ECR Repo -->
        <mxCell id="e-task1-ecr" edge="1" parent="region-group" source="svc-task1" target="svc-ecr" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry">
            <Array as="points">
              <mxPoint x="500" y="380" />
              <mxPoint x="500" y="464" />
            </Array>
          </mxGeometry>
        </mxCell>

        <!-- Task 2 -> Bedrock AI -->
        <mxCell id="e-task2-bedrock" edge="1" parent="region-group" source="svc-task2" target="svc-bedrock" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry">
            <Array as="points">
              <mxPoint x="500" y="400" />
              <mxPoint x="500" y="574" />
            </Array>
          </mxGeometry>
        </mxCell>

        <!-- Task 2 -> CloudWatch Logs -->
        <mxCell id="e-task2-logs" edge="1" parent="region-group" source="svc-task2" target="svc-cw-logs" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry">
            <Array as="points">
              <mxPoint x="500" y="400" />
              <mxPoint x="500" y="574" />
            </Array>
          </mxGeometry>
        </mxCell>

        <!-- EventBridge -> Task 2 -->
        <mxCell id="e-eb-task2" edge="1" parent="region-group" source="svc-eventbridge" target="svc-task2" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry">
            <Array as="points">
              <mxPoint x="754" y="530" />
              <mxPoint x="490" y="530" />
              <mxPoint x="490" y="380" />
            </Array>
          </mxGeometry>
        </mxCell>

        <!-- Synthetics Canary -> ALB -->
        <mxCell id="e-synth-alb" edge="1" parent="region-group" source="svc-synthetics" target="svc-alb" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=open;endFill=0;strokeColor=#545B64;">
          <mxGeometry relative="1" as="geometry">
            <Array as="points">
              <mxPoint x="1104" y="340" />
              <mxPoint x="490" y="340" />
            </Array>
          </mxGeometry>
        </mxCell>

      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""
    return xml

if __name__ == "__main__":
    content = generate_exact_nextcloud_drawio()
    out_path = "infra/docs/nextcloud_architecture.drawio"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Generated {out_path} ({len(content)} bytes)")
    
    # Also write to docs/
    with open("docs/nextcloud_architecture.drawio", "w", encoding="utf-8") as f:
        f.write(content)
