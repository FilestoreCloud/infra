package terratest

import (
	"context"
	"crypto/tls"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/ecs"
	ecsTypes "github.com/aws/aws-sdk-go-v2/service/ecs/types"
	elbv2 "github.com/aws/aws-sdk-go-v2/service/elasticloadbalancingv2"
	elbv2Types "github.com/aws/aws-sdk-go-v2/service/elasticloadbalancingv2/types"
	http_helper "github.com/gruntwork-io/terratest/modules/http-helper"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestInPlaceResilience_ECSFargateSelfHealing tests automated recovery (Self-Healing)
// when an ECS Fargate container dies unexpectedly.
//
// Chaos Scenario:
// 1. Steady State: Verify current task is running, ALB Target Group is healthy, and /status.php is 200.
// 2. Chaos Injection: Stop the currently active Fargate task via AWS SDK (simulating OOM or crash).
// 3. Self-Healing Observation: Measure MTTR (Mean Time To Recovery).
// 4. Assertion: ECS Service auto-spawns a new task, registers to ALB, and passes health check within SLA (< 180s).
func TestInPlaceResilience_ECSFargateSelfHealing(t *testing.T) {
	cfg := LoadInPlaceConfig(t)
	stackName := cfg.GetStackName("05", "compute")

	outputs, exists := cfg.GetStackOutputs(t, stackName)
	if !exists {
		t.Skipf("Stack %s is not deployed yet; skipping In-Place Resilience test.", stackName)
		return
	}

	clusterName, hasCluster := outputs["ECSClusterName"]
	require.True(t, hasCluster, "Output ECSClusterName must exist")
	serviceName, hasService := outputs["ECSServiceName"]
	require.True(t, hasService, "Output ECSServiceName must exist")
	albURL, hasURL := outputs["LoadBalancerURL"]
	require.True(t, hasURL, "Output LoadBalancerURL must exist")
	tgArn, hasTG := outputs["DefaultTargetGroupArn"]
	if !hasTG || tgArn == "" {
		tgArn, hasTG = outputs["TargetGroupArn"]
	}
	if !hasTG || tgArn == "" {
		elbClient := elbv2.NewFromConfig(cfg.awsConfig)
		tgRes, err := elbClient.DescribeTargetGroups(context.TODO(), &elbv2.DescribeTargetGroupsInput{
			Names: []string{fmt.Sprintf("%s-nextcloud-tg", cfg.Environment)},
		})
		if err == nil && len(tgRes.TargetGroups) > 0 {
			tgArn = *tgRes.TargetGroups[0].TargetGroupArn
			hasTG = true
		}
	}
	require.True(t, hasTG, "Target Group ARN must exist (either via Output DefaultTargetGroupArn or lookup)")

	ecsClient := ecs.NewFromConfig(cfg.awsConfig)
	elbClient := elbv2.NewFromConfig(cfg.awsConfig)
	tlsConfig := &tls.Config{InsecureSkipVerify: true}
	statusEndpoint := fmt.Sprintf("%s/status.php", strings.TrimRight(albURL, "/"))

	// -------------------------------------------------------------
	// Phase 1: Verify Steady State (Hypothesis of Normal Behavior)
	// -------------------------------------------------------------
	t.Logf("🔍 [Phase 1: Steady State] Verifying normal service health before chaos...")

	listTasksRes, err := ecsClient.ListTasks(context.TODO(), &ecs.ListTasksInput{
		Cluster:       aws.String(clusterName),
		ServiceName:   aws.String(serviceName),
		DesiredStatus: ecsTypes.DesiredStatusRunning,
	})
	require.NoError(t, err, "Failed to list running ECS tasks")
	require.NotEmpty(t, listTasksRes.TaskArns, "Must have at least 1 running ECS task before injecting chaos")

	initialTaskArn := listTasksRes.TaskArns[0]
	t.Logf("   -> Current healthy task ARN: %s", initialTaskArn)

	// Quick check steady-state HTTP 200
	statusCode, body := http_helper.HttpGet(t, statusEndpoint, tlsConfig)
	require.Equal(t, 200, statusCode, "Steady state health endpoint must return 200 OK")
	t.Logf("   -> Steady state verified: HTTP %d (Response: %s)", statusCode, strings.TrimSpace(body))

	// -------------------------------------------------------------
	// Phase 2: Chaos Injection (Terminate active container)
	// -------------------------------------------------------------
	t.Logf("💥 [Phase 2: Chaos Injection] Killing active Fargate task to simulate sudden container crash...")
	chaosStartTime := time.Now()

	_, err = ecsClient.StopTask(context.TODO(), &ecs.StopTaskInput{
		Cluster: aws.String(clusterName),
		Task:    aws.String(initialTaskArn),
		Reason:  aws.String("Terratest Chaos Injection: Self-Healing Resilience Verification"),
	})
	require.NoError(t, err, "Failed to stop ECS task for chaos experiment")
	t.Logf("   -> Terminated task: %s at %s", initialTaskArn, chaosStartTime.Format(time.RFC3339))

	// -------------------------------------------------------------
	// Phase 3: Observe Self-Healing & MTTR (Mean Time To Recovery)
	// -------------------------------------------------------------
	t.Logf("⏱️ [Phase 3: Self-Healing] Waiting for ECS auto-recovery and ALB target re-registration...")

	// SLA Max Recovery Duration: 180 seconds (Fargate provisioning + Nextcloud container boot + ALB health checks)
	maxWaitTime := 3 * time.Minute
	pollInterval := 5 * time.Second
	recovered := false
	var recoveryDuration time.Duration
	var replacementTaskArn string

	timeoutChan := time.After(maxWaitTime)
	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()

Loop:
	for {
		select {
		case <-timeoutChan:
			t.Fatalf("❌ SLA Breached: Service did not recover within %v", maxWaitTime)
		case <-ticker.C:
			elapsed := time.Since(chaosStartTime).Round(time.Second)

			// Step A: Check if a new task is in RUNNING state
			currentTasks, err := ecsClient.ListTasks(context.TODO(), &ecs.ListTasksInput{
				Cluster:       aws.String(clusterName),
				ServiceName:   aws.String(serviceName),
				DesiredStatus: ecsTypes.DesiredStatusRunning,
			})
			if err != nil || len(currentTasks.TaskArns) == 0 {
				t.Logf("   [%s] Awaiting new task spawn in ECS cluster...", elapsed)
				continue
			}

			// Ensure the newly running task is different from the terminated task
			newRunningTask := currentTasks.TaskArns[0]
			if newRunningTask == initialTaskArn {
				t.Logf("   [%s] Old task still draining/shutting down...", elapsed)
				continue
			}
			replacementTaskArn = newRunningTask

			// Step B: Check if ALB Target Group has marked the new container HEALTHY
			healthRes, err := elbClient.DescribeTargetHealth(context.TODO(), &elbv2.DescribeTargetHealthInput{
				TargetGroupArn: aws.String(tgArn),
			})
			if err != nil {
				continue
			}

			isTargetHealthy := false
			for _, desc := range healthRes.TargetHealthDescriptions {
				if desc.TargetHealth != nil && desc.TargetHealth.State == elbv2Types.TargetHealthStateEnumHealthy {
					isTargetHealthy = true
					break
				}
			}

			if !isTargetHealthy {
				t.Logf("   [%s] New task running (%s), awaiting ALB Target Health status HEALTHY...", elapsed, replacementTaskArn)
				continue
			}

			// Step C: Verify live HTTP request succeeds
			code, respBody := http_helper.HttpGet(t, statusEndpoint, tlsConfig)
			if code == 200 && (strings.Contains(respBody, "installed") || strings.Contains(respBody, "version")) {
				recoveryDuration = time.Since(chaosStartTime)
				recovered = true
				t.Logf("   [%s] App successfully restored and serving traffic! HTTP %d", elapsed, code)
				break Loop
			} else {
				t.Logf("   [%s] Target is healthy in ALB, waiting for Nextcloud app response (HTTP %d)...", elapsed, code)
			}
		}
	}

	// -------------------------------------------------------------
	// Phase 4: Final Assertions & SLA Metrics
	// -------------------------------------------------------------
	require.True(t, recovered, "Service must fully self-heal after container crash")
	assert.NotEmpty(t, replacementTaskArn, "Replacement task ARN must be detected")
	assert.NotEqual(t, initialTaskArn, replacementTaskArn, "Replacement task must be a fresh task instance")

	t.Logf("==========================================================================")
	t.Logf("🎉 [Resilience Test Passed] Self-Healing Verified Successfully!")
	t.Logf("   • Terminated Task (Chaos): %s", initialTaskArn)
	t.Logf("   • Replacement Task (Healed): %s", replacementTaskArn)
	t.Logf("   • Measured MTTR: %v (Target SLA: < %v)", recoveryDuration.Round(time.Millisecond), maxWaitTime)
	t.Logf("   • Health Endpoint: %s -> HTTP 200 OK", statusEndpoint)
	t.Logf("==========================================================================")
}
