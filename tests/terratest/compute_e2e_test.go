package terratest

import (
	"crypto/tls"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"

	http_helper "github.com/gruntwork-io/terratest/modules/http-helper"
	"github.com/stretchr/testify/require"
)

// TestComputeEndpointSmoke validates the live Application Load Balancer endpoint.
// It can test against an existing deployed environment (e.g. dev/staging)
// or an active CloudFormation Compute Stack.
func TestComputeEndpointSmoke(t *testing.T) {
	region := GetDefaultRegion()

	// Target ALB URL can be specified via env var or resolved from stack outputs
	targetURL := os.Getenv("NEXTCLOUD_ALB_URL")
	if targetURL == "" {
		stackName := os.Getenv("COMPUTE_STACK_NAME")
		if stackName == "" {
			stackName = "dev-nextcloud-05-compute"
		}
		t.Logf("ℹ️ Checking Stack: %s for LoadBalancerURL output...", stackName)
		outputs := GetStackOutputs(t, region, stackName)
		albURL, hasURL := outputs["LoadBalancerURL"]
		if !hasURL || albURL == "" {
			t.Skipf("No LoadBalancerURL found in stack %s and NEXTCLOUD_ALB_URL not set; skipping live endpoint test", stackName)
			return
		}
		targetURL = albURL
	}

	statusURL := fmt.Sprintf("%s/status.php", strings.TrimRight(targetURL, "/"))
	t.Logf("🌐 [Terratest] Probing Nextcloud health status endpoint: %s", statusURL)

	// TLS config ignoring self-signed certs in test environments
	tlsConfig := &tls.Config{
		InsecureSkipVerify: true,
	}

	// Validate endpoint responds with HTTP 200 and Nextcloud status JSON
	retries := 15
	sleepBetweenRetries := 5 * time.Second

	http_helper.HttpGetWithRetryWithCustomValidation(
		t,
		statusURL,
		tlsConfig,
		retries,
		sleepBetweenRetries,
		func(statusCode int, body string) bool {
			if statusCode != 200 {
				t.Logf("Pending readiness: HTTP %d (retrying...)", statusCode)
				return false
			}
			// Verify response body contains Nextcloud JSON payload
			return strings.Contains(body, "installed") || strings.Contains(body, "version")
		},
	)

	t.Logf("✅ [Terratest] Nextcloud ALB endpoint verified successfully at %s", statusURL)
	require.NotEmpty(t, statusURL)
}
