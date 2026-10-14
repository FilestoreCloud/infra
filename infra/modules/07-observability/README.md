# Module 07: Observability & Monitoring

Dedicated observability, metrics dashboard, log aggregation, and real-time operational alerting module for the Nextcloud Multi-Tenant SaaS platform on AWS.

---

## 1. Overview & Architecture

Module 07 provisions the centralized observability infrastructure for the entire SaaS platform:

- **Unified CloudWatch Operational Dashboard:**
  - Tenant Storage Utilization (auto-discovered dynamically using CloudWatch `SEARCH()` expressions across all tenant namespaces).
  - Tenant Lifecycle Status (Active: 1, Suspended: 0).
  - Application Load Balancer (ALB) Request Rate and Average Target Response Latency.
  - ALB HTTP 5xx Error Spike tracking.
  - ECS Fargate Task Container CPU & Memory Utilization.
  - ECS Running Task count tracking for auto-scaling health.
- **Proactive CloudWatch Metric Alarms:**
  - `ALB5xxErrorRateAlarm`: Triggers when HTTP 5xx error rate exceeds 5 for 2 consecutive 1-minute intervals.
  - `ALBHighLatencyAlarm`: Triggers when ALB target latency exceeds 1.5 seconds for 3 consecutive intervals.
  - `ECSHighCPUAlarm`: Triggers when Nextcloud ECS service CPU exceeds 85% for 3 consecutive 5-minute intervals.
  - `ECSHighMemoryAlarm`: Triggers when Nextcloud ECS service Memory exceeds 85% for 3 consecutive intervals.
  - `RDSHighCPUAlarm`: Triggers when RDS PostgreSQL CPU exceeds 80% for 3 consecutive intervals.
- **Centralized Alerts SNS Topic:**
  - `ObservabilityNotificationTopic`: Delivers critical operational alerts to administrative subscribers.
- **Platform Log Group:**
  - `/aws/observability/${EnvironmentName}-nextcloud` with 90-day retention for platform-wide metrics and diagnostics.

---

## 2. Directory Contents

| File                               | Purpose                                                                                          |
| ---------------------------------- | ------------------------------------------------------------------------------------------------ |
| [`template.yaml`](template.yaml)   | CloudFormation template provisioning CloudWatch Dashboard, Alarms, SNS topic, and SSM parameters |
| [`dashboard.json`](dashboard.json) | CloudWatch operational telemetry dashboard definition source                                     |

---

## 3. CloudFormation Exports & Contract Outputs

| Export Name                                                      | Description                                             |
| ---------------------------------------------------------------- | ------------------------------------------------------- |
| `${EnvironmentName}-nextcloud-CloudWatchDashboardName`           | Physical name of the CloudWatch operational dashboard   |
| `${EnvironmentName}-nextcloud-CloudWatchDashboardURL`            | Direct AWS Management Console URL to view the dashboard |
| `${EnvironmentName}-nextcloud-ObservabilityNotificationTopicArn` | Central SNS Topic ARN for all metric alarms             |
| `${EnvironmentName}-nextcloud-ALB5xxErrorRateAlarmArn`           | CloudWatch Alarm ARN for ALB 5xx errors                 |
| `${EnvironmentName}-nextcloud-ALBHighLatencyAlarmArn`            | CloudWatch Alarm ARN for high latency                   |
| `${EnvironmentName}-nextcloud-ECSHighCPUAlarmArn`                | CloudWatch Alarm ARN for ECS CPU spikes                 |
| `${EnvironmentName}-nextcloud-ECSHighMemoryAlarmArn`             | CloudWatch Alarm ARN for ECS Memory spikes              |
| `${EnvironmentName}-nextcloud-RDSHighCPUAlarmArn`                | CloudWatch Alarm ARN for RDS CPU spikes                 |
