package terratest

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"net/http"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/lambda"
	http_helper "github.com/gruntwork-io/terratest/modules/http-helper"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type OperatorAPIResponse struct {
	Status      string                 `json:"status"`
	Action      string                 `json:"action"`
	Message     string                 `json:"message"`
	Tenants     []map[string]interface{} `json:"tenants"`
	Tenant      map[string]interface{} `json:"tenant"`
	Item        map[string]interface{} `json:"item"`
	AWSTopology map[string]interface{} `json:"aws_topology"`
	Metrics     map[string]interface{} `json:"metrics"`
}

// invokeOperatorAction invokes the Tenant Operator Lambda directly or over Function URL.
func invokeOperatorAction(t *testing.T, lambdaClient *lambda.Client, lambdaArn string, funcURL string, payload map[string]interface{}) OperatorAPIResponse {
	payloadBytes, err := json.Marshal(payload)
	require.NoError(t, err, "Failed to marshal payload")

	// If Function URL is available, use Terratest http_helper
	if funcURL != "" {
		tlsConfig := &tls.Config{InsecureSkipVerify: true}
		var parsedResp OperatorAPIResponse
		http_helper.HTTPDoWithCustomValidationWithOptions(
			t,
			http_helper.HttpDoOptions{
				Method:    "POST",
				Url:       funcURL,
				TlsConfig: tlsConfig,
				Body:      strings.NewReader(string(payloadBytes)),
				Headers: map[string]string{
					"Content-Type": "application/json",
					"User-Agent":   "Terratest-TenantOperator-Auditor",
				},
			},
			func(statusCode int, body string) bool {
				if statusCode == http.StatusOK {
					_ = json.Unmarshal([]byte(body), &parsedResp)
					return true
				}
				return false
			},
		)
		if parsedResp.Status != "" {
			return parsedResp
		}
	}

	// Fallback to direct Lambda invocation via AWS SDK v2
	invRes, err := lambdaClient.Invoke(context.TODO(), &lambda.InvokeInput{
		FunctionName: aws.String(lambdaArn),
		Payload:      payloadBytes,
	})
	require.NoError(t, err, "Lambda Invoke failed for operator action")
	require.Nil(t, invRes.FunctionError, "Lambda returned unhandled function error")

	// Lambda may return API Gateway style { statusCode, body } or direct JSON
	var lambdaWrapper LambdaResponse
	if err := json.Unmarshal(invRes.Payload, &lambdaWrapper); err == nil && lambdaWrapper.Body != "" {
		var resp OperatorAPIResponse
		_ = json.Unmarshal([]byte(lambdaWrapper.Body), &resp)
		return resp
	}

	var resp OperatorAPIResponse
	err = json.Unmarshal(invRes.Payload, &resp)
	require.NoError(t, err, "Failed to unmarshal Operator direct JSON payload")
	return resp
}

