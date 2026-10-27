import os
import xml.etree.ElementTree as ET

def build_drawio_xml():
    # Colors:
    # Implemented: Stroke #2E7D32, Fill #E8F5E9 (Green)
    # Gap / Need Upgrade: Stroke #E65100, Fill #FFF3E0 (Orange)
    # Future Roadmap: Stroke #0284C7, Fill #E0F2FE (Blue)

    xml_content = """<mxfile host="Electron" agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) draw.io/29.6.1 Chrome/142.0.7444.265 Electron/39.8.0 Safari/537.36" version="29.6.1">
  <diagram name="Storix-Gap-Analysis-Roadmap" id="storix-gap-roadmap">
    <mxGraphModel dx="2400" dy="1600" grid="0" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="2200" pageHeight="1450" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />

        <!-- ============================================================== -->
        <!-- HEADER BLOCK                                                   -->
        <!-- ============================================================== -->
        <mxCell id="hdr-group" connectable="0" parent="1" style="group;fontFamily=Helvetica;" value="" vertex="1">
          <mxGeometry height="90" width="2100" x="50" y="30" as="geometry" />
        </mxCell>
        <mxCell id="hdr-title" parent="hdr-group" style="text;html=1;align=left;verticalAlign=middle;fontSize=26;fontStyle=1;fontFamily=Helvetica;fontColor=#232F3E;" value="Storix Multi-Tenant Platform — Gap Analysis &amp; Evolutionary Roadmap" vertex="1">
          <mxGeometry height="36" width="1300" x="0" y="0" as="geometry" />
        </mxCell>
        <mxCell id="hdr-sub" parent="hdr-group" style="text;html=1;align=left;verticalAlign=middle;fontSize=14;fontFamily=Helvetica;fontColor=#545B64;" value="Comparison of Implemented Capabilities vs. Requirements Gaps and 3-Phase Strategic Evolution Plan" vertex="1">
          <mxGeometry height="24" width="1400" x="0" y="38" as="geometry" />
        </mxCell>
        <mxCell id="hdr-line" parent="hdr-group" style="line;strokeWidth=2;html=1;strokeColor=#FF9900;" value="" vertex="1">
          <mxGeometry height="10" width="2100" x="0" y="68" as="geometry" />
        </mxCell>

        <!-- ============================================================== -->
        <!-- LEGEND STATUS BANNER                                           -->
        <!-- ============================================================== -->
        <mxCell id="legend-box" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#D5DBDB;strokeWidth=1;shadow=1;fontFamily=Helvetica;" value="" vertex="1">
          <mxGeometry height="54" width="920" x="1230" y="35" as="geometry" />
        </mxCell>
        <!-- Item 1: Implemented -->
        <mxCell id="leg-box-1" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#E8F5E9;strokeColor=#2E7D32;strokeWidth=2;" value="" vertex="1">
          <mxGeometry height="22" width="34" x="1250" y="51" as="geometry" />
        </mxCell>
        <mxCell id="leg-txt-1" parent="1" style="text;html=1;align=left;verticalAlign=middle;fontSize=12;fontStyle=1;fontColor=#2E7D32;fontFamily=Helvetica;" value="Đã đạt được (Implemented)" vertex="1">
          <mxGeometry height="24" width="170" x="1295" y="50" as="geometry" />
        </mxCell>
        <!-- Item 2: Gaps / Upgrades -->
        <mxCell id="leg-box-2" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF3E0;strokeColor=#E65100;strokeWidth=2;dashed=1;" value="" vertex="1">
          <mxGeometry height="22" width="34" x="1540" y="51" as="geometry" />
        </mxCell>
        <mxCell id="leg-txt-2" parent="1" style="text;html=1;align=left;verticalAlign=middle;fontSize=12;fontStyle=1;fontColor=#E65100;fontFamily=Helvetica;" value="Chưa đạt / Cần nâng cấp (Gaps)" vertex="1">
          <mxGeometry height="24" width="190" x="1585" y="50" as="geometry" />
        </mxCell>
        <!-- Item 3: Future Roadmap -->
        <mxCell id="leg-box-3" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#E0F2FE;strokeColor=#0284C7;strokeWidth=2;dashed=1;dashPattern=2 2;" value="" vertex="1">
          <mxGeometry height="22" width="34" x="1850" y="51" as="geometry" />
        </mxCell>
        <mxCell id="leg-txt-3" parent="1" style="text;html=1;align=left;verticalAlign=middle;fontSize=12;fontStyle=1;fontColor=#0284C7;fontFamily=Helvetica;" value="Lộ trình tương lai (Roadmap)" vertex="1">
          <mxGeometry height="24" width="180" x="1895" y="50" as="geometry" />
        </mxCell>

        <!-- ============================================================== -->
        <!-- ZONE 1: CLIENTS & ACCESS CONTROL (Left Column)                 -->
        <!-- ============================================================== -->
        <mxCell id="zone-clients" parent="1" style="rounded=1;whiteSpace=wrap;html=1;strokeColor=#2E7D32;strokeWidth=2;fillColor=#F1F8E9;verticalAlign=top;align=left;spacingLeft=16;spacingTop=12;fontStyle=1;fontSize=14;fontColor=#1B5E20;fontFamily=Helvetica;" value="1. Access Control &amp; APIs (Hiện tại &amp; Nâng cấp)" vertex="1">
          <mxGeometry height="1260" width="380" x="50" y="140" as="geometry" />
        </mxCell>

        <!-- Actors -->
        <mxCell id="act-tenant-user" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#232F3D;strokeColor=#ffffff;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.users;fontFamily=Helvetica;" value="Tenant Members &amp; Users" vertex="1">
          <mxGeometry height="44" width="44" x="80" y="190" as="geometry" />
        </mxCell>
        <mxCell id="act-guest-user" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#232F3D;strokeColor=#ffffff;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.user;fontFamily=Helvetica;" value="External Guests (Public Link)" vertex="1">
          <mxGeometry height="44" width="44" x="200" y="190" as="geometry" />
        </mxCell>
        <mxCell id="act-admin-user" parent="1" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#4338CA;strokeColor=#ffffff;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.authenticated_user;fontFamily=Helvetica;" value="SuperAdmin (WebAuthn/MFA)" vertex="1">
          <mxGeometry height="44" width="44" x="320" y="190" as="geometry" />
        </mxCell>

        <!-- Current APIs Box -->
        <mxCell id="card-api-current" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#E8F5E9;strokeColor=#2E7D32;strokeWidth=1.5;verticalAlign=top;align=left;spacingLeft=12;spacingTop=10;fontSize=12;fontFamily=Helvetica;" value="&lt;b&gt;ĐÃ ĐẠT: RESTful &amp; WebDAV APIs&lt;/b&gt;&lt;br&gt;&lt;hr&gt;&lt;ul style=&quot;margin-left:-18px;margin-top:4px;&quot;&gt;&lt;li&gt;&lt;b&gt;WebDAV (RFC 4918):&lt;/b&gt; Streaming, Chunked Upload, Range Download, Delete.&lt;/li&gt;&lt;li&gt;&lt;b&gt;Nextcloud OCS REST API:&lt;/b&gt; Shares, Tags, Users, Quota, Metadata (JSON/XML).&lt;/li&gt;&lt;li&gt;&lt;b&gt;RBAC &amp; Sharing:&lt;/b&gt; Password, Expiration, Drop-box upload-only, Group Folders.&lt;/li&gt;&lt;li&gt;&lt;b&gt;Control Plane API:&lt;/b&gt; Tenant CRUD, Suspend/Resume SAGA, Async OCC.&lt;/li&gt;&lt;/ul&gt;" vertex="1">
          <mxGeometry height="190" width="340" x="70" y="270" as="geometry" />
        </mxCell>

        <!-- Current Security & Audit Box -->
        <mxCell id="card-audit-current" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#E8F5E9;strokeColor=#2E7D32;strokeWidth=1.5;verticalAlign=top;align=left;spacingLeft=12;spacingTop=10;fontSize=12;fontFamily=Helvetica;" value="&lt;b&gt;ĐÃ ĐẠT: Audit Logging &amp; IAM&lt;/b&gt;&lt;br&gt;&lt;hr&gt;&lt;ul style=&quot;margin-left:-18px;margin-top:4px;&quot;&gt;&lt;li&gt;&lt;b&gt;SuperAdmin Audit:&lt;/b&gt; DynamoDB Audit Table (1-year TTL, immutability).&lt;/li&gt;&lt;li&gt;&lt;b&gt;Data Plane Audit:&lt;/b&gt; Nextcloud &lt;code&gt;admin_audit&lt;/code&gt; app ghi lại file_create, read, delete, share.&lt;/li&gt;&lt;li&gt;&lt;b&gt;Biometric MFA:&lt;/b&gt; FIDO2 Touch ID / Face ID WebAuthn Passkeys.&lt;/li&gt;&lt;li&gt;&lt;b&gt;CloudWatch EMF:&lt;/b&gt; Structured audit metrics.&lt;/li&gt;&lt;/ul&gt;" vertex="1">
          <mxGeometry height="180" width="340" x="70" y="480" as="geometry" />
        </mxCell>

        <!-- GAP: Direct Presigned URL Access -->
        <mxCell id="card-gap-presigned" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF3E0;strokeColor=#E65100;strokeWidth=2;dashed=1;verticalAlign=top;align=left;spacingLeft=12;spacingTop=10;fontSize=12;fontFamily=Helvetica;" value="&lt;b style=&quot;color:#C62828;&quot;&gt;CHƯA CÓ: S3 Presigned URL I/O Bypass&lt;/b&gt;&lt;br&gt;&lt;hr&gt;&lt;ul style=&quot;margin-left:-18px;margin-top:4px;&quot;&gt;&lt;li&gt;&lt;b&gt;Hiện trạng:&lt;/b&gt; 100% Upload/Download phải chạy xuyên qua PHP Fargate Container → Nghẽn CPU/RAM khi file lớn.&lt;/li&gt;&lt;li&gt;&lt;b&gt;Nâng cấp:&lt;/b&gt; Triển khai API cấp S3 Presigned URL để client Upload/Download trực tiếp tới S3.&lt;/li&gt;&lt;/ul&gt;" vertex="1">
          <mxGeometry height="160" width="340" x="70" y="680" as="geometry" />
        </mxCell>

        <!-- GAP: Developer Portal & Custom Rate Limiting -->
        <mxCell id="card-gap-devportal" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF3E0;strokeColor=#E65100;strokeWidth=2;dashed=1;verticalAlign=top;align=left;spacingLeft=12;spacingTop=10;fontSize=12;fontFamily=Helvetica;" value="&lt;b style=&quot;color:#C62828;&quot;&gt;CHƯA CÓ: Developer Portal &amp; Swagger UI&lt;/b&gt;&lt;br&gt;&lt;hr&gt;&lt;ul style=&quot;margin-left:-18px;margin-top:4px;&quot;&gt;&lt;li&gt;&lt;b&gt;Hiện trạng:&lt;/b&gt; Thiếu tài liệu API OpenAPI/Swagger công khai cho 3rd-party integration.&lt;/li&gt;&lt;li&gt;&lt;b&gt;Nâng cấp:&lt;/b&gt; Cung cấp Swagger UI, SDK Generator (Python/TypeScript), API Key management.&lt;/li&gt;&lt;/ul&gt;" vertex="1">
          <mxGeometry height="160" width="340" x="70" y="860" as="geometry" />
        </mxCell>

        <!-- ROADMAP: CloudFront CDN Edge & DLP -->
        <mxCell id="card-road-cdn" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#E0F2FE;strokeColor=#0284C7;strokeWidth=2;dashed=1;dashPattern=2 2;verticalAlign=top;align=left;spacingLeft=12;spacingTop=10;fontSize=12;fontFamily=Helvetica;" value="&lt;b style=&quot;color:#0369A1;&quot;&gt;ROADMAP: Edge CDN &amp; DLP Protection&lt;/b&gt;&lt;br&gt;&lt;hr&gt;&lt;ul style=&quot;margin-left:-18px;margin-top:4px;&quot;&gt;&lt;li&gt;&lt;b&gt;CloudFront Signed URLs:&lt;/b&gt; Tải file cực nhanh tại Edge location toàn cầu.&lt;/li&gt;&lt;li&gt;&lt;b&gt;DLP (Data Loss Prevention):&lt;/b&gt; Tự động quét số thẻ tín dụng, CCCD, đóng watermark bản quyền lên file PDF.&lt;/li&gt;&lt;/ul&gt;" vertex="1">
          <mxGeometry height="160" width="340" x="70" y="1040" as="geometry" />
        </mxCell>


        <!-- ============================================================== -->
        <!-- ZONE 2: CORE MULTI-TENANT SYSTEM (Middle Column)               -->
        <!-- ============================================================== -->
        <mxCell id="zone-core" parent="1" style="rounded=1;whiteSpace=wrap;html=1;strokeColor=#2E7D32;strokeWidth=2;fillColor=#F9FBE7;verticalAlign=top;align=left;spacingLeft=16;spacingTop=12;fontStyle=1;fontSize=14;fontColor=#1B5E20;fontFamily=Helvetica;" value="2. Scalable Multi-Tenant Architecture &amp; File Operations (Sản phẩm cốt lõi)" vertex="1">
          <mxGeometry height="1260" width="820" x="460" y="140" as="geometry" />
        </mxCell>

        <!-- Ingress WAF & ALB -->
        <mxCell id="box-ingress" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#E8F5E9;strokeColor=#2E7D32;strokeWidth=1.5;verticalAlign=top;align=left;spacingLeft=12;spacingTop=8;fontSize=11;fontFamily=Helvetica;" value="&lt;b&gt;ĐÃ ĐẠT: Ingress &amp; Traffic Routing&lt;/b&gt;&lt;br&gt;AWS WAFv2 (OWASP Rules) + Multi-AZ ALB Host-Header Routing (&lt;i&gt;&lt;tenant&gt;.png261.dev&lt;/i&gt;) + TLS 1.3" vertex="1">
          <mxGeometry height="70" width="780" x="480" y="180" as="geometry" />
        </mxCell>

        <!-- Tenant Compute Isolation (Fargate) -->
        <mxCell id="box-compute" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#E8F5E9;strokeColor=#2E7D32;strokeWidth=1.5;verticalAlign=top;align=left;spacingLeft=12;spacingTop=8;fontSize=12;fontFamily=Helvetica;" value="&lt;b&gt;ĐÃ ĐẠT: Container-per-Tenant Compute Isolation (Amazon ECS Fargate ARM64)&lt;/b&gt;" vertex="1">
          <mxGeometry height="260" width="780" x="480" y="270" as="geometry" />
        </mxCell>

        <!-- Tenant A Container -->
        <mxCell id="tnt-a" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;verticalAlign=top;align=left;spacingLeft=10;spacingTop=6;fontSize=11;fontFamily=Helvetica;" value="&lt;b&gt;ECS Task: service-acme&lt;/b&gt;&lt;br&gt;&lt;span style=&quot;font-size:10px;color:#555;&quot;&gt;• Nextcloud 30 (Graviton ARM64)&lt;br&gt;• APCu Local Memcache&lt;br&gt;• LiteLLM Sidecar (127.0.0.1:4000)&lt;br&gt;• SOCI Instant Cold Start &amp;lt; 15s&lt;br&gt;• Scale-to-Zero Compute FinOps&lt;/span&gt;" vertex="1">
          <mxGeometry height="180" width="230" x="500" y="315" as="geometry" />
        </mxCell>

        <!-- Tenant B Container -->
        <mxCell id="tnt-b" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;verticalAlign=top;align=left;spacingLeft=10;spacingTop=6;fontSize=11;fontFamily=Helvetica;" value="&lt;b&gt;ECS Task: service-marvel&lt;/b&gt;&lt;br&gt;&lt;span style=&quot;font-size:10px;color:#555;&quot;&gt;• Nextcloud 30 (Graviton ARM64)&lt;br&gt;• APCu Local Memcache&lt;br&gt;• LiteLLM Sidecar (127.0.0.1:4000)&lt;br&gt;• SOCI Instant Cold Start &amp;lt; 15s&lt;br&gt;• Scale-to-Zero Compute FinOps&lt;/span&gt;" vertex="1">
          <mxGeometry height="180" width="230" x="755" y="315" as="geometry" />
        </mxCell>

        <!-- Tenant Provisioning / Step Functions -->
        <mxCell id="tnt-ctrl" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#7C3AED;strokeWidth=1.5;verticalAlign=top;align=left;spacingLeft=10;spacingTop=6;fontSize=11;fontFamily=Helvetica;" value="&lt;b&gt;Step Functions SAGA&lt;/b&gt;&lt;br&gt;&lt;span style=&quot;font-size:10px;color:#555;&quot;&gt;• Provisioning Workflow&lt;br&gt;• Suspend / Resume Engine&lt;br&gt;• Deprovisioning Rollback&lt;br&gt;• EventBridge Dedicated Cron&lt;br&gt;• DynamoDB Tenant Registry&lt;/span&gt;" vertex="1">
          <mxGeometry height="180" width="245" x="1005" y="315" as="geometry" />
        </mxCell>

        <!-- UPGRADE: ElastiCache Redis Cluster -->
        <mxCell id="box-gap-redis" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF3E0;strokeColor=#E65100;strokeWidth=2;dashed=1;verticalAlign=top;align=left;spacingLeft=12;spacingTop=8;fontSize=11;fontFamily=Helvetica;" value="&lt;b style=&quot;color:#C62828;&quot;&gt;CHƯA CÓ: Distributed File Locking &amp; Session Store (Amazon ElastiCache Redis)&lt;/b&gt;&lt;br&gt;&lt;span style=&quot;font-size:11px;&quot;&gt;Hiện tại dùng APCu cục bộ trong container. Khi Fargate tự động mở rộng theo tải (&amp;gt; 1 replica), bắt buộc cần cụm Redis tập trung để tránh xung đột file lock và mất session.&lt;/span&gt;" vertex="1">
          <mxGeometry height="75" width="780" x="480" y="550" as="geometry" />
        </mxCell>

        <!-- Multi-Tenant Database Layer -->
        <mxCell id="box-db" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#E8F5E9;strokeColor=#2E7D32;strokeWidth=1.5;verticalAlign=top;align=left;spacingLeft=12;spacingTop=8;fontSize=12;fontFamily=Helvetica;" value="&lt;b&gt;ĐÃ ĐẠT: Database-per-Tenant Isolation &amp; Connection Pooling&lt;/b&gt;&lt;br&gt;&lt;span style=&quot;font-size:11px;&quot;&gt;Amazon RDS Proxy (chống cạn kiệt connection pool khi scale) → Amazon RDS PostgreSQL 16 (Catalogs: &lt;code&gt;nc_acme&lt;/code&gt;, &lt;code&gt;nc_marvel&lt;/code&gt;). Đầy đủ metadata table &lt;code&gt;oc_filecache&lt;/code&gt;, &lt;code&gt;oc_systemtag&lt;/code&gt;, &lt;code&gt;oc_files_versions&lt;/code&gt;.&lt;/span&gt;" vertex="1">
          <mxGeometry height="100" width="780" x="480" y="645" as="geometry" />
        </mxCell>

        <!-- Multi-Tenant Storage Layer -->
        <mxCell id="box-storage" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#E8F5E9;strokeColor=#2E7D32;strokeWidth=1.5;verticalAlign=top;align=left;spacingLeft=12;spacingTop=8;fontSize=12;fontFamily=Helvetica;" value="&lt;b&gt;ĐÃ ĐẠT: Multi-Tenant Storage Tiering (S3 Vault + EFS Access Points)&lt;/b&gt;&lt;br&gt;&lt;span style=&quot;font-size:11px;&quot;&gt;• &lt;b&gt;Amazon EFS:&lt;/b&gt; Config mount cô lập tuyệt đối theo Access Point (&lt;code&gt;/tenants/&amp;lt;id&amp;gt;/config&lt;/code&gt;, UID/GID 33:33). Lifecycle: 30d IA, 90d Archive.&lt;br&gt;• &lt;b&gt;Amazon S3 Vault:&lt;/b&gt; Prefix-isolated (&lt;code&gt;s3://vault/tenants/&amp;lt;id&amp;gt;/*&lt;/code&gt;) với S3 Intelligent-Tiering &amp; KMS Server-Side Encryption.&lt;/span&gt;" vertex="1">
          <mxGeometry height="100" width="780" x="480" y="765" as="geometry" />
        </mxCell>

        <!-- GAP: Antivirus / S3 Malware Protection Pipeline -->
        <mxCell id="box-gap-malware" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF3E0;strokeColor=#E65100;strokeWidth=2;dashed=1;verticalAlign=top;align=left;spacingLeft=12;spacingTop=8;fontSize=11;fontFamily=Helvetica;" value="&lt;b style=&quot;color:#C62828;&quot;&gt;CHƯA CÓ: Tự động quét mã độc tệp tải lên (AWS GuardDuty Malware Protection / ClamAV Pipeline)&lt;/b&gt;&lt;br&gt;&lt;span style=&quot;font-size:11px;&quot;&gt;Thiếu cơ chế EventBridge bắt sự kiện S3 ObjectCreated để quét mã độc trước khi cho phép user khác download; thiếu Quarantine Bucket để cách ly file nhiễm.&lt;/span&gt;" vertex="1">
          <mxGeometry height="80" width="780" x="480" y="885" as="geometry" />
        </mxCell>

        <!-- ROADMAP: Multi-Region Disaster Recovery -->
        <mxCell id="box-road-dr" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#E0F2FE;strokeColor=#0284C7;strokeWidth=2;dashed=1;dashPattern=2 2;verticalAlign=top;align=left;spacingLeft=12;spacingTop=8;fontSize=11;fontFamily=Helvetica;" value="&lt;b style=&quot;color:#0369A1;&quot;&gt;ROADMAP: Multi-Region Disaster Recovery (Active-Passive Global Resilience)&lt;/b&gt;&lt;br&gt;&lt;span style=&quot;font-size:11px;&quot;&gt;• Amazon S3 Cross-Region Replication (CRR) sang secondary region (e.g. us-east-1).&lt;br&gt;• Amazon Aurora Global Database hoặc RDS Cross-Region Automated Snapshots.&lt;br&gt;• Amazon Route 53 DNS Automated Health Check Failover (RPO &amp;lt; 5m, RTO &amp;lt; 15m).&lt;/span&gt;" vertex="1">
          <mxGeometry height="95" width="780" x="480" y="985" as="geometry" />
        </mxCell>

        <!-- Telemetry & Health -->
        <mxCell id="box-telemetry" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#E8F5E9;strokeColor=#2E7D32;strokeWidth=1.5;verticalAlign=top;align=left;spacingLeft=12;spacingTop=8;fontSize=11;fontFamily=Helvetica;" value="&lt;b&gt;ĐÃ ĐẠT: 24/7 SLA Synthetics Canary &amp; Health Monitoring&lt;/b&gt;&lt;br&gt;AWS CloudWatch Synthetics liên tục gửi HTTP request probe tới từng tenant domain; tự động kích hoạt CloudWatch Alarms." vertex="1">
          <mxGeometry height="65" width="780" x="480" y="1100" as="geometry" />
        </mxCell>


        <!-- ============================================================== -->
        <!-- ZONE 3: METADATA & SEARCH EVOLUTION (Right Column)             -->
        <!-- ============================================================== -->
        <mxCell id="zone-search" parent="1" style="rounded=1;whiteSpace=wrap;html=1;strokeColor=#E65100;strokeWidth=2;fillColor=#FFF8E1;verticalAlign=top;align=left;spacingLeft=16;spacingTop=12;fontStyle=1;fontSize=14;fontColor=#B78103;fontFamily=Helvetica;" value="3. Metadata Management &amp; Content Search Evolution" vertex="1">
          <mxGeometry height="1260" width="820" x="1310" y="140" as="geometry" />
        </mxCell>

        <!-- Current Search Status -->
        <mxCell id="card-curr-search" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#E8F5E9;strokeColor=#2E7D32;strokeWidth=1.5;verticalAlign=top;align=left;spacingLeft=12;spacingTop=10;fontSize=12;fontFamily=Helvetica;" value="&lt;b&gt;ĐÃ ĐẠT: SQL Database Metadata Search &amp; Generative AI Assistant&lt;/b&gt;&lt;br&gt;&lt;hr&gt;&lt;ul style=&quot;margin-left:-18px;margin-top:4px;&quot;&gt;&lt;li&gt;&lt;b&gt;Metadata Search:&lt;/b&gt; Tìm kiếm cực nhanh theo thuộc tính tệp (filename, path, size, date, mimetype, tags) thông qua index bảng &lt;code&gt;oc_filecache&lt;/code&gt; trong PostgreSQL.&lt;/li&gt;&lt;li&gt;&lt;b&gt;AI Integration:&lt;/b&gt; LiteLLM Sidecar + Claude 3.5 Sonnet on Amazon Bedrock hỗ trợ chat, hỏi đáp, tóm tắt tài liệu.&lt;/li&gt;&lt;/ul&gt;" vertex="1">
          <mxGeometry height="140" width="780" x="1330" y="180" as="geometry" />
        </mxCell>

        <!-- GAP / MISSING: Deep Full-Text Content Search -->
        <mxCell id="card-gap-search" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF3E0;strokeColor=#E65100;strokeWidth=2;dashed=1;verticalAlign=top;align=left;spacingLeft=12;spacingTop=10;fontSize=12;fontFamily=Helvetica;" value="&lt;b style=&quot;color:#C62828;&quot;&gt;KHOẢNG TRỐNG CỐT LÕI (GAP): Chưa có Full-Text Search qua nội dung tệp (File Content Search)&lt;/b&gt;&lt;br&gt;&lt;hr&gt;&lt;p style=&quot;font-size:11px;line-height:1.4;&quot;&gt;Đề bài yêu cầu: &lt;i&gt;&quot;efficient search functionality across file content and attributes&quot;&lt;/i&gt;.&lt;br&gt;Hiện tại chỉ search được &lt;b&gt;attributes&lt;/b&gt; trong SQL. Khi số lượng file lên hàng triệu tệp PDF, DOCX, XLSX, TXT, việc tìm từ khóa &lt;b&gt;bên trong nội dung tệp&lt;/b&gt; (file content) bằng SQL sẽ thất bại hoặc không khả thi do thiếu Full-Text Inverted Index, OCR hình ảnh và Stemming/Tokenization.&lt;/p&gt;" vertex="1">
          <mxGeometry height="150" width="780" x="1330" y="340" as="geometry" />
        </mxCell>

        <!-- PROPOSED ARCHITECTURE FOR FULL-TEXT SEARCH -->
        <mxCell id="box-search-arch" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#E65100;strokeWidth=2;verticalAlign=top;align=left;spacingLeft=12;spacingTop=8;fontSize=12;fontFamily=Helvetica;" value="&lt;b style=&quot;color:#E65100;&quot;&gt;KIẾN TRÚC ĐỀ XUẤT: Serverless Full-Text Content Indexing Pipeline&lt;/b&gt;" vertex="1">
          <mxGeometry height="360" width="780" x="1330" y="510" as="geometry" />
        </mxCell>

        <!-- Step 1 in Pipeline -->
        <mxCell id="pipe-1" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF3E0;strokeColor=#E65100;fontSize=11;align=center;fontFamily=Helvetica;" value="&lt;b&gt;1. S3 Event Notification&lt;/b&gt;&lt;br&gt;&lt;span style=&quot;font-size:10px;&quot;&gt;Khi có file upload mới&lt;br&gt;(&lt;code&gt;ObjectCreated:*&lt;/code&gt;)&lt;/span&gt;" vertex="1">
          <mxGeometry height="80" width="160" x="1350" y="560" as="geometry" />
        </mxCell>
        <!-- Arrow 1-2 -->
        <mxCell id="arr-1" edge="1" parent="1" source="pipe-1" target="pipe-2" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#E65100;strokeWidth=2;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <!-- Step 2: SQS Queue -->
        <mxCell id="pipe-2" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF3E0;strokeColor=#E65100;fontSize=11;align=center;fontFamily=Helvetica;" value="&lt;b&gt;2. Amazon SQS Buffer&lt;/b&gt;&lt;br&gt;&lt;span style=&quot;font-size:10px;&quot;&gt;Hàng đợi đệm chống quá tải&lt;br&gt;(Dead-Letter Queue retry)&lt;/span&gt;" vertex="1">
          <mxGeometry height="80" width="160" x="1550" y="560" as="geometry" />
        </mxCell>
        <!-- Arrow 2-3 -->
        <mxCell id="arr-2" edge="1" parent="1" source="pipe-2" target="pipe-3" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#E65100;strokeWidth=2;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <!-- Step 3: Textract & Tika Lambda / Fargate -->
        <mxCell id="pipe-3" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF3E0;strokeColor=#E65100;fontSize=11;align=center;fontFamily=Helvetica;" value="&lt;b&gt;3. Ingestion Worker&lt;/b&gt;&lt;br&gt;&lt;span style=&quot;font-size:10px;&quot;&gt;AWS Lambda + Apache Tika&lt;br&gt;/ Amazon Textract (OCR)&lt;br&gt;Trích xuất raw text từ file&lt;/span&gt;" vertex="1">
          <mxGeometry height="80" width="170" x="1750" y="560" as="geometry" />
        </mxCell>
        <!-- Arrow 3-4 -->
        <mxCell id="arr-3" edge="1" parent="1" source="pipe-3" target="pipe-4" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#E65100;strokeWidth=2;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <!-- Step 4: Amazon OpenSearch Service -->
        <mxCell id="pipe-4" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF3E0;strokeColor=#E65100;strokeWidth=2;fontSize=12;align=center;fontFamily=Helvetica;" value="&lt;b&gt;4. Amazon OpenSearch Service (Chỉ mục toàn văn)&lt;/b&gt;&lt;br&gt;&lt;span style=&quot;font-size:10px;&quot;&gt;Chỉ mục riêng biệt từng tenant: &lt;code&gt;index_tenant_acme&lt;/code&gt;, &lt;code&gt;index_marvel&lt;/code&gt;&lt;br&gt;Hỗ trợ Highlight từ khóa, Fuzzy Search, Auto-complete, Boolean Query&lt;/span&gt;" vertex="1">
          <mxGeometry height="90" width="570" x="1350" y="680" as="geometry" />
        </mxCell>
        <!-- Pipeline benefits note -->
        <mxCell id="pipe-note" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FAFAFA;strokeColor=#CCCCCC;fontSize=10;align=left;spacingLeft=8;fontFamily=Helvetica;" value="&lt;b&gt;Lợi ích:&lt;/b&gt; Hoàn toàn bất đồng bộ (async), không làm chậm tốc độ upload tệp của người dùng; mở rộng không giới hạn theo khối lượng dữ liệu." vertex="1">
          <mxGeometry height="50" width="740" x="1350" y="800" as="geometry" />
        </mxCell>

        <!-- ROADMAP: AI Semantic Search & Vector Embeddings -->
        <mxCell id="card-road-vector" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#E0F2FE;strokeColor=#0284C7;strokeWidth=2;dashed=1;dashPattern=2 2;verticalAlign=top;align=left;spacingLeft=12;spacingTop=10;fontSize=12;fontFamily=Helvetica;" value="&lt;b style=&quot;color:#0369A1;&quot;&gt;ROADMAP ĐỘT PHÁ: Semantic Search &amp; Vector Embeddings (Amazon Bedrock)&lt;/b&gt;&lt;br&gt;&lt;hr&gt;&lt;p style=&quot;font-size:11px;line-height:1.4;&quot;&gt;• Sử dụng &lt;b&gt;Amazon Titan Embeddings G1&lt;/b&gt; để vector hóa từng đoạn văn bản trong tài liệu.&lt;br&gt;• Lưu trữ vector tại &lt;b&gt;OpenSearch Serverless Vector Engine&lt;/b&gt; (k-NN search).&lt;br&gt;• Cho phép người dùng tìm kiếm theo ý nghĩa tự nhiên (Ví dụ: &lt;i&gt;&quot;Báo cáo tài chính quý 3 có doanh thu vượt kế hoạch&quot;&lt;/i&gt;) ngay cả khi văn bản không chứa chính xác từ khóa đó.&lt;br&gt;• Tích hợp Retrieval-Augmented Generation (RAG) vào giao diện Nextcloud Assistant.&lt;/p&gt;" vertex="1">
          <mxGeometry height="160" width="780" x="1330" y="890" as="geometry" />
        </mxCell>

        <!-- ROADMAP SUMMARY PHASES TABLE -->
        <mxCell id="card-phases-table" parent="1" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#0284C7;strokeWidth=1.5;verticalAlign=top;align=left;spacingLeft=12;spacingTop=10;fontSize=12;fontFamily=Helvetica;" value="&lt;b style=&quot;color:#0369A1;&quot;&gt;LỘ TRÌNH TRIỂN KHAI CHI TIẾT (3-PHASE EXECUTION PLAN)&lt;/b&gt;&lt;br&gt;&lt;hr&gt;&lt;table style=&quot;font-size:10.5px;width:100%;border-collapse:collapse;margin-top:6px;&quot;&gt;&lt;tr style=&quot;background:#F0F9FF;font-weight:bold;&quot;&gt;&lt;td style=&quot;padding:4px;&quot;&gt;Giai đoạn&lt;/td&gt;&lt;td style=&quot;padding:4px;&quot;&gt;Mục tiêu trọng tâm&lt;/td&gt;&lt;td style=&quot;padding:4px;&quot;&gt;Hạng mục kỹ thuật chính&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td style=&quot;padding:4px;border-top:1px solid #E2E8F0;&quot;&gt;&lt;b&gt;Phase 1 (1-2 tháng)&lt;/b&gt;&lt;/td&gt;&lt;td style=&quot;padding:4px;border-top:1px solid #E2E8F0;&quot;&gt;Khắc phục Gaps tìm kiếm &amp; An toàn&lt;/td&gt;&lt;td style=&quot;padding:4px;border-top:1px solid #E2E8F0;&quot;&gt;OpenSearch Full-Text Search, S3 Malware Scan, ElastiCache Redis Cluster&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td style=&quot;padding:4px;border-top:1px solid #E2E8F0;&quot;&gt;&lt;b&gt;Phase 2 (2-3 tháng)&lt;/b&gt;&lt;/td&gt;&lt;td style=&quot;padding:4px;border-top:1px solid #E2E8F0;&quot;&gt;Tối ưu hiệu năng I/O &amp; AI Semantic&lt;/td&gt;&lt;td style=&quot;padding:4px;border-top:1px solid #E2E8F0;&quot;&gt;Presigned URLs Direct-to-S3, CloudFront Signed CDN, Bedrock Titan Embeddings&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td style=&quot;padding:4px;border-top:1px solid #E2E8F0;&quot;&gt;&lt;b&gt;Phase 3 (3-6 tháng)&lt;/b&gt;&lt;/td&gt;&lt;td style=&quot;padding:4px;border-top:1px solid #E2E8F0;&quot;&gt;Enterprise Governance &amp; Global DR&lt;/td&gt;&lt;td style=&quot;padding:4px;border-top:1px solid #E2E8F0;&quot;&gt;Developer Swagger Portal, API Key Metering, Multi-Region DR (CRR &amp; Aurora Global)&lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;" vertex="1">
          <mxGeometry height="160" width="780" x="1330" y="1070" as="geometry" />
        </mxCell>

      </root>
    </mxGraphModel>
  </diagram>
</mxfile>"""
    return xml_content

if __name__ == "__main__":
    out_path = "docs/storix_gap_analysis_and_roadmap.drawio"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(build_drawio_xml())
    print(f"Generated {out_path}")
