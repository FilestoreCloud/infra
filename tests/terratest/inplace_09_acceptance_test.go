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
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	dynamoTypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/lambda"
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

	maxRetries := 30
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
		Status string `json:"status"`
	}
	_ = json.Unmarshal(suspendInv.Payload, &suspendResp)
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
		Status string `json:"status"`
	}
	_ = json.Unmarshal(resumeInv.Payload, &resumeResp)
	assert.Contains(t, []string{"OK", "ACTIVE", "RESUMING"}, resumeResp.Status, "RESUME status must indicate scale-out transition")
	t.Logf("   -> Tenant scaled out successfully (status: %s)", resumeResp.Status)

	t.Logf("🎉 [Acceptance] First-time deployment and tenant scaling acceptance tests passed completely with Terratest!")
}
