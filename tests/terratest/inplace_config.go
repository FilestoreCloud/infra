package terratest

import (
	"context"
	"fmt"
	"os"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/cloudformation"
	cfnTypes "github.com/aws/aws-sdk-go-v2/service/cloudformation/types"
	"github.com/stretchr/testify/require"
)

// InPlaceConfig holds configuration for evaluating live, deployed AWS stacks.
type InPlaceConfig struct {
	Environment string
	Region      string
	cfnClient   *cloudformation.Client
	awsConfig   aws.Config
}

// LoadInPlaceConfig loads configuration from environment variables.
func LoadInPlaceConfig(t *testing.T) *InPlaceConfig {
	env := os.Getenv("ENV")
	if env == "" {
		env = os.Getenv("ENVIRONMENT")
	}
	if env == "" {
		env = "dev"
	}

	region := os.Getenv("AWS_REGION")
	if region == "" {
		region = "ap-southeast-1"
	}

	cfg, err := config.LoadDefaultConfig(context.TODO(), config.WithRegion(region))
	require.NoError(t, err, "Failed to initialize AWS SDK config")

	return &InPlaceConfig{
		Environment: env,
		Region:      region,
		cfnClient:   cloudformation.NewFromConfig(cfg),
		awsConfig:   cfg,
	}
}

// GetStackName generates the standard CloudFormation stack name for a module.
// Example: dev-nextcloud-01-networking
func (c *InPlaceConfig) GetStackName(modulePrefix string, moduleName string) string {
	return fmt.Sprintf("%s-nextcloud-%s-%s", c.Environment, modulePrefix, moduleName)
}

// GetStackOutputs retrieves outputs of an existing stack without modifying or destroying it.
// Returns (outputs, true) if stack is ACTIVE/COMPLETE, or (nil, false) if not found.
func (c *InPlaceConfig) GetStackOutputs(t *testing.T, stackName string) (map[string]string, bool) {
	t.Logf("🔍 [In-Place Terratest] Inspecting live stack: %s (Region: %s)", stackName, c.Region)

	res, err := c.cfnClient.DescribeStacks(context.TODO(), &cloudformation.DescribeStacksInput{
		StackName: aws.String(stackName),
	})
	if err != nil {
		t.Logf("ℹ️ Stack %s does not exist or is not deployed yet: %v", stackName, err)
		return nil, false
	}

	if len(res.Stacks) == 0 {
		return nil, false
	}

	stack := res.Stacks[0]
	status := stack.StackStatus
	t.Logf("📊 Stack %s current status: %s", stackName, status)

	// Acceptable active statuses
	if status != cfnTypes.StackStatusCreateComplete &&
		status != cfnTypes.StackStatusUpdateComplete &&
		status != cfnTypes.StackStatusImportComplete {
		t.Logf("⚠️ Stack %s is not in a completed state (status: %s)", stackName, status)
		return nil, false
	}

	outputs := make(map[string]string)
	for _, out := range stack.Outputs {
		if out.OutputKey != nil && out.OutputValue != nil {
			outputs[*out.OutputKey] = *out.OutputValue
		}
	}
	return outputs, true
}
