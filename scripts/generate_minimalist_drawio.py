import xml.etree.ElementTree as ET

def build_minimalist_xml():
    xml = """<mxfile host="Electron" agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) draw.io/29.6.1 Chrome/142.0.7444.265 Electron/39.8.0 Safari/537.36" version="29.6.1">
  <diagram name="Storix-Gap-Roadmap-Minimalist" id="storix-min-roadmap">
    <mxGraphModel dx="2200" dy="1400" grid="0" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="2000" pageHeight="1150" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />

        <!-- ============================================================== -->
        <!-- HEADER BLOCK                                                   -->
        <!-- ============================================================== -->
        <mxCell id="hdr-group" connectable="0" parent="1" style="group;fontFamily=Helvetica;" value="" vertex="1">
          <mxGeometry height="70" width="1900" x="50" y="30" as="geometry" />
        </mxCell>
        <mxCell id="hdr-title" parent="hdr-group" style="text;html=1;align=left;verticalAlign=middle;fontSize=24;fontStyle=1;fontFamily=Helvetica;fontColor=#232F3E;" value="Storix: Đã Đạt Được vs. Chưa Đạt Được vs. Lộ Trình Phát Triển" vertex="1">
          <mxGeometry height="34" width="1100" x="0" y="0" as="geometry" />
        </mxCell>
        <mxCell id="hdr-sub" parent="hdr-group" style="text;html=1;align=left;verticalAlign=middle;fontSize=13;fontFamily=Helvetica;fontColor=#545B64;" value="Tối giản trực quan • Nhiều Icon minh hoạ • Rõ ràng ranh giới năng lực và định hướng" vertex="1">
          <mxGeometry height="20" width="900" x="0" y="34" as="geometry" />
        </mxCell>
        <mxCell id="hdr-line" parent="hdr-group" style="line;strokeWidth=2;html=1;strokeColor=#FF9900;" value="" vertex="1">
          <mxGeometry height="8" width="1900" x="0" y="58" as="geometry" />
        </mxCell>

        <!-- ============================================================== -->
        <!-- PANEL 1: ĐÃ ĐẠT ĐƯỢC (CURRENT PRODUCTION)                      -->
        <!-- ============================================================== -->
        <mxCell id="pnl-done" parent="1" style="rounded=1;whiteSpace=wrap;html=1;strokeColor=#16A34A;strokeWidth=2;fillColor=#F0FDF4;verticalAlign=top;align=left;spacingLeft=18;spacingTop=12;fontStyle=1;fontSize=15;fontColor=#15803D;fontFamily=Helvetica;" value="✅ 1. ĐÃ ĐẠT ĐƯỢC (Nền tảng vận hành hiện tại)" vertex="1">
          <mxGeometry height="300" width="1900" x="50" y="120" as="geometry" />
        </mxCell>

        <!-- Actors -->
        <mxCell id="ic-users" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#0284C7;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=1;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.users;fontFamily=Helvetica;" value="Tenant Users&lt;br&gt;&lt;i style=&quot;font-size:9px;color:#666;&quot;&gt;(Multi-Tenant)&lt;/i&gt;" vertex="1">
          <mxGeometry height="48" width="48" x="90" y="180" as="geometry" />
        </mxCell>
        <mxCell id="ic-admin" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#4338CA;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=1;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.authenticated_user;fontFamily=Helvetica;" value="SuperAdmin&lt;br&gt;&lt;i style=&quot;font-size:9px;color:#666;&quot;&gt;(WebAuthn/MFA)&lt;/i&gt;" vertex="1">
          <mxGeometry height="48" width="48" x="210" y="180" as="geometry" />
        </mxCell>

        <!-- Arrow Ingress -->
        <mxCell id="arr-in" edge="1" parent="1" source="ic-users" target="ic-waf" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#16A34A;strokeWidth=2;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- WAF -->
        <mxCell id="ic-waf" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#DD344C;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=1;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.waf;fontFamily=Helvetica;" value="AWS WAF&lt;br&gt;&lt;i style=&quot;font-size:9px;color:#666;&quot;&gt;(TLS 1.3/Rate Limit)&lt;/i&gt;" vertex="1">
          <mxGeometry height="48" width="48" x="330" y="180" as="geometry" />
        </mxCell>

        <!-- ALB -->
        <mxCell id="ic-alb" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#8C4FFF;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=1;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.elastic_load_balancing;fontFamily=Helvetica;" value="ALB Dual-AZ&lt;br&gt;&lt;i style=&quot;font-size:9px;color:#666;&quot;&gt;(Host Routing)&lt;/i&gt;" vertex="1">
          <mxGeometry height="48" width="48" x="450" y="180" as="geometry" />
        </mxCell>

        <!-- Arrow ALB -> Compute -->
        <mxCell id="arr-alb-cmp" edge="1" parent="1" source="ic-waf" target="ic-alb" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#16A34A;strokeWidth=2;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- Fargate Acme -->
        <mxCell id="ic-fg-acme" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#FF9900;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=1;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.fargate;fontFamily=Helvetica;" value="Fargate (Acme)&lt;br&gt;&lt;i style=&quot;font-size:9px;color:#666;&quot;&gt;Graviton ARM64&lt;/i&gt;" vertex="1">
          <mxGeometry height="48" width="48" x="590" y="180" as="geometry" />
        </mxCell>

        <!-- Fargate Marvel -->
        <mxCell id="ic-fg-marvel" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#FF9900;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=1;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.fargate;fontFamily=Helvetica;" value="Fargate (Marvel)&lt;br&gt;&lt;i style=&quot;font-size:9px;color:#666;&quot;&gt;Scale-to-Zero&lt;/i&gt;" vertex="1">
          <mxGeometry height="48" width="48" x="720" y="180" as="geometry" />
        </mxCell>

        <!-- Bedrock AI Sidecar -->
        <mxCell id="ic-bedrock" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#0284C7;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=1;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.bedrock;fontFamily=Helvetica;" value="Amazon Bedrock&lt;br&gt;&lt;i style=&quot;font-size:9px;color:#666;&quot;&gt;Claude 3.5 Sonnet&lt;/i&gt;" vertex="1">
          <mxGeometry height="48" width="48" x="850" y="180" as="geometry" />
        </mxCell>

        <!-- RDS Proxy + PostgreSQL -->
        <mxCell id="ic-rds" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#3B48CC;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=1;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.rds;fontFamily=Helvetica;" value="RDS Proxy + DB&lt;br&gt;&lt;i style=&quot;font-size:9px;color:#666;&quot;&gt;DB-per-Tenant&lt;/i&gt;" vertex="1">
          <mxGeometry height="48" width="48" x="980" y="180" as="geometry" />
        </mxCell>

        <!-- Amazon EFS -->
        <mxCell id="ic-efs" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#16A34A;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=1;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.elastic_file_system;fontFamily=Helvetica;" value="Amazon EFS&lt;br&gt;&lt;i style=&quot;font-size:9px;color:#666;&quot;&gt;Config Access Points&lt;/i&gt;" vertex="1">
          <mxGeometry height="48" width="48" x="1110" y="180" as="geometry" />
        </mxCell>

        <!-- Amazon S3 Vault -->
        <mxCell id="ic-s3" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#16A34A;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=1;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.s3;fontFamily=Helvetica;" value="S3 Vault Bucket&lt;br&gt;&lt;i style=&quot;font-size:9px;color:#666;&quot;&gt;Prefix Isolation + KMS&lt;/i&gt;" vertex="1">
          <mxGeometry height="48" width="48" x="1240" y="180" as="geometry" />
        </mxCell>

        <!-- Step Functions SAGA -->
        <mxCell id="ic-sfn" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#FF4F8B;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=1;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.step_functions;fontFamily=Helvetica;" value="Step Functions&lt;br&gt;&lt;i style=&quot;font-size:9px;color:#666;&quot;&gt;SAGA Orchestration&lt;/i&gt;" vertex="1">
          <mxGeometry height="48" width="48" x="1370" y="180" as="geometry" />
        </mxCell>

        <!-- DynamoDB Audit -->
        <mxCell id="ic-ddb" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#3B48CC;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=1;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.dynamodb;fontFamily=Helvetica;" value="DynamoDB&lt;br&gt;&lt;i style=&quot;font-size:9px;color:#666;&quot;&gt;1-Year Audit Log&lt;/i&gt;" vertex="1">
          <mxGeometry height="48" width="48" x="1500" y="180" as="geometry" />
        </mxCell>

        <!-- WebDAV & OCS REST API -->
        <mxCell id="ic-api-rest" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#DCFCE7;strokeColor=#16A34A;strokeWidth=1.5;fontSize=11;fontStyle=1;align=center;fontFamily=Helvetica;" value="&lt;b&gt;APIs Có Sẵn&lt;/b&gt;&lt;br&gt;• WebDAV (RFC 4918)&lt;br&gt;• Nextcloud OCS REST" vertex="1">
          <mxGeometry height="54" width="160" x="1620" y="177" as="geometry" />
        </mxCell>

        <!-- Feature pill summary -->
        <mxCell id="pill-done" parent="1" style="rounded=20;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#16A34A;strokeWidth=1;fontSize=11;fontColor=#15803D;align=center;fontFamily=Helvetica;" value="🌟 Đã đạt: Multi-tenant 4 tầng (Compute / DB / Storage / Config) • Upload / Download / Trashbin / Versioning • WebAuthn MFA • Audit Ledger • Bedrock AI" vertex="1">
          <mxGeometry height="32" width="1860" x="70" y="270" as="geometry" />
        </mxCell>

        <!-- ============================================================== -->
        <!-- PANEL 2: CHƯA ĐẠT ĐƯỢC (GAPS TO UPGRADE)                       -->
        <!-- ============================================================== -->
        <mxCell id="pnl-gap" parent="1" style="rounded=1;whiteSpace=wrap;html=1;strokeColor=#EA580C;strokeWidth=2;fillColor=#FFF7ED;dashed=1;verticalAlign=top;align=left;spacingLeft=18;spacingTop=12;fontStyle=1;fontSize=15;fontColor=#C2410C;fontFamily=Helvetica;" value="⏳ 2. CHƯA ĐẠT ĐƯỢC (Khoảng trống cần khắc phục &amp; nâng cấp)" vertex="1">
          <mxGeometry height="330" width="1900" x="50" y="450" as="geometry" />
        </mxCell>

        <!-- GAP 1: Full-Text Content Search Box -->
        <mxCell id="gap-box-1" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#EA580C;strokeWidth=1.5;fontSize=12;fontFamily=Helvetica;" value="" vertex="1">
          <mxGeometry height="210" width="440" x="70" y="495" as="geometry" />
        </mxCell>
        <mxCell id="gap-t1" parent="1" style="text;html=1;align=left;fontSize=13;fontStyle=1;fontColor=#C2410C;fontFamily=Helvetica;" value="1. Full-Text Search qua nội dung file" vertex="1">
          <mxGeometry height="24" width="300" x="85" y="505" as="geometry" />
        </mxCell>
        <!-- Gap 1 Icons Pipeline -->
        <mxCell id="g1-s3" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#16A34A;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.s3;fontFamily=Helvetica;" value="S3 Upload" vertex="1">
          <mxGeometry height="40" width="40" x="90" y="540" as="geometry" />
        </mxCell>
        <mxCell id="g1-sqs" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#FF4F8B;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.sqs;fontFamily=Helvetica;" value="SQS Queue" vertex="1">
          <mxGeometry height="40" width="40" x="180" y="540" as="geometry" />
        </mxCell>
        <mxCell id="g1-txt" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#0284C7;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.textract;fontFamily=Helvetica;" value="OCR / Tika" vertex="1">
          <mxGeometry height="40" width="40" x="270" y="540" as="geometry" />
        </mxCell>
        <mxCell id="g1-os" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#FF9900;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.elasticsearch_service;fontFamily=Helvetica;" value="OpenSearch" vertex="1">
          <mxGeometry height="40" width="40" x="360" y="540" as="geometry" />
        </mxCell>
        <mxCell id="g1-desc" parent="1" style="text;html=1;align=left;fontSize=10.5;fontColor=#555;fontFamily=Helvetica;whiteSpace=wrap;" value="• Hiện tại: Chỉ tìm metadata trong SQL.&lt;br&gt;• Cần có: Ingestion Pipeline tự trích xuất chữ trong PDF, DOCX, bản scan &amp; đẩy vào OpenSearch." vertex="1">
          <mxGeometry height="50" width="410" x="85" y="640" as="geometry" />
        </mxCell>


        <!-- GAP 2: Presigned Direct S3 Box -->
        <mxCell id="gap-box-2" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#EA580C;strokeWidth=1.5;fontSize=12;fontFamily=Helvetica;" value="" vertex="1">
          <mxGeometry height="210" width="440" x="530" y="495" as="geometry" />
        </mxCell>
        <mxCell id="gap-t2" parent="1" style="text;html=1;align=left;fontSize=13;fontStyle=1;fontColor=#C2410C;fontFamily=Helvetica;" value="2. Presigned URLs (Bypass Fargate I/O)" vertex="1">
          <mxGeometry height="24" width="300" x="545" y="505" as="geometry" />
        </mxCell>
        <!-- Gap 2 Icons -->
        <mxCell id="g2-usr" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#0284C7;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.users;fontFamily=Helvetica;" value="User" vertex="1">
          <mxGeometry height="40" width="40" x="560" y="540" as="geometry" />
        </mxCell>
        <mxCell id="g2-apigw" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#8C4FFF;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.api_gateway;fontFamily=Helvetica;" value="API Gateway" vertex="1">
          <mxGeometry height="40" width="40" x="660" y="540" as="geometry" />
        </mxCell>
        <mxCell id="g2-lmb" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#FF9900;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.lambda;fontFamily=Helvetica;" value="Token Signer" vertex="1">
          <mxGeometry height="40" width="40" x="760" y="540" as="geometry" />
        </mxCell>
        <mxCell id="g2-s3" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#16A34A;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.s3;fontFamily=Helvetica;" value="Direct S3" vertex="1">
          <mxGeometry height="40" width="40" x="860" y="540" as="geometry" />
        </mxCell>
        <mxCell id="g2-desc" parent="1" style="text;html=1;align=left;fontSize=10.5;fontColor=#555;fontFamily=Helvetica;whiteSpace=wrap;" value="• Hiện tại: File chạy xuyên qua Fargate → Nghẽn CPU/RAM.&lt;br&gt;• Cần có: Client upload/download trực tiếp tới S3 qua Presigned URL có thời hạn." vertex="1">
          <mxGeometry height="50" width="410" x="545" y="640" as="geometry" />
        </mxCell>


        <!-- GAP 3: S3 Malware Protection Box -->
        <mxCell id="gap-box-3" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#EA580C;strokeWidth=1.5;fontSize=12;fontFamily=Helvetica;" value="" vertex="1">
          <mxGeometry height="210" width="440" x="990" y="495" as="geometry" />
        </mxCell>
        <mxCell id="gap-t3" parent="1" style="text;html=1;align=left;fontSize=13;fontStyle=1;fontColor=#C2410C;fontFamily=Helvetica;" value="3. Antivirus &amp; S3 Malware Protection" vertex="1">
          <mxGeometry height="24" width="300" x="1005" y="505" as="geometry" />
        </mxCell>
        <!-- Gap 3 Icons -->
        <mxCell id="g3-s3" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#16A34A;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.s3;fontFamily=Helvetica;" value="Upload S3" vertex="1">
          <mxGeometry height="40" width="40" x="1020" y="540" as="geometry" />
        </mxCell>
        <mxCell id="g3-gd" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#DD344C;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.guardduty;fontFamily=Helvetica;" value="GuardDuty" vertex="1">
          <mxGeometry height="40" width="40" x="1130" y="540" as="geometry" />
        </mxCell>
        <mxCell id="g3-evb" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#FF4F8B;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.eventbridge;fontFamily=Helvetica;" value="EventBridge" vertex="1">
          <mxGeometry height="40" width="40" x="1240" y="540" as="geometry" />
        </mxCell>
        <mxCell id="g3-iso" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#DD344C;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.s3;fontFamily=Helvetica;" value="Quarantine S3" vertex="1">
          <mxGeometry height="40" width="40" x="1350" y="540" as="geometry" />
        </mxCell>
        <mxCell id="g3-desc" parent="1" style="text;html=1;align=left;fontSize=10.5;fontColor=#555;fontFamily=Helvetica;whiteSpace=wrap;" value="• Hiện tại: Chưa quét mã độc tự động cho file upload.&lt;br&gt;• Cần có: GuardDuty Malware Scan + cách ly vào Quarantine Bucket khi phát hiện virus." vertex="1">
          <mxGeometry height="50" width="410" x="1005" y="640" as="geometry" />
        </mxCell>


        <!-- GAP 4: Distributed Redis Lock & Swagger Box -->
        <mxCell id="gap-box-4" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#EA580C;strokeWidth=1.5;fontSize=12;fontFamily=Helvetica;" value="" vertex="1">
          <mxGeometry height="210" width="480" x="1450" y="495" as="geometry" />
        </mxCell>
        <mxCell id="gap-t4" parent="1" style="text;html=1;align=left;fontSize=13;fontStyle=1;fontColor=#C2410C;fontFamily=Helvetica;" value="4. Distributed Redis &amp; Developer Portal" vertex="1">
          <mxGeometry height="24" width="350" x="1465" y="505" as="geometry" />
        </mxCell>
        <!-- Gap 4 Icons -->
        <mxCell id="g4-redis" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#3B48CC;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.elasticache;fontFamily=Helvetica;" value="ElastiCache Redis&lt;br&gt;(Multi-AZ Lock)" vertex="1">
          <mxGeometry height="40" width="40" x="1510" y="540" as="geometry" />
        </mxCell>
        <mxCell id="g4-apigw" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#8C4FFF;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.api_gateway;fontFamily=Helvetica;" value="Swagger API&lt;br&gt;(Usage Plans)" vertex="1">
          <mxGeometry height="40" width="40" x="1690" y="540" as="geometry" />
        </mxCell>
        <mxCell id="g4-desc" parent="1" style="text;html=1;align=left;fontSize=10.5;fontColor=#555;fontFamily=Helvetica;whiteSpace=wrap;" value="• Hiện tại: APCu nội bộ container (khó scale ngang Fargate tasks); thiếu Swagger UI công khai.&lt;br&gt;• Cần có: Cụm Redis phân tán và cổng Developer Portal quản lý API Keys." vertex="1">
          <mxGeometry height="50" width="450" x="1465" y="640" as="geometry" />
        </mxCell>


        <!-- ============================================================== -->
        <!-- PANEL 3: LỘ TRÌNH PHÁT TRIỂN (STRATEGIC ROADMAP)               -->
        <!-- ============================================================== -->
        <mxCell id="pnl-road" parent="1" style="rounded=1;whiteSpace=wrap;html=1;strokeColor=#0284C7;strokeWidth=2;fillColor=#F0F9FF;dashed=1;dashPattern=2 2;verticalAlign=top;align=left;spacingLeft=18;spacingTop=12;fontStyle=1;fontSize=15;fontColor=#0369A1;fontFamily=Helvetica;" value="🚀 3. HƯỚNG PHÁT TRIỂN TIẾP THEO (Roadmap 3 Giai Đoạn)" vertex="1">
          <mxGeometry height="290" width="1900" x="50" y="810" as="geometry" />
        </mxCell>

        <!-- Phase 1 Card -->
        <mxCell id="rd-card-1" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;fontSize=12;fontFamily=Helvetica;" value="" vertex="1">
          <mxGeometry height="190" width="580" x="70" y="865" as="geometry" />
        </mxCell>
        <mxCell id="rd-t1" parent="1" style="text;html=1;align=left;fontSize=13;fontStyle=1;fontColor=#0369A1;fontFamily=Helvetica;" value="Phase 1 (1 - 2 tháng): Search &amp; Data Protection" vertex="1">
          <mxGeometry height="24" width="400" x="85" y="875" as="geometry" />
        </mxCell>
        <!-- Phase 1 Icons -->
        <mxCell id="r1-ic1" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#FF9900;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.elasticsearch_service;fontFamily=Helvetica;" value="OpenSearch" vertex="1">
          <mxGeometry height="42" width="42" x="120" y="915" as="geometry" />
        </mxCell>
        <mxCell id="r1-ic2" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#DD344C;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.guardduty;fontFamily=Helvetica;" value="S3 GuardDuty" vertex="1">
          <mxGeometry height="42" width="42" x="260" y="915" as="geometry" />
        </mxCell>
        <mxCell id="r1-ic3" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#3B48CC;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.elasticache;fontFamily=Helvetica;" value="Redis Cluster" vertex="1">
          <mxGeometry height="42" width="42" x="400" y="915" as="geometry" />
        </mxCell>
        <mxCell id="r1-desc" parent="1" style="text;html=1;align=left;fontSize=11;fontColor=#555;fontFamily=Helvetica;" value="• Hoàn thành OpenSearch Ingestion Pipeline (PDF/Word/OCR).&lt;br&gt;• Quét tự động &amp; cách ly mã độc tải lên S3.&lt;br&gt;• Đồng bộ Session &amp; Khóa tệp bằng ElastiCache Redis." vertex="1">
          <mxGeometry height="45" width="550" x="85" y="995" as="geometry" />
        </mxCell>

        <!-- Phase 2 Card -->
        <mxCell id="rd-card-2" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;fontSize=12;fontFamily=Helvetica;" value="" vertex="1">
          <mxGeometry height="190" width="580" x="710" y="865" as="geometry" />
        </mxCell>
        <mxCell id="rd-t2" parent="1" style="text;html=1;align=left;fontSize=13;fontStyle=1;fontColor=#0369A1;fontFamily=Helvetica;" value="Phase 2 (2 - 3 tháng): Performance &amp; AI Semantic" vertex="1">
          <mxGeometry height="24" width="400" x="725" y="875" as="geometry" />
        </mxCell>
        <!-- Phase 2 Icons -->
        <mxCell id="r2-ic1" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#8C4FFF;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.cloudfront;fontFamily=Helvetica;" value="CloudFront CDN" vertex="1">
          <mxGeometry height="42" width="42" x="770" y="915" as="geometry" />
        </mxCell>
        <mxCell id="r2-ic2" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#16A34A;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.s3;fontFamily=Helvetica;" value="Presigned S3" vertex="1">
          <mxGeometry height="42" width="42" x="910" y="915" as="geometry" />
        </mxCell>
        <mxCell id="r2-ic3" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#0284C7;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.bedrock;fontFamily=Helvetica;" value="Titan Vector" vertex="1">
          <mxGeometry height="42" width="42" x="1050" y="915" as="geometry" />
        </mxCell>
        <mxCell id="r2-desc" parent="1" style="text;html=1;align=left;fontSize=11;fontColor=#555;fontFamily=Helvetica;" value="• Phân phối file tải qua CloudFront Signed URLs Edge Caching.&lt;br&gt;• Direct Multipart Upload lên S3 giảm 80% tải Fargate compute.&lt;br&gt;• Tìm kiếm tệp theo ngữ nghĩa bằng Bedrock Titan Embeddings." vertex="1">
          <mxGeometry height="45" width="550" x="725" y="995" as="geometry" />
        </mxCell>

        <!-- Phase 3 Card -->
        <mxCell id="rd-card-3" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;fontSize=12;fontFamily=Helvetica;" value="" vertex="1">
          <mxGeometry height="190" width="590" x="1350" y="865" as="geometry" />
        </mxCell>
        <mxCell id="rd-t3" parent="1" style="text;html=1;align=left;fontSize=13;fontStyle=1;fontColor=#0369A1;fontFamily=Helvetica;" value="Phase 3 (3 - 6 tháng): Enterprise SaaS &amp; Multi-Region" vertex="1">
          <mxGeometry height="24" width="400" x="1365" y="875" as="geometry" />
        </mxCell>
        <!-- Phase 3 Icons -->
        <mxCell id="r3-ic1" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#8C4FFF;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.api_gateway;fontFamily=Helvetica;" value="Dev Portal" vertex="1">
          <mxGeometry height="42" width="42" x="1420" y="915" as="geometry" />
        </mxCell>
        <mxCell id="r3-ic2" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#16A34A;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.s3;fontFamily=Helvetica;" value="S3 CRR Backup" vertex="1">
          <mxGeometry height="42" width="42" x="1560" y="915" as="geometry" />
        </mxCell>
        <mxCell id="r3-ic3" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#8C4FFF;strokeColor=none;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.route_53;fontFamily=Helvetica;" value="R53 Failover" vertex="1">
          <mxGeometry height="42" width="42" x="1700" y="915" as="geometry" />
        </mxCell>
        <mxCell id="r3-desc" parent="1" style="text;html=1;align=left;fontSize=11;fontColor=#555;fontFamily=Helvetica;" value="• Swagger UI + SDK Generator + API Key Throttling.&lt;br&gt;• Multi-Region Disaster Recovery (S3 CRR + Aurora Global DB).&lt;br&gt;• DLP chống rò rỉ dữ liệu thẻ/CCCD &amp; đóng dấu Watermark PDF." vertex="1">
          <mxGeometry height="45" width="550" x="1365" y="995" as="geometry" />
        </mxCell>

      </root>
    </mxGraphModel>
  </diagram>
</mxfile>"""
    return xml

if __name__ == "__main__":
    path = "docs/storix_gap_roadmap_minimalist.drawio"
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_minimalist_xml())
    print(f"Generated {path}")
