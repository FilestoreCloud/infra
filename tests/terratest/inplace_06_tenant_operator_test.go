package terratest

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/lambda"
	"github.com/aws/aws-sdk-go-v2/service/ssm"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type OperatorAPIResponse struct {
	Status      string                   `json:"status"`
	Action      string                   `json:"action"`
	Message     string                   `json:"message"`
	Tenants     []map[string]interface{} `json:"tenants"`
	Tenant      map[string]interface{}   `json:"tenant"`
	Item        map[string]interface{}   `json:"item"`
	AWSTopology map[string]interface{}   `json:"aws_topology"`
	Metrics     map[string]interface{}   `json:"metrics"`
}

// invokeOperatorActionSafe invokes the Tenant Operator Lambda directly or over Function URL, returning errors without calling t.FailNow.
func invokeOperatorActionSafe(lambdaClient *lambda.Client, lambdaArn string, funcURL string, payload map[string]interface{}) (OperatorAPIResponse, error) {
	var resp OperatorAPIResponse
	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return resp, fmt.Errorf("failed to marshal payload: %w", err)
	}

	// If Function URL is available, invoke over HTTP POST
	if funcURL != "" {
		client := &http.Client{
			Timeout: 15 * time.Second,
			Transport: &http.Transport{
				TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
			},
		}
		req, err := http.NewRequestWithContext(context.TODO(), http.MethodPost, funcURL, strings.NewReader(string(payloadBytes)))
		if err == nil {
			req.Header.Set("Content-Type", "application/json")
			req.Header.Set("User-Agent", "Terratest-TenantOperator-Auditor")
			httpResp, err := client.Do(req)
			if err == nil {
				defer httpResp.Body.Close()
				if httpResp.StatusCode == http.StatusOK {
					bodyBytes, err := io.ReadAll(httpResp.Body)
					if err == nil {
						var parsedResp OperatorAPIResponse
						if err := json.Unmarshal(bodyBytes, &parsedResp); err == nil && parsedResp.Status != "" {
							return parsedResp, nil
						}
					}
				}
			}
		}
	}

	// Fallback to direct Lambda invocation via AWS SDK v2
	invRes, err := lambdaClient.Invoke(context.TODO(), &lambda.InvokeInput{
		FunctionName: aws.String(lambdaArn),
		Payload:      payloadBytes,
	})
	if err != nil {
		return resp, fmt.Errorf("lambda Invoke failed: %w", err)
	}
	if invRes.FunctionError != nil {
		return resp, fmt.Errorf("lambda returned unhandled function error: %s", *invRes.FunctionError)
	}

	// Lambda may return API Gateway style { statusCode, body } or direct JSON
	var lambdaWrapper struct {
		StatusCode int               `json:"statusCode"`
		Headers    map[string]string `json:"headers"`
		Body       string            `json:"body"`
	}
	if err := json.Unmarshal(invRes.Payload, &lambdaWrapper); err == nil && lambdaWrapper.Body != "" {
		if err := json.Unmarshal([]byte(lambdaWrapper.Body), &resp); err == nil && resp.Status != "" {
			return resp, nil
		}
	}

	if err := json.Unmarshal(invRes.Payload, &resp); err != nil {
		return resp, fmt.Errorf("failed to unmarshal Operator direct JSON payload: %w", err)
	}
	return resp, nil
}

// invokeOperatorAction invokes the Tenant Operator Lambda directly or over Function URL.
func invokeOperatorAction(t *testing.T, lambdaClient *lambda.Client, lambdaArn string, funcURL string, payload map[string]interface{}) OperatorAPIResponse {
	resp, err := invokeOperatorActionSafe(lambdaClient, lambdaArn, funcURL, payload)
	require.NoError(t, err, "Operator action failed")
	return resp
}

// probeTenantStatus probes the tenant's health endpoint (/status.php) on the ALB with the tenant Host header.
func probeTenantStatus(ctx context.Context, albBaseURL string, tenantHost string) (int, string, error) {
	baseURL := strings.TrimRight(albBaseURL, "/")
	if !strings.HasPrefix(baseURL, "http://") && !strings.HasPrefix(baseURL, "https://") {
		baseURL = "https://" + baseURL
	}
	statusURL := fmt.Sprintf("%s/status.php", baseURL)

	client := &http.Client{
		Timeout: 5 * time.Second,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		},
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, statusURL, nil)
	if err != nil {
		return 0, "", err
	}
	req.Host = tenantHost
	req.Header.Set("User-Agent", "Terratest-OperatorLifecycle-Probe")

	resp, err := client.Do(req)
	if err != nil {
		// If HTTPS failed and baseURL was auto-prefixed with https://, try http:// fallback
		if strings.HasPrefix(baseURL, "https://") && !strings.HasPrefix(albBaseURL, "https://") {
			statusURLHttp := fmt.Sprintf("http://%s/status.php", strings.TrimPrefix(baseURL, "https://"))
			reqHttp, errHttp := http.NewRequestWithContext(ctx, http.MethodGet, statusURLHttp, nil)
			if errHttp == nil {
				reqHttp.Host = tenantHost
				reqHttp.Header.Set("User-Agent", "Terratest-OperatorLifecycle-Probe")
				respHttp, errHttpDo := client.Do(reqHttp)
				if errHttpDo == nil {
					defer respHttp.Body.Close()
					bodyBytes, _ := io.ReadAll(respHttp.Body)
					return respHttp.StatusCode, string(bodyBytes), nil
				}
			}
		}
		return 0, "", err
	}
	defer resp.Body.Close()

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return resp.StatusCode, "", err
	}
	return resp.StatusCode, string(bodyBytes), nil
}

