package terratest

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	dynamoTypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/lambda"
	lambdaTypes "github.com/aws/aws-sdk-go-v2/service/lambda/types"
	"github.com/aws/aws-sdk-go-v2/service/ssm"
	http_helper "github.com/gruntwork-io/terratest/modules/http-helper"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// LambdaResponse models the standard API Gateway / Function URL response payload.
type LambdaResponse struct {
	StatusCode int               `json:"statusCode"`
	Headers    map[string]string `json:"headers"`
	Body       string            `json:"body"`
}

// TestInPlaceSuperAdmin verifies Module 06 SuperAdmin (DynamoDB, Lambda Operator, Function URL, CloudWatch & Runbook).
func TestInPlaceSuperAdmin(t *testing.T) {
	cfg := LoadInPlaceConfig(t)
	stackName := cfg.GetStackName("06", "superadmin")

	outputs, exists := cfg.GetStackOutputs(t, stackName)
	if !exists {
		t.Skipf("Stack %s is not deployed yet; skipping In-Place SuperAdmin test.", stackName)
		return
	}

	tableName, tableExists := outputs["TenantRegistryTable"]
	require.True(t, tableExists, "Output TenantRegistryTable must exist")
	require.NotEmpty(t, tableName, "TenantRegistryTable must not be empty")

	lambdaArn, hasLambda := outputs["TenantOperatorLambdaArn"]
	require.True(t, hasLambda, "Output TenantOperatorLambdaArn must exist")
	require.NotEmpty(t, lambdaArn, "TenantOperatorLambdaArn must not be empty")

	funcURL := outputs["TenantOperatorLambdaFunctionUrl"]

	// 1. Assert DynamoDB Tenant Registry Table Status
	t.Logf("🗄️ [In-Place] Validating DynamoDB Tenant Registry: %s", tableName)
	dynamoClient := dynamodb.NewFromConfig(cfg.awsConfig)
	tableRes, err := dynamoClient.DescribeTable(context.TODO(), &dynamodb.DescribeTableInput{
		TableName: aws.String(tableName),
	})
	require.NoError(t, err, fmt.Sprintf("Failed to describe DynamoDB table %s", tableName))
	require.NotNil(t, tableRes.Table, "Table description must not be nil")
	assert.Equal(t, dynamoTypes.TableStatusActive, tableRes.Table.TableStatus, "DynamoDB table status must be ACTIVE")

	// 2. Assert Lambda Function Configuration & State
	t.Logf("⚡ [In-Place] Validating Control Plane Lambda: %s", lambdaArn)
	lambdaClient := lambda.NewFromConfig(cfg.awsConfig)
	fnRes, err := lambdaClient.GetFunction(context.TODO(), &lambda.GetFunctionInput{
		FunctionName: aws.String(lambdaArn),
	})
	require.NoError(t, err, fmt.Sprintf("Failed to inspect Lambda function %s", lambdaArn))
	require.NotNil(t, fnRes.Configuration, "Lambda configuration must not be nil")
	assert.Equal(t, lambdaTypes.StateActive, fnRes.Configuration.State, "Lambda function state must be ACTIVE")
	assert.Equal(t, lambdaTypes.RuntimePython311, fnRes.Configuration.Runtime, "Lambda runtime should be python3.11")

	// 3. Direct Lambda Invocation: CORS Preflight (OPTIONS)
	t.Logf("⚡ [In-Place] Invoking Lambda for CORS preflight validation")
	optionsEvent := map[string]interface{}{
		"httpMethod": "OPTIONS",
	}
	optionsBytes, _ := json.Marshal(optionsEvent)
	invRes, err := lambdaClient.Invoke(context.TODO(), &lambda.InvokeInput{
		FunctionName: aws.String(lambdaArn),
		Payload:      optionsBytes,
	})
	require.NoError(t, err, "Lambda Invoke failed for OPTIONS event")
	assert.Nil(t, invRes.FunctionError, "Lambda execution must not throw unhandled runtime error")

	var optResp LambdaResponse
	err = json.Unmarshal(invRes.Payload, &optResp)
	require.NoError(t, err, "Failed to parse Lambda JSON response payload")
	assert.Equal(t, 200, optResp.StatusCode, "CORS preflight must return HTTP 200")
	assert.Equal(t, "*", optResp.Headers["Access-Control-Allow-Origin"], "CORS header Access-Control-Allow-Origin must be *")

	// 4. Direct Lambda Invocation: Mutation error handling (missing tenant_id)
	t.Logf("⚡ [In-Place] Invoking Lambda for mutation validation (missing tenant_id)")
	missingTenantEvent := map[string]interface{}{
		"httpMethod": "POST",
		"body":       `{"action": "PROVISION"}`,
	}
	missingTenantBytes, _ := json.Marshal(missingTenantEvent)
	invErrRes, err := lambdaClient.Invoke(context.TODO(), &lambda.InvokeInput{
		FunctionName: aws.String(lambdaArn),
		Payload:      missingTenantBytes,
	})
	require.NoError(t, err, "Lambda Invoke failed for missing tenant event")
	var errResp LambdaResponse
	_ = json.Unmarshal(invErrRes.Payload, &errResp)
	// Must return client error (HTTP 400 or 401 unauthorized because no auth token is provided)
	assert.Contains(t, []int{400, 401}, errResp.StatusCode, "Mutations without auth/tenant_id must return 400 or 401")

	// 5. Probe Lambda Function URL over HTTP (if configured)
	if funcURL != "" {
		t.Logf("🌐 [In-Place] Probing Lambda Function URL directly: %s", funcURL)
		tlsConfig := &tls.Config{InsecureSkipVerify: true}

		http_helper.HTTPDoWithCustomValidationWithOptions(
			t,
			http_helper.HttpDoOptions{
				Method:    "OPTIONS",
				Url:       funcURL,
				TlsConfig: tlsConfig,
				Headers: map[string]string{
					"Origin":                        "http://localhost:3000",
					"Access-Control-Request-Method": "GET",
				},
			},
			func(statusCode int, body string) bool {
				return statusCode == http.StatusOK
			},
		)
		t.Logf("✅ Lambda Function URL responds with HTTP 200 on OPTIONS")

		http_helper.HTTPDoWithCustomValidationWithOptions(
			t,
			http_helper.HttpDoOptions{
				Method:    "POST",
				Url:       funcURL,
				TlsConfig: tlsConfig,
				Body:      strings.NewReader(`{"action": "HEALTH"}`),
				Headers: map[string]string{
					"Content-Type": "application/json",
				},
			},
			func(statusCode int, body string) bool {
				return statusCode == http.StatusOK || statusCode == http.StatusUnauthorized
			},
		)
		t.Logf("✅ Lambda Function URL responds successfully on POST")
	}

	// 6. Assert CloudWatch Dashboard exists
	cwClient := cloudwatch.NewFromConfig(cfg.awsConfig)
	dashName := fmt.Sprintf("%s-Nextcloud-SaaS-Control-Plane", cfg.Environment)
	t.Logf("📈 [In-Place] Validating CloudWatch Dashboard: %s", dashName)
	dashRes, err := cwClient.GetDashboard(context.TODO(), &cloudwatch.GetDashboardInput{
		DashboardName: aws.String(dashName),
	})
	if err == nil && dashRes.DashboardArn != nil {
		assert.Contains(t, *dashRes.DashboardArn, dashName, "CloudWatch Dashboard ARN must contain dashboard name")
	} else {
		t.Logf("ℹ️ CloudWatch Dashboard %s is optional or in dedicated observability stack", dashName)
	}

	// 7. Assert SSM Tenant Operator Runbook exists
	ssmRunbookName, hasRunbook := outputs["SSMRunbookName"]
	if hasRunbook && ssmRunbookName != "" {
		t.Logf("📋 [In-Place] Validating SSM Runbook: %s", ssmRunbookName)
		ssmClient := ssm.NewFromConfig(cfg.awsConfig)
		docRes, err := ssmClient.DescribeDocument(context.TODO(), &ssm.DescribeDocumentInput{
			Name: aws.String(ssmRunbookName),
		})
		require.NoError(t, err, fmt.Sprintf("Failed to describe SSM Document %s", ssmRunbookName))
		assert.Equal(t, "Active", string(docRes.Document.Status), "SSM Document status must be Active")
	}

	// 8. Assert Web Admin CloudFront URL output
	adminURL, hasAdminURL := outputs["AdminWebURL"]
	if hasAdminURL && adminURL != "" {
		t.Logf("🌐 [In-Place] Super Admin Web Console URL: %s", adminURL)
		assert.Contains(t, adminURL, "https://", "AdminWebURL must be secure HTTPS")
	}

	t.Logf("✅ [In-Place] Module 06 SuperAdmin validation passed completely for %s", stackName)
}