// TestInPlaceTenantOperatorAPI validates the complete Tenant Operator control plane:
// LIST, DESCRIBE, METRICS, SUSPEND and RESUME actions.
func TestInPlaceTenantOperatorAPI(t *testing.T) {
	cfg := LoadInPlaceConfig(t)
	stackName := cfg.GetStackName("06", "superadmin")

	outputs, exists := cfg.GetStackOutputs(t, stackName)
	if !exists {
		t.Skipf("Stack %s is not deployed yet; skipping Tenant Operator API test.", stackName)
		return
	}

	lambdaArn, hasLambda := outputs["TenantOperatorLambdaArn"]
	require.True(t, hasLambda, "TenantOperatorLambdaArn output must exist")
	require.NotEmpty(t, lambdaArn, "TenantOperatorLambdaArn must not be empty")

	funcURL := outputs["TenantOperatorLambdaFunctionUrl"]
	lambdaClient := lambda.NewFromConfig(cfg.awsConfig)

	// 1. LIST action
	t.Logf("📋 [Operator API] Invoking LIST tenants...")
	listResp := invokeOperatorAction(t, lambdaClient, lambdaArn, funcURL, map[string]interface{}{
		"action": "LIST",
	})
	assert.Equal(t, "OK", listResp.Status, "LIST action must return status OK")

	tenants := listResp.Tenants
	require.NotEmpty(t, tenants, "Active fleet must contain at least one tenant")

	// Resolve target tenant dynamically (zero hardcoding)
	targetTenant := os.Getenv("TENANT_ID")
	if targetTenant == "" {
		if firstTenant, ok := tenants[0]["tenant_id"].(string); ok {
			targetTenant = firstTenant
		}
	}
	require.NotEmpty(t, targetTenant, "Target tenant ID could not be resolved from environment or fleet")
	t.Logf("🎯 Testing operations against active tenant: %s", targetTenant)

	// 2. DESCRIBE action
	t.Logf("🔍 [Operator API] Invoking DESCRIBE tenant for %s...", targetTenant)
	descResp := invokeOperatorAction(t, lambdaClient, lambdaArn, funcURL, map[string]interface{}{
		"action":    "DESCRIBE",
		"tenant_id": targetTenant,
	})
	assert.Equal(t, "OK", descResp.Status, "DESCRIBE action must return status OK")

	tenantObj := descResp.Tenant
	if tenantObj == nil {
		tenantObj = descResp.Item
	}
	require.NotNil(t, tenantObj, "Tenant details must be present")
	assert.Equal(t, targetTenant, tenantObj["tenant_id"])
	assert.Contains(t, []string{"ACTIVE", "SUSPENDED"}, tenantObj["status"])

	// Assert topology & metrics structures
	assert.NotNil(t, descResp.AWSTopology, "aws_topology must be present in DESCRIBE response")

	// 3. METRICS action
	t.Logf("📈 [Operator API] Invoking METRICS action for %s...", targetTenant)
	metricsResp := invokeOperatorAction(t, lambdaClient, lambdaArn, funcURL, map[string]interface{}{
		"action":    "METRICS",
		"tenant_id": targetTenant,
	})
	assert.Equal(t, "OK", metricsResp.Status, "METRICS action must return status OK")

	// 4. SUSPEND and RESUME lifecycle toggle
	t.Logf("⏸️ [Operator API] Testing SUSPEND action for %s...", targetTenant)
	suspendResp := invokeOperatorAction(t, lambdaClient, lambdaArn, funcURL, map[string]interface{}{
		"action":    "SUSPEND",
		"tenant_id": targetTenant,
	})
	assert.Contains(t, []string{"OK", "SUSPENDED"}, suspendResp.Status)

	time.Sleep(1 * time.Second)

	// Verify state is suspended
	descSuspended := invokeOperatorAction(t, lambdaClient, lambdaArn, funcURL, map[string]interface{}{
		"action":    "DESCRIBE",
		"tenant_id": targetTenant,
	})
	sTenant := descSuspended.Tenant
	if sTenant == nil {
		sTenant = descSuspended.Item
	}
	assert.Equal(t, "SUSPENDED", sTenant["status"])

	// Resume back
	t.Logf("▶️ [Operator API] Testing RESUME action for %s...", targetTenant)
	resumeResp := invokeOperatorAction(t, lambdaClient, lambdaArn, funcURL, map[string]interface{}{
		"action":    "RESUME",
		"tenant_id": targetTenant,
	})
	assert.Contains(t, []string{"OK", "ACTIVE"}, resumeResp.Status)

	time.Sleep(1 * time.Second)

	// Verify state is restored to active
	descResumed := invokeOperatorAction(t, lambdaClient, lambdaArn, funcURL, map[string]interface{}{
		"action":    "DESCRIBE",
		"tenant_id": targetTenant,
	})
	rTenant := descResumed.Tenant
	if rTenant == nil {
		rTenant = descResumed.Item
	}
	assert.Equal(t, "ACTIVE", rTenant["status"])

	t.Logf("✅ [Terratest] Tenant Operator API passed all lifecycle and inspection actions.")
}
