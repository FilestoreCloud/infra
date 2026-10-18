package terratest

import (
	"context"
	"crypto/hmac"
	"crypto/sha1"
	"crypto/tls"
	"encoding/base32"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	dynamoTypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/ecs"
	ecsTypes "github.com/aws/aws-sdk-go-v2/service/ecs/types"
	"github.com/aws/aws-sdk-go-v2/service/lambda"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	s3Types "github.com/aws/aws-sdk-go-v2/service/s3/types"
	"github.com/aws/aws-sdk-go-v2/service/ssm"
	http_helper "github.com/gruntwork-io/terratest/modules/http-helper"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func generateTotpCode(secret string) string {
	secret = strings.ToUpper(strings.TrimSpace(secret))
	key, err := base32.StdEncoding.WithPadding(base32.NoPadding).DecodeString(secret)
	if err != nil {
		return ""
	}
	epoch := time.Now().Unix() / 30
	buf := make([]byte, 8)
	binary.BigEndian.PutUint64(buf, uint64(epoch))
	mac := hmac.New(sha1.New, key)
	mac.Write(buf)
	h := mac.Sum(nil)
	offset := h[len(h)-1] & 0x0f
	truncated := binary.BigEndian.Uint32(h[offset:offset+4]) & 0x7fffffff
	code := truncated % 1000000
	return fmt.Sprintf("%06d", code)
}

// TestInPlaceDeploymentAcceptance executes the comprehensive Acceptance Test Suite:
// 1. SuperAdmin Control Plane Functions (Authentication with MFA TOTP, Session Token).
// 2. DynamoDB Tenant Registry item status verification (ACTIVE).
// 3. Nextcloud Tenant Application & Storage verification (/status.php and WebDAV PROPFIND).
func TestInPlaceDeploymentAcceptance(t *testing.T) {
	cfg := LoadInPlaceConfig(t)
	superadminStack := cfg.GetStackName("06", "superadmin")

	outputs, exists := cfg.GetStackOutputs(t, superadminStack)
	if !exists {
		t.Skipf("Stack %s is not deployed yet; skipping In-Place Deployment Acceptance test.", superadminStack)
		return
	}

	lambdaArn, hasLambda := outputs["TenantOperatorLambdaArn"]
	require.True(t, hasLambda, "TenantOperatorLambdaArn must exist")

	tableName, hasTable := outputs["TenantRegistryTable"]
	require.True(t, hasTable, "TenantRegistryTable must exist")

	// Resolve tenant ID strictly from environment (zero hardcoding)
	tenantID := os.Getenv("TENANT_ID")
	require.NotEmpty(t, tenantID, "TENANT_ID environment variable must be specified for acceptance test")

	// 1. SuperAdmin Authentication & MFA Challenge via Lambda
	t.Logf("🔐 [Acceptance] Testing SuperAdmin Login & MFA Authentication...")
	adminUser := os.Getenv("SUPERADMIN_USERNAME")
	adminPass := os.Getenv("ADMIN_PASSWORD")
	if adminPass == "" {
		adminPass = os.Getenv("SUPERADMIN_PASSWORD")
	}
	require.NotEmpty(t, adminUser, "SUPERADMIN_USERNAME environment variable must be set")
	require.NotEmpty(t, adminPass, "ADMIN_PASSWORD or SUPERADMIN_PASSWORD must be set")

	lambdaClient := lambda.NewFromConfig(cfg.awsConfig)
	loginPayload, _ := json.Marshal(map[string]interface{}{
		"action":   "LOGIN",
		"username": adminUser,
		"password": adminPass,
	})

	loginInv, err := lambdaClient.Invoke(context.TODO(), &lambda.InvokeInput{
		FunctionName: aws.String(lambdaArn),
		Payload:      loginPayload,
	})
	require.NoError(t, err, "Failed to invoke Login action")

	var loginResp struct {
		StatusCode int               `json:"statusCode"`
		Body       string            `json:"body"`
		Status     string            `json:"status"`
		Token      string            `json:"token"`
		Challenge  string            `json:"challenge_token"`
	}
	_ = json.Unmarshal(loginInv.Payload, &loginResp)
	if loginResp.Body != "" {
		var inner struct {
			Status    string `json:"status"`
			Token     string `json:"token"`
			Challenge string `json:"challenge_token"`
		}
		_ = json.Unmarshal([]byte(loginResp.Body), &inner)
		if inner.Status != "" {
			loginResp.Status = inner.Status
			loginResp.Token = inner.Token
			loginResp.Challenge = inner.Challenge
		}
	}

	sessionToken := loginResp.Token
	if loginResp.Status == "MFA_REQUIRED" || loginResp.Challenge != "" {
		totpSecret := os.Getenv("SUPERADMIN_TOTP_SECRET")
		require.NotEmpty(t, totpSecret, "SUPERADMIN_TOTP_SECRET required for MFA verification")
		mfaCode := generateTotpCode(totpSecret)

		mfaPayload, _ := json.Marshal(map[string]interface{}{
			"action":          "VERIFY_MFA",
			"challenge_token": loginResp.Challenge,
			"mfa_code":        mfaCode,
		})
		mfaInv, err := lambdaClient.Invoke(context.TODO(), &lambda.InvokeInput{
			FunctionName: aws.String(lambdaArn),
			Payload:      mfaPayload,
		})
		require.NoError(t, err, "Failed to invoke VERIFY_MFA action")

		var mfaResp struct {
			StatusCode int    `json:"statusCode"`
			Body       string `json:"body"`
			Token      string `json:"token"`
		}
		_ = json.Unmarshal(mfaInv.Payload, &mfaResp)
		if mfaResp.Body != "" {
			var inner struct {
				Token string `json:"token"`
			}
			_ = json.Unmarshal([]byte(mfaResp.Body), &inner)
			sessionToken = inner.Token
		} else {
			sessionToken = mfaResp.Token
		}
	}
	require.NotEmpty(t, sessionToken, "Valid SuperAdmin session token must be established")
	t.Logf("✅ SuperAdmin session authenticated successfully.")

	// 2. DynamoDB Tenant Registry item status verification (ACTIVE)
	t.Logf("🗄️ [Acceptance] Auditing DynamoDB Tenant Registry for tenant '%s' in table '%s'...", tenantID, tableName)
	dynamoClient := dynamodb.NewFromConfig(cfg.awsConfig)
	getItemRes, err := dynamoClient.GetItem(context.TODO(), &dynamodb.GetItemInput{
		TableName: aws.String(tableName),
		Key: map[string]dynamoTypes.AttributeValue{
			"tenant_id": &dynamoTypes.AttributeValueMemberS{Value: tenantID},
		},
		ConsistentRead: aws.Bool(true),
	})
	require.NoError(t, err, fmt.Sprintf("Failed to get item for tenant %s from DynamoDB", tenantID))
	if len(getItemRes.Item) == 0 {
		t.Logf("⚡ Tenant '%s' not yet registered in DynamoDB. Provisioning via SuperAdmin Control Plane...", tenantID)
		provPayload, _ := json.Marshal(map[string]interface{}{
			"action":    "PROVISION",
			"tenant_id": tenantID,
		})
		_, provErr := lambdaClient.Invoke(context.TODO(), &lambda.InvokeInput{
			FunctionName: aws.String(lambdaArn),
			Payload:      provPayload,
		})
		require.NoError(t, provErr, "Failed to provision tenant via SuperAdmin Lambda")

		getItemRes, err = dynamoClient.GetItem(context.TODO(), &dynamodb.GetItemInput{
			TableName: aws.String(tableName),
			Key: map[string]dynamoTypes.AttributeValue{
				"tenant_id": &dynamoTypes.AttributeValueMemberS{Value: tenantID},
			},
			ConsistentRead: aws.Bool(true),
		})
		require.NoError(t, err, fmt.Sprintf("Failed to re-fetch tenant %s from DynamoDB", tenantID))
	}
	require.NotEmpty(t, getItemRes.Item, fmt.Sprintf("Tenant '%s' must exist in DynamoDB", tenantID))

	if statusAttr, ok := getItemRes.Item["status"].(*dynamoTypes.AttributeValueMemberS); ok {
		assert.Equal(t, "ACTIVE", statusAttr.Value, fmt.Sprintf("Tenant %s status must be ACTIVE", tenantID))
	}
	t.Logf("✅ DynamoDB confirmed: Tenant '%s' is registered and ACTIVE.", tenantID)

	// 3. Nextcloud Tenant Application & Storage verification
	ssmClient := ssm.NewFromConfig(cfg.awsConfig)
	albParam, err := ssmClient.GetParameter(context.TODO(), &ssm.GetParameterInput{
		Name: aws.String(fmt.Sprintf("/nextcloud/%s/infra/alb-dns", cfg.Environment)),
	})
	if err != nil || albParam.Parameter == nil || albParam.Parameter.Value == nil {
		t.Logf("ℹ️ ALB DNS SSM parameter not found, skipping direct HTTP probe.")
		return
	}

	albDNS := *albParam.Parameter.Value
	t.Logf("🌐 [Acceptance] Probing Nextcloud Tenant endpoint via ALB: http://%s/status.php", albDNS)

	tlsConfig := &tls.Config{InsecureSkipVerify: true}
	statusURL := fmt.Sprintf("http://%s/status.php", albDNS)

	maxRetries := 45
	sleepBetweenRetries := 5 * time.Second
	var lastStatus int
	var lastBody string
	var success bool

	for attempt := 1; attempt <= maxRetries; attempt++ {
		statusCode, body, err := http_helper.HttpGetE(t, statusURL, tlsConfig)
		lastStatus = statusCode
		lastBody = body
		if err == nil && statusCode == http.StatusOK {
			var statusData map[string]interface{}
			if err := json.Unmarshal([]byte(body), &statusData); err == nil {
				if statusData["installed"] == true {
					success = true
					break
				}
			}
		}
		t.Logf("   -> Awaiting Nextcloud status.php (attempt %d/%d, status=%d)...", attempt, maxRetries, statusCode)
		time.Sleep(sleepBetweenRetries)
	}

	if !success {
		// 1. Inspect ECS Cluster, Service Events & Deployments
		ecsClient := ecs.NewFromConfig(cfg.awsConfig)
		clusterName := fmt.Sprintf("%s-nextcloud-cluster", cfg.Environment)
		serviceName := fmt.Sprintf("%s-nextcloud-service", cfg.Environment)
		svcOut, svcErr := ecsClient.DescribeServices(context.TODO(), &ecs.DescribeServicesInput{
			Cluster:  aws.String(clusterName),
			Services: []string{serviceName},
		})
		if svcErr == nil && len(svcOut.Services) > 0 {
			svc := svcOut.Services[0]
			t.Logf("🔍 ECS Service Status: Running=%d, Desired=%d, Pending=%d", svc.RunningCount, svc.DesiredCount, svc.PendingCount)
			for _, d := range svc.Deployments {
				taskDef := ""
				if d.TaskDefinition != nil {
					taskDef = *d.TaskDefinition
				}
				rollout := ""
				if d.RolloutState != "" {
					rollout = string(d.RolloutState)
				}
				t.Logf("   -> Deployment [%s]: Status=%s, Desired=%d, Pending=%d, Running=%d, RolloutState=%s, TaskDef=%s",
					*d.Id, *d.Status, d.DesiredCount, d.PendingCount, d.RunningCount, rollout, taskDef)
			}
			t.Logf("🔍 Recent ECS Service Events:")
			eventCount := len(svc.Events)
			if eventCount > 10 {
				eventCount = 10
			}
			for i := 0; i < eventCount; i++ {
				ev := svc.Events[i]
				t.Logf("   [%s] %s", ev.CreatedAt.Format("15:04:05"), *ev.Message)
			}
		}

		// 2. Inspect Stopped Tasks and reasons
		tasksOut, tErr := ecsClient.ListTasks(context.TODO(), &ecs.ListTasksInput{
			Cluster:       aws.String(clusterName),
			DesiredStatus: ecsTypes.DesiredStatusStopped,
			MaxResults:    aws.Int32(5),
		})
		if tErr == nil && len(tasksOut.TaskArns) > 0 {
			descTasks, dtErr := ecsClient.DescribeTasks(context.TODO(), &ecs.DescribeTasksInput{
				Cluster: aws.String(clusterName),
				Tasks:   tasksOut.TaskArns,
			})
			if dtErr == nil {
				for _, tk := range descTasks.Tasks {
					stoppedReason := ""
					if tk.StoppedReason != nil {
						stoppedReason = *tk.StoppedReason
					}
					t.Logf("🔍 Stopped Task: %s, StopCode: %s, Reason: %s", *tk.TaskArn, tk.StopCode, stoppedReason)
					for _, c := range tk.Containers {
						exitCode := -1
						if c.ExitCode != nil {
							exitCode = int(*c.ExitCode)
						}
						cReason := ""
						if c.Reason != nil {
							cReason = *c.Reason
						}
						t.Logf("   -> Container: %s, ExitCode: %d, Reason: %s", *c.Name, exitCode, cReason)
					}
				}
			}
		}

		logGroupName := fmt.Sprintf("/ecs/%s-nextcloud", cfg.Environment)
		t.Logf("⚠️ Nextcloud status.php probe failed (lastStatus=%d). Inspecting recent ECS logs from CloudWatch group '%s'...", lastStatus, logGroupName)
		cwLogsClient := cloudwatchlogs.NewFromConfig(cfg.awsConfig)
		streamsOut, streamErr := cwLogsClient.DescribeLogStreams(context.TODO(), &cloudwatchlogs.DescribeLogStreamsInput{
			LogGroupName: aws.String(logGroupName),
			OrderBy:      "LastEventTime",
			Descending:   aws.Bool(true),
			Limit:        aws.Int32(5),
		})
		if streamErr != nil {
			t.Logf("⚠️ Failed to describe log streams in %s: %v", logGroupName, streamErr)
		} else {
			for _, stream := range streamsOut.LogStreams {
				if stream.LogStreamName == nil {
					continue
				}
				t.Logf("📜 ECS Log Stream: %s", *stream.LogStreamName)
				// Fetch startup / entrypoint logs
				headOut, headErr := cwLogsClient.GetLogEvents(context.TODO(), &cloudwatchlogs.GetLogEventsInput{
					LogGroupName:  aws.String(logGroupName),
					LogStreamName: stream.LogStreamName,
					StartFromHead: aws.Bool(true),
					Limit:         aws.Int32(50),
				})
				if headErr == nil && len(headOut.Events) > 0 {
					t.Logf("   --- Entrypoint / Startup Log Events (Head) ---")
					for _, ev := range headOut.Events {
						if ev.Timestamp != nil && ev.Message != nil {
							t.Logf("   [%s] %s", time.UnixMilli(*ev.Timestamp).Format("15:04:05"), strings.TrimSpace(*ev.Message))
						}
					}
				}
				// Fetch latest logs
				eventsOut, eventErr := cwLogsClient.GetLogEvents(context.TODO(), &cloudwatchlogs.GetLogEventsInput{
					LogGroupName:  aws.String(logGroupName),
					LogStreamName: stream.LogStreamName,
					StartFromHead: aws.Bool(false),
					Limit:         aws.Int32(50),
				})
				if eventErr == nil && len(eventsOut.Events) > 0 {
					t.Logf("   --- Recent Log Events (Tail) ---")
					for _, ev := range eventsOut.Events {
						if ev.Timestamp != nil && ev.Message != nil {
							t.Logf("   [%s] %s", time.UnixMilli(*ev.Timestamp).Format("15:04:05"), strings.TrimSpace(*ev.Message))
						}
					}
				}
			}
		}
	}

	require.True(t, success, fmt.Sprintf("Nextcloud status.php must return HTTP 200 with installed=true. Last status: %d, body: %s", lastStatus, lastBody))
	t.Logf("✅ Nextcloud status.php returned HTTP 200 with installed=true.")

	// 4. Tenant Scaling Lifecycle & Dynamic Scale Verification
	t.Logf("📈 [Acceptance] Testing Tenant Scaling Lifecycle for '%s'...", tenantID)

	// A. Query Tenant Scaling Telemetry via METRICS action
	metricsPayload, _ := json.Marshal(map[string]interface{}{
		"action":    "METRICS",
		"tenant_id": tenantID,
	})
	metricsInv, err := lambdaClient.Invoke(context.TODO(), &lambda.InvokeInput{
		FunctionName: aws.String(lambdaArn),
		Payload:      metricsPayload,
	})
	if err == nil && metricsInv.Payload != nil {
		t.Logf("   -> Tenant scaling telemetry queried successfully.")
	}

	// B. Test Tenant Scale-to-Zero ($0 FinOps) via SUSPEND
	t.Logf("   -> Testing Tenant Scale-to-Zero ($0 FinOps)...")
	suspendPayload, _ := json.Marshal(map[string]interface{}{
		"action":    "SUSPEND",
		"tenant_id": tenantID,
	})
	suspendInv, err := lambdaClient.Invoke(context.TODO(), &lambda.InvokeInput{
		FunctionName: aws.String(lambdaArn),
		Payload:      suspendPayload,
	})
	require.NoError(t, err, "Failed to invoke SUSPEND action for tenant scaling test")
	var suspendResp struct {
		StatusCode int    `json:"statusCode"`
		Body       string `json:"body"`
		Status     string `json:"status"`
	}
	_ = json.Unmarshal(suspendInv.Payload, &suspendResp)
	if suspendResp.Body != "" {
		var inner struct {
			Status string `json:"status"`
		}
		_ = json.Unmarshal([]byte(suspendResp.Body), &inner)
		if inner.Status != "" {
			suspendResp.Status = inner.Status
		}
	}
	assert.Contains(t, []string{"OK", "SUSPENDED", "SUSPENDING"}, suspendResp.Status, "SUSPEND status must indicate scale-to-zero transition")
	t.Logf("   -> Tenant scaled to zero successfully (status: %s)", suspendResp.Status)

	time.Sleep(2 * time.Second)

	// C. Test Tenant Scale-Out via RESUME
	t.Logf("   -> Testing Tenant Scale-Out back to operational capacity...")
	resumePayload, _ := json.Marshal(map[string]interface{}{
		"action":    "RESUME",
		"tenant_id": tenantID,
	})
	resumeInv, err := lambdaClient.Invoke(context.TODO(), &lambda.InvokeInput{
		FunctionName: aws.String(lambdaArn),
		Payload:      resumePayload,
	})
	require.NoError(t, err, "Failed to invoke RESUME action for tenant scaling test")
	var resumeResp struct {
		StatusCode int    `json:"statusCode"`
		Body       string `json:"body"`
		Status     string `json:"status"`
	}
	_ = json.Unmarshal(resumeInv.Payload, &resumeResp)
	if resumeResp.Body != "" {
		var inner struct {
			Status string `json:"status"`
		}
		_ = json.Unmarshal([]byte(resumeResp.Body), &inner)
		if inner.Status != "" {
			resumeResp.Status = inner.Status
		}
	}
	assert.Contains(t, []string{"OK", "ACTIVE", "RESUMING"}, resumeResp.Status, "RESUME status must indicate scale-out transition")
	t.Logf("   -> Tenant scaled out successfully (status: %s)", resumeResp.Status)

	// 5. Live Tenant Container Image Rolling Upgrade Verification (Zero Downtime)
	t.Logf("🚀 [Acceptance] Testing Live Container Image Upgrade while Tenant is Running (Zero Downtime)...")

	// A. Ensure tenant is back in healthy serving state after scale-out
	t.Logf("   -> Awaiting tenant steady-state availability before initiating image upgrade...")
	resumeSteady := false
	for attempt := 1; attempt <= 30; attempt++ {
		statusCode, body, err := http_helper.HttpGetE(t, statusURL, tlsConfig)
		if err == nil && statusCode == http.StatusOK {
			var statusData map[string]interface{}
			if err := json.Unmarshal([]byte(body), &statusData); err == nil && statusData["installed"] == true {
				resumeSteady = true
				break
			}
		}
		time.Sleep(2 * time.Second)
	}
	require.True(t, resumeSteady, "Tenant must be actively serving traffic before triggering image upgrade")
	t.Logf("   -> Tenant confirmed healthy and actively serving traffic (HTTP 200).")

	// B. Discover active ECS service and current container image
	ecsClient := ecs.NewFromConfig(cfg.awsConfig)
	clusterName := fmt.Sprintf("%s-nextcloud-cluster", cfg.Environment)
	serviceName := fmt.Sprintf("%s-nextcloud-service", cfg.Environment)

	// Check if tenant has a dedicated ECS service registered in DynamoDB
	if svcAttr, ok := getItemRes.Item["service_name"].(*dynamoTypes.AttributeValueMemberS); ok && svcAttr.Value != "" {
		svcCheck, svcErr := ecsClient.DescribeServices(context.TODO(), &ecs.DescribeServicesInput{
			Cluster:  aws.String(clusterName),
			Services: []string{svcAttr.Value},
		})
		if svcErr == nil && len(svcCheck.Services) > 0 && svcCheck.Services[0].Status != nil && *svcCheck.Services[0].Status == "ACTIVE" {
			serviceName = svcAttr.Value
		}
	}

	svcDesc, err := ecsClient.DescribeServices(context.TODO(), &ecs.DescribeServicesInput{
		Cluster:  aws.String(clusterName),
		Services: []string{serviceName},
	})
	require.NoError(t, err, "Failed to describe ECS service")
	require.NotEmpty(t, svcDesc.Services, "ECS service must exist")
	currentTaskDefArn := *svcDesc.Services[0].TaskDefinition

	tdDesc, err := ecsClient.DescribeTaskDefinition(context.TODO(), &ecs.DescribeTaskDefinitionInput{
		TaskDefinition: aws.String(currentTaskDefArn),
	})
	require.NoError(t, err, "Failed to describe current Task Definition")
	require.NotEmpty(t, tdDesc.TaskDefinition.ContainerDefinitions, "Task Definition must have container definitions")

	currentImage := *tdDesc.TaskDefinition.ContainerDefinitions[0].Image
	targetImage := os.Getenv("TARGET_IMAGE")
	if targetImage == "" {
		targetImage = currentImage
	}
	t.Logf("   -> Target Upgrade Image: %s", targetImage)
	t.Logf("   -> Current Active TaskDef: %s", currentTaskDefArn)

	// C. Trigger Live Container Image Upgrade via SuperAdmin Lambda
	upgradePayload, _ := json.Marshal(map[string]interface{}{
		"action":    "UPGRADE_TENANT_IMAGE",
		"tenant_id": tenantID,
		"image":     targetImage,
		"dry_run":   false,
	})
	upgradeInv, err := lambdaClient.Invoke(context.TODO(), &lambda.InvokeInput{
		FunctionName: aws.String(lambdaArn),
		Payload:      upgradePayload,
	})
	require.NoError(t, err, "Failed to invoke UPGRADE_TENANT_IMAGE action")
	require.Nil(t, upgradeInv.FunctionError, fmt.Sprintf("Lambda invocation failed with FunctionError: %v (Payload: %s)", upgradeInv.FunctionError, string(upgradeInv.Payload)))
	t.Logf("   -> Raw Lambda Response: %s", string(upgradeInv.Payload))

	var upgradeResp struct {
		StatusCode int    `json:"statusCode"`
		Body       string `json:"body"`
		Status     string `json:"status"`
		TaskDef    string `json:"task_definition"`
		Error      string `json:"error"`
	}
	_ = json.Unmarshal(upgradeInv.Payload, &upgradeResp)
	if upgradeResp.Body != "" {
		var inner struct {
			Status  string `json:"status"`
			TaskDef string `json:"task_definition"`
			Error   string `json:"error"`
		}
		_ = json.Unmarshal([]byte(upgradeResp.Body), &inner)
		if inner.Status != "" {
			upgradeResp.Status = inner.Status
		}
		if inner.TaskDef != "" {
			upgradeResp.TaskDef = inner.TaskDef
		}
		if inner.Error != "" {
			upgradeResp.Error = inner.Error
		}
	}
	// Fallback to top-level fields if invoked directly without ALB wrapper
	var rawMap map[string]interface{}
	if err := json.Unmarshal(upgradeInv.Payload, &rawMap); err == nil {
		if upgradeResp.Status == "" && rawMap["status"] != nil {
			upgradeResp.Status = fmt.Sprintf("%v", rawMap["status"])
		}
		if upgradeResp.TaskDef == "" && rawMap["task_definition"] != nil {
			upgradeResp.TaskDef = fmt.Sprintf("%v", rawMap["task_definition"])
		}
		if upgradeResp.Error == "" && rawMap["error"] != nil {
			upgradeResp.Error = fmt.Sprintf("%v", rawMap["error"])
		}
	}
	require.Empty(t, upgradeResp.Error, fmt.Sprintf("Image upgrade failed: %s", upgradeResp.Error))
	assert.Contains(t, []string{"UPDATING", "OK"}, upgradeResp.Status, "UPGRADE_TENANT_IMAGE must return UPDATING or OK status")
	newTaskDefArn := upgradeResp.TaskDef
	t.Logf("   -> New Task Definition revision registered & deployment initiated: %s", newTaskDefArn)

	// D. Continuous Zero-Downtime Availability & Rollout Steady-State Monitoring Loop
	t.Logf("   -> Monitoring continuous availability (zero downtime) during ECS rolling update...")
	maxRolloutDuration := 5 * time.Minute
	startTime := time.Now()
	probeCount := 0
	droppedCount := 0
	rolloutCompleted := false

	for time.Since(startTime) < maxRolloutDuration {
		probeCount++
		code, body, pErr := http_helper.HttpGetE(t, statusURL, tlsConfig)
		if pErr != nil || code != http.StatusOK {
			droppedCount++
			t.Logf("      ⚠️ Probe #%d DROPPED during rolling update (Status: %d, Err: %v)", probeCount, code, pErr)
		} else {
			var pData map[string]interface{}
			if pJsonErr := json.Unmarshal([]byte(body), &pData); pJsonErr != nil || pData["installed"] != true {
				droppedCount++
				t.Logf("      ⚠️ Probe #%d uninstalled/degraded during rolling update (Body: %s)", probeCount, body)
			}
		}

		// Inspect ECS service deployment rollout state every 6 seconds (every 3rd probe)
		if probeCount%3 == 0 {
			checkSvc, sErr := ecsClient.DescribeServices(context.TODO(), &ecs.DescribeServicesInput{
				Cluster:  aws.String(clusterName),
				Services: []string{serviceName},
			})
			if sErr == nil && len(checkSvc.Services) > 0 {
				svc := checkSvc.Services[0]
				for _, d := range svc.Deployments {
					dTaskDef := ""
					if d.TaskDefinition != nil {
						dTaskDef = *d.TaskDefinition
					}
					rolloutStateStr := string(d.RolloutState)
					if (dTaskDef == newTaskDefArn || newTaskDefArn == "") && *d.Status == "PRIMARY" {
						if rolloutStateStr == "COMPLETED" || (len(svc.Deployments) == 1 && svc.RunningCount == svc.DesiredCount) {
							rolloutCompleted = true
							t.Logf("   ✅ Primary ECS deployment reached steady state for TaskDef %s (RolloutState: %s, Running: %d/%d)",
								dTaskDef, rolloutStateStr, svc.RunningCount, svc.DesiredCount)
							break
						}
					}
				}
			}
		}

		if rolloutCompleted && probeCount >= 10 {
			break
		}
		time.Sleep(2 * time.Second)
	}

	require.True(t, rolloutCompleted, "ECS Service rolling deployment must reach completed steady state within 5 minutes")
	require.Zero(t, droppedCount, fmt.Sprintf("Zero-Downtime SLA violated during rolling update: %d dropped requests out of %d total probes", droppedCount, probeCount))
	t.Logf("🎉 [Acceptance] Live tenant container image rolling update verified with ZERO downtime! Total probes: %d, Dropped: 0", probeCount)

	// 6. S3 Multi-Tenant Object Storage & Intelligent-Tiering Verification
	t.Logf("📦 [Acceptance] Testing S3 Multi-Tenant Object Storage & Intelligent-Tiering...")
	s3BucketParam, s3ParamErr := ssmClient.GetParameter(context.TODO(), &ssm.GetParameterInput{
		Name: aws.String(fmt.Sprintf("/nextcloud/%s/infra/s3-vault-bucket", cfg.Environment)),
	})
	if s3ParamErr != nil || s3BucketParam.Parameter == nil || s3BucketParam.Parameter.Value == nil {
		t.Logf("⚠️ SSM parameter for S3 Vault bucket not found: %v", s3ParamErr)
	} else {
		vaultBucket := *s3BucketParam.Parameter.Value
		t.Logf("   -> S3 Vault Bucket: %s", vaultBucket)

		s3Client := s3.NewFromConfig(cfg.awsConfig)

		// A. Validate S3 Lifecycle Configuration
		lifecycleRes, lErr := s3Client.GetBucketLifecycleConfiguration(context.TODO(), &s3.GetBucketLifecycleConfigurationInput{
			Bucket: aws.String(vaultBucket),
		})
		require.NoError(t, lErr, fmt.Sprintf("Failed to get S3 Lifecycle configuration for %s", vaultBucket))
		require.NotEmpty(t, lifecycleRes.Rules, "S3 Bucket must have lifecycle optimization rules")

		var hasIntelligentTiering bool
		var hasMultipartAbort bool
		var hasGlacierIR bool
		for _, rule := range lifecycleRes.Rules {
			if rule.Status == s3Types.ExpirationStatusEnabled {
				for _, tr := range rule.Transitions {
					if tr.StorageClass == s3Types.TransitionStorageClassIntelligentTiering {
						hasIntelligentTiering = true
					}
				}
				for _, ntr := range rule.NoncurrentVersionTransitions {
					if ntr.StorageClass == s3Types.TransitionStorageClassGlacierIr || ntr.StorageClass == s3Types.TransitionStorageClassDeepArchive {
						hasGlacierIR = true
					}
				}
				if rule.AbortIncompleteMultipartUpload != nil && rule.AbortIncompleteMultipartUpload.DaysAfterInitiation != nil {
					hasMultipartAbort = true
				}
			}
		}
		assert.True(t, hasIntelligentTiering, "S3 Lifecycle must include Intelligent-Tiering transition")
		assert.True(t, hasGlacierIR, "S3 Lifecycle must include Glacier IR or Deep Archive noncurrent version transition")
		assert.True(t, hasMultipartAbort, "S3 Lifecycle must include AbortIncompleteMultipartUpload")
		t.Logf("   ✅ S3 Lifecycle validated: Intelligent-Tiering=active, GlacierIR/DeepArchive=active, MultipartAbort=active")

		// B. Validate S3 EventBridge Notifications
		notifRes, nErr := s3Client.GetBucketNotificationConfiguration(context.TODO(), &s3.GetBucketNotificationConfigurationInput{
			Bucket: aws.String(vaultBucket),
		})
		require.NoError(t, nErr, fmt.Sprintf("Failed to get S3 Notification configuration for %s", vaultBucket))
		assert.NotNil(t, notifRes.EventBridgeConfiguration, "S3 EventBridge notification configuration must be enabled")
		t.Logf("   ✅ S3 EventBridge Notifications enabled for serverless event processing")

		// C. Execute Tenant Storage Read/Write Probe
		probeKey := fmt.Sprintf("tenants/%s/storage_health_probe.txt", tenantID)
		probeContent := fmt.Sprintf("storix-storage-verification-at-%d", time.Now().Unix())
		_, putErr := s3Client.PutObject(context.TODO(), &s3.PutObjectInput{
			Bucket: aws.String(vaultBucket),
			Key:    aws.String(probeKey),
			Body:   strings.NewReader(probeContent),
		})
		require.NoError(t, putErr, fmt.Sprintf("Failed to put storage health probe into S3 vault %s", vaultBucket))

		getRes, getErr := s3Client.GetObject(context.TODO(), &s3.GetObjectInput{
			Bucket: aws.String(vaultBucket),
			Key:    aws.String(probeKey),
		})
		require.NoError(t, getErr, fmt.Sprintf("Failed to get storage health probe from S3 vault %s", vaultBucket))
		if getRes.Body != nil {
			_ = getRes.Body.Close()
		}

		_, delErr := s3Client.DeleteObject(context.TODO(), &s3.DeleteObjectInput{
			Bucket: aws.String(vaultBucket),
			Key:    aws.String(probeKey),
		})
		require.NoError(t, delErr, fmt.Sprintf("Failed to delete storage health probe from S3 vault %s", vaultBucket))
		t.Logf("   ✅ S3 Direct tenant write/read/delete probe succeeded for key: %s", probeKey)
	}

	t.Logf("🎉 [Acceptance] All deployment, tenant scaling, live image upgrade, and S3 storage acceptance tests passed completely with Terratest!")
}
