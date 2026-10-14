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
	elbv2 "github.com/aws/aws-sdk-go-v2/service/elasticloadbalancingv2"
	elbv2Types "github.com/aws/aws-sdk-go-v2/service/elasticloadbalancingv2/types"
	http_helper "github.com/gruntwork-io/terratest/modules/http-helper"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestInPlaceCompute verifies live Module 05 (ECS Fargate, ALB, Target Groups & App Health).
func TestInPlaceCompute(t *testing.T) {
	cfg := LoadInPlaceConfig(t)
	stackName := cfg.GetStackName("05", "compute")

	outputs, exists := cfg.GetStackOutputs(t, stackName)
	if !exists {
		t.Skipf("Stack %s is not deployed yet; skipping In-Place Compute test.", stackName)
		return
	}

	clusterName, hasCluster := outputs["ECSClusterName"]
	require.True(t, hasCluster, "Output ECSClusterName must exist")
	serviceName, hasService := outputs["ECSServiceName"]
	require.True(t, hasService, "Output ECSServiceName must exist")
	albURL, hasURL := outputs["LoadBalancerURL"]
	require.True(t, hasURL, "Output LoadBalancerURL must exist")
	tgArn, hasTG := outputs["DefaultTargetGroupArn"]
	require.True(t, hasTG, "Output DefaultTargetGroupArn must exist")

	// 1. Assert ECS Fargate Service Status & Task Count
	t.Logf("🚀 [In-Place] Validating ECS Fargate Service: %s (Cluster: %s)", serviceName, clusterName)
	ecsClient := ecs.NewFromConfig(cfg.awsConfig)
	svcRes, err := ecsClient.DescribeServices(context.TODO(), &ecs.DescribeServicesInput{
		Cluster:  aws.String(clusterName),
		Services: []string{serviceName},
	})
	require.NoError(t, err, "DescribeServices API call failed")
	require.NotEmpty(t, svcRes.Services, "Service not found in ECS Cluster")
	ecsSvc := svcRes.Services[0]
	assert.Equal(t, "ACTIVE", *ecsSvc.Status, "ECS Service status must be ACTIVE")
	assert.GreaterOrEqual(t, ecsSvc.RunningCount, int32(1), "ECS Service must have at least 1 running task")

	// 2. Assert ALB Target Group Health (Container Healthy)
	t.Logf("🎯 [In-Place] Validating ALB Target Health: %s", tgArn)
	elbClient := elbv2.NewFromConfig(cfg.awsConfig)
	healthRes, err := elbClient.DescribeTargetHealth(context.TODO(), &elbv2.DescribeTargetHealthInput{
		TargetGroupArn: aws.String(tgArn),
	})
	require.NoError(t, err, "DescribeTargetHealth API call failed")
	hasHealthyTarget := false
	for _, target := range healthRes.TargetHealthDescriptions {
		if target.TargetHealth != nil && target.TargetHealth.State == elbv2Types.TargetHealthStateEnumHealthy {
			hasHealthyTarget = true
			break
		}
	}
	assert.True(t, hasHealthyTarget, "At least 1 container target in the ALB Target Group must be HEALTHY")

	// 3. Probe Live Nextcloud Endpoint via HTTP/HTTPS
	statusEndpoint := fmt.Sprintf("%s/status.php", strings.TrimRight(albURL, "/"))
	t.Logf("🌐 [In-Place] Testing live Nextcloud health endpoint: %s", statusEndpoint)

	tlsConfig := &tls.Config{InsecureSkipVerify: true}
	retries := 10
	sleepBetweenRetries := 5 * time.Second

	http_helper.HttpGetWithRetryWithCustomValidation(
		t,
		statusEndpoint,
		tlsConfig,
		retries,
		sleepBetweenRetries,
		func(statusCode int, body string) bool {
			if statusCode != 200 {
				t.Logf("Awaiting Nextcloud ready status: HTTP %d...", statusCode)
				return false
			}
			return strings.Contains(body, "installed") || strings.Contains(body, "version")
		},
	)

	t.Logf("✅ [In-Place] Module 05 Compute & ALB validation passed (App is LIVE at %s)", statusEndpoint)
}