// TestInPlaceTenantOperatorAPI validates the complete Tenant Operator control plane:
// LIST, DESCRIBE, METRICS, SUSPEND and RESUME actions with real HTTP traffic verification
// and robust teardown guardrails.
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

	// Teardown Guardrail: guarantee that target tenant is restored to ACTIVE state on test completion or failure
	t.Cleanup(func() {
		t.Logf("🧹 [Teardown Guardrail] Ensuring tenant %s is restored to ACTIVE state...", targetTenant)
		cleanResp, cleanErr := invokeOperatorActionSafe(lambdaClient, lambdaArn, funcURL, map[string]interface{}{
			"action":    "RESUME",
			"tenant_id": targetTenant,
		})
		if cleanErr != nil {
			t.Logf("⚠️ [Teardown Guardrail] Warning: failed to resume tenant %s: %v", targetTenant, cleanErr)
		} else {
			t.Logf("✅ [Teardown Guardrail] Tenant %s restored: status=%s", targetTenant, cleanResp.Status)
		}
	})

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

	// Resolve ALB URL for real traffic verification
	albURL := os.Getenv("ALB_URL")
	if albURL == "" {
		albURL = os.Getenv("NEXTCLOUD_ALB_URL")
	}
	if albURL == "" {
		if u, ok := outputs["LoadBalancerURL"]; ok && u != "" {
			albURL = u
		}
	}
	if albURL == "" {
		computeStackName := cfg.GetStackName("05", "compute")
		if computeOutputs, hasCompute := cfg.GetStackOutputs(t, computeStackName); hasCompute {
			albURL = computeOutputs["LoadBalancerURL"]
			if albURL == "" {
				albURL = computeOutputs["LoadBalancerDNS"]
			}
			if albURL == "" {
				albURL = computeOutputs["LoadBalancerDNSName"]
			}
		}
	}
	if albURL == "" {
		ssmClient := ssm.NewFromConfig(cfg.awsConfig)
		for _, paramPath := range []string{
			fmt.Sprintf("/nextcloud/%s/infra/alb-dns", cfg.Environment),
			fmt.Sprintf("/nextcloud/%s/infra/alb-dns-name", cfg.Environment),
		} {
			paramRes, err := ssmClient.GetParameter(context.TODO(), &ssm.GetParameterInput{
				Name: aws.String(paramPath),
			})
			if err == nil && paramRes.Parameter != nil && paramRes.Parameter.Value != nil && *paramRes.Parameter.Value != "" {
				albURL = *paramRes.Parameter.Value
				break
			}
		}
	}

	rootDomain := os.Getenv("ROOT_DOMAIN")
	if rootDomain == "" {
		rootDomain = "png261.dev"
	}
	tenantDomain := fmt.Sprintf("%s.%s", targetTenant, rootDomain)
	if d, ok := tenantObj["domain"].(string); ok && d != "" {
		tenantDomain = d
	}

	if albURL == "" {
		albURL = fmt.Sprintf("https://%s", tenantDomain)
	}
	require.NotEmpty(t, albURL, "ALB endpoint must be resolved for real traffic verification")

	t.Logf("🌐 [Traffic Probe] Target ALB endpoint: %s (Host: %s)", albURL, tenantDomain)
	if tenantObj["status"] == "ACTIVE" {
		initCode, initBody, initErr := probeTenantStatus(context.TODO(), albURL, tenantDomain)
		t.Logf("🌐 Initial baseline probe: code=%d, err=%v, body=%s", initCode, initErr, initBody)
	}

	// 4. SUSPEND lifecycle toggle with Real Traffic verification
	t.Logf("⏸️ [Operator API] Testing SUSPEND action for %s...", targetTenant)
	suspendResp := invokeOperatorAction(t, lambdaClient, lambdaArn, funcURL, map[string]interface{}{
		"action":    "SUSPEND",
		"tenant_id": targetTenant,
	})
	assert.Contains(t, []string{"OK", "SUSPENDED", "SUSPENDING"}, suspendResp.Status)

	// Replace fragile sleep with proper polling loop for status == SUSPENDED
	t.Logf("⏳ Polling until tenant %s reaches SUSPENDED status...", targetTenant)
	require.Eventually(t, func() bool {
		descSuspended := invokeOperatorAction(t, lambdaClient, lambdaArn, funcURL, map[string]interface{}{
			"action":    "DESCRIBE",
			"tenant_id": targetTenant,
		})
		sTenant := descSuspended.Tenant
		if sTenant == nil {
			sTenant = descSuspended.Item
		}
		return sTenant != nil && sTenant["status"] == "SUSPENDED"
	}, 2*time.Minute, 2*time.Second, "Tenant failed to transition to SUSPENDED status within 2 minutes")

	// Real Traffic verification on SUSPEND: Assert HTTP 503 (or connection/maintenance response) indicating traffic is blocked
	t.Logf("🌐 [Traffic Probe] Verifying HTTP traffic is blocked after SUSPEND for %s (Host: %s)...", albURL, tenantDomain)
	require.Eventually(t, func() bool {
		code, body, err := probeTenantStatus(context.TODO(), albURL, tenantDomain)
		if err != nil {
			t.Logf("Probe error during SUSPEND (traffic blocked): %v", err)
			return true
		}
		t.Logf("Probe during SUSPEND: code=%d, body=%s", code, body)
		// Traffic is blocked if ALB returns HTTP 503 Service Unavailable, 502, 504, or maintenance mode
		if code == http.StatusServiceUnavailable || code == http.StatusBadGateway || code == http.StatusGatewayTimeout {
			return true
		}
		if strings.Contains(body, `"maintenance":true`) || strings.Contains(body, `"maintenance": true`) {
			return true
		}
		return code != http.StatusOK
	}, 2*time.Minute, 2*time.Second, "Traffic was not cut/blocked after SUSPEND action")

	// 5. RESUME lifecycle toggle with Real Traffic verification
	t.Logf("▶️ [Operator API] Testing RESUME action for %s...", targetTenant)
	resumeResp := invokeOperatorAction(t, lambdaClient, lambdaArn, funcURL, map[string]interface{}{
		"action":    "RESUME",
		"tenant_id": targetTenant,
	})
	assert.Contains(t, []string{"OK", "ACTIVE", "RESUMING"}, resumeResp.Status)

	// Replace fragile sleep with proper polling loop for status == ACTIVE
	t.Logf("⏳ Polling until tenant %s reaches ACTIVE status...", targetTenant)
	require.Eventually(t, func() bool {
		descResumed := invokeOperatorAction(t, lambdaClient, lambdaArn, funcURL, map[string]interface{}{
			"action":    "DESCRIBE",
			"tenant_id": targetTenant,
		})
		rTenant := descResumed.Tenant
		if rTenant == nil {
			rTenant = descResumed.Item
		}
		return rTenant != nil && rTenant["status"] == "ACTIVE"
	}, 3*time.Minute, 3*time.Second, "Tenant failed to transition to ACTIVE status within 3 minutes")

	// Real Traffic verification on RESUME: Assert HTTP 200 OK with installed: true, maintenance: false indicating traffic is restored
	t.Logf("🌐 [Traffic Probe] Verifying HTTP traffic is restored after RESUME for %s (Host: %s)...", albURL, tenantDomain)
	require.Eventually(t, func() bool {
		code, body, err := probeTenantStatus(context.TODO(), albURL, tenantDomain)
		if err != nil {
			t.Logf("Probe error during RESUME (retrying): %v", err)
			return false
		}
		t.Logf("Probe during RESUME: code=%d, body=%s", code, body)
		if code == http.StatusOK {
			var statusData map[string]interface{}
			if err := json.Unmarshal([]byte(body), &statusData); err == nil {
				installed, _ := statusData["installed"].(bool)
				maintenance, _ := statusData["maintenance"].(bool)
				return installed && !maintenance
			}
			hasInstalled := strings.Contains(body, `"installed":true`) || strings.Contains(body, `"installed": true`)
			hasNoMaint := !strings.Contains(body, `"maintenance":true`) && !strings.Contains(body, `"maintenance": true`)
			return hasInstalled && hasNoMaint
		}
		return false
	}, 3*time.Minute, 3*time.Second, "Traffic was not restored to HTTP 200 OK (installed: true, maintenance: false) after RESUME action")

	t.Logf("✅ [Terratest] Tenant Operator API passed all lifecycle, real traffic, and inspection actions.")
}
