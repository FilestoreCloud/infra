package terratest

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/cloudformation"
	cfnTypes "github.com/aws/aws-sdk-go-v2/service/cloudformation/types"
	"github.com/stretchr/testify/require"
)

// GetDefaultRegion returns AWS_REGION from env or defaults to ap-southeast-1.
func GetDefaultRegion() string {
	region := os.Getenv("AWS_REGION")
	if region == "" {
		region = "ap-southeast-1"
	}
	return region
}

// GetAWSCfnClient creates an AWS CloudFormation client for the specified region.
func GetAWSCfnClient(t *testing.T, region string) *cloudformation.Client {
	cfg, err := config.LoadDefaultConfig(context.TODO(), config.WithRegion(region))
	require.NoError(t, err, "Failed to load AWS configuration")
	return cloudformation.NewFromConfig(cfg)
}

// ResolveTemplatePath returns the absolute path to a template relative to infra/ directory.
func ResolveTemplatePath(t *testing.T, relativePath string) string {
	// From infra/tests/terratest -> ../../
	baseDir, err := filepath.Abs("../../")
	require.NoError(t, err, "Failed to resolve repository infra base dir")
	fullPath := filepath.Join(baseDir, relativePath)
	_, err = os.Stat(fullPath)
	require.NoError(t, err, fmt.Sprintf("Template file does not exist at %s", fullPath))
	return fullPath
}

// DeployCloudFormationStack deploys a CloudFormation template and waits for CREATE_COMPLETE.
func DeployCloudFormationStack(
	t *testing.T,
	region string,
	stackName string,
	templatePath string,
	params map[string]string,
) {
	client := GetAWSCfnClient(t, region)

	templateBody, err := os.ReadFile(templatePath)
	require.NoError(t, err, fmt.Sprintf("Failed to read CloudFormation template at %s", templatePath))

	var cfnParams []cfnTypes.Parameter
	for k, v := range params {
		cfnParams = append(cfnParams, cfnTypes.Parameter{
			ParameterKey:   aws.String(k),
			ParameterValue: aws.String(v),
		})
	}

	t.Logf("🚀 [Terratest] Deploying CloudFormation Stack: %s (Region: %s)", stackName, region)
	bodyStr := string(templateBody)
	_, err = client.CreateStack(context.TODO(), &cloudformation.CreateStackInput{
		StackName:    aws.String(stackName),
		TemplateBody: aws.String(bodyStr),
		Parameters:   cfnParams,
		Capabilities: []cfnTypes.Capability{
			cfnTypes.CapabilityCapabilityIam,
			cfnTypes.CapabilityCapabilityNamedIam,
			cfnTypes.CapabilityCapabilityAutoExpand,
		},
	})
	require.NoError(t, err, fmt.Sprintf("CreateStack API call failed for %s", stackName))

	waiter := cloudformation.NewStackCreateCompleteWaiter(client)
	err = waiter.Wait(context.TODO(), &cloudformation.DescribeStacksInput{
		StackName: aws.String(stackName),
	}, 20*time.Minute)
	require.NoError(t, err, fmt.Sprintf("Stack %s failed to reach CREATE_COMPLETE", stackName))
	t.Logf("✅ [Terratest] Stack %s reached CREATE_COMPLETE", stackName)
}

// DestroyCloudFormationStack deletes a CloudFormation stack and waits for DELETE_COMPLETE.
func DestroyCloudFormationStack(t *testing.T, region string, stackName string) {
	client := GetAWSCfnClient(t, region)

	t.Logf("🧹 [Terratest] Tearing down CloudFormation Stack: %s", stackName)
	_, err := client.DeleteStack(context.TODO(), &cloudformation.DeleteStackInput{
		StackName: aws.String(stackName),
	})
	if err != nil {
		t.Logf("⚠️ Warning: DeleteStack failed or stack already deleted: %v", err)
		return
	}

	waiter := cloudformation.NewStackDeleteCompleteWaiter(client)
	_ = waiter.Wait(context.TODO(), &cloudformation.DescribeStacksInput{
		StackName: aws.String(stackName),
	}, 20*time.Minute)
	t.Logf("🗑️ [Terratest] Stack %s deleted cleanly", stackName)
}

// GetStackOutputs retrieves the output key-value map from a CloudFormation stack.
func GetStackOutputs(t *testing.T, region string, stackName string) map[string]string {
	client := GetAWSCfnClient(t, region)

	res, err := client.DescribeStacks(context.TODO(), &cloudformation.DescribeStacksInput{
		StackName: aws.String(stackName),
	})
	require.NoError(t, err, fmt.Sprintf("DescribeStacks failed for %s", stackName))
	require.NotEmpty(t, res.Stacks, fmt.Sprintf("No stack found with name %s", stackName))

	outputs := make(map[string]string)
	for _, out := range res.Stacks[0].Outputs {
		if out.OutputKey != nil && out.OutputValue != nil {
			outputs[*out.OutputKey] = *out.OutputValue
		}
	}
	return outputs
}
