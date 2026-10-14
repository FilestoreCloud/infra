package terratest

import (
	"context"
	"fmt"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch"
	cwTypes "github.com/aws/aws-sdk-go-v2/service/cloudwatch/types"
	"github.com/aws/aws-sdk-go-v2/service/sns"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestInPlaceObservability verifies Module 07 (CloudWatch Dashboard, Metric Alarms & SNS Topics).
func TestInPlaceObservability(t *testing.T) {
	cfg := LoadInPlaceConfig(t)
	stackName := cfg.GetStackName("07", "observability")

	outputs, exists := cfg.GetStackOutputs(t, stackName)
	if !exists {
		t.Skipf("Stack %s is not deployed yet; skipping In-Place Observability test.", stackName)
		return
	}

	dashboardName, hasDash := outputs["CloudWatchDashboardName"]
	require.True(t, hasDash, "Output CloudWatchDashboardName must exist")
	require.NotEmpty(t, dashboardName, "CloudWatchDashboardName must not be empty")

	snsTopicArn, hasSNS := outputs["ObservabilityNotificationTopicArn"]
	require.True(t, hasSNS, "Output ObservabilityNotificationTopicArn must exist")
	require.NotEmpty(t, snsTopicArn, "ObservabilityNotificationTopicArn must not be empty")

	// 1. Assert CloudWatch Operational Dashboard is active
	t.Logf("📊 [In-Place] Validating Central CloudWatch Dashboard: %s", dashboardName)
	cwClient := cloudwatch.NewFromConfig(cfg.awsConfig)
	dashRes, err := cwClient.GetDashboard(context.TODO(), &cloudwatch.GetDashboardInput{
		DashboardName: aws.String(dashboardName),
	})
	require.NoError(t, err, fmt.Sprintf("Failed to fetch dashboard %s", dashboardName))
	require.NotNil(t, dashRes.DashboardArn, "Dashboard ARN must not be nil")
	assert.Contains(t, *dashRes.DashboardArn, dashboardName, "Dashboard ARN must contain dashboard name")

	// 2. Assert SNS Observability Alert Topic is ready
	t.Logf("🔔 [In-Place] Validating SNS Alerts Topic: %s", snsTopicArn)
	snsClient := sns.NewFromConfig(cfg.awsConfig)
	topicRes, err := snsClient.GetTopicAttributes(context.TODO(), &sns.GetTopicAttributesInput{
		TopicArn: aws.String(snsTopicArn),
	})
	require.NoError(t, err, fmt.Sprintf("Failed to get attributes for SNS topic %s", snsTopicArn))
	require.NotEmpty(t, topicRes.Attributes, "SNS topic attributes must not be empty")

	// 3. Assert SRE Platform Alarms are NOT in ALARM state
	alarmOutputs := []string{
		"ALB5xxErrorRateAlarmArn",
		"ALBHighLatencyAlarmArn",
		"ECSHighCPUAlarmArn",
		"ECSHighMemoryAlarmArn",
		"RDSHighCPUAlarmArn",
	}

	t.Logf("🚨 [In-Place] Auditing CloudWatch Metric Alarms state...")
	for _, alarmKey := range alarmOutputs {
		alarmArn, hasAlarm := outputs[alarmKey]
		if !hasAlarm || alarmArn == "" {
			continue
		}
		// Alarm name is the last component of ARN (after :alarm:)
		parts := aws.ToString(&alarmArn)
		alarmName := parts
		if idx := len("arn:aws:cloudwatch:"); idx < len(parts) {
			split := aws.ToString(&alarmArn)
			if n := split[len(split)-stringsLastIndex(split, ":"):]; n != "" {
				alarmName = n
			}
		}

		alarmsRes, err := cwClient.DescribeAlarms(context.TODO(), &cloudwatch.DescribeAlarmsInput{
			AlarmNames: []string{alarmName},
		})
		if err == nil && len(alarmsRes.MetricAlarms) > 0 {
			alarm := alarmsRes.MetricAlarms[0]
			t.Logf("  • Alarm %s status: %s", *alarm.AlarmName, alarm.StateValue)
			assert.NotEqual(t, cwTypes.StateValueAlarm, alarm.StateValue,
				fmt.Sprintf("Alarm %s is currently firing (State: ALARM)!", *alarm.AlarmName))
		}
	}

	t.Logf("✅ [In-Place] Module 07 Observability verification passed for %s", stackName)
}

func stringsLastIndex(s string, sep string) int {
	for i := len(s) - 1; i >= 0; i-- {
		if s[i] == sep[0] {
			return len(s) - 1 - i
		}
	}
	return len(s)
}
