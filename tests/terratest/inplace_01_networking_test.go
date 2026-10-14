package terratest

import (
	"context"
	"fmt"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/ssm"
	terratestAWS "github.com/gruntwork-io/terratest/modules/aws"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestInPlaceNetworking verifies the live, deployed Module 01 (Networking Stack).
// It performs purely read-only assertions and NEVER destroys any resource.
func TestInPlaceNetworking(t *testing.T) {
	cfg := LoadInPlaceConfig(t)
	stackName := cfg.GetStackName("01", "networking")

	outputs, exists := cfg.GetStackOutputs(t, stackName)
	if !exists {
		t.Skipf("Stack %s is not deployed yet; skipping In-Place Networking test.", stackName)
		return
	}

	vpcID, hasVpc := outputs["VpcId"]
	require.True(t, hasVpc, "Output VpcId must exist in stack outputs")
	require.NotEmpty(t, vpcID, "VpcId must not be empty")

	pubSubnet1, hasPub1 := outputs["PublicSubnet1Id"]
	require.True(t, hasPub1, "Output PublicSubnet1Id must exist")
	pubSubnet2, hasPub2 := outputs["PublicSubnet2Id"]
	require.True(t, hasPub2, "Output PublicSubnet2Id must exist")

	privSubnet1, hasPriv1 := outputs["PrivateSubnet1Id"]
	require.True(t, hasPriv1, "Output PrivateSubnet1Id must exist")
	privSubnet2, hasPriv2 := outputs["PrivateSubnet2Id"]
	require.True(t, hasPriv2, "Output PrivateSubnet2Id must exist")

	// 1. Assert VPC State & Multi-AZ Distribution
	t.Logf("🌐 [In-Place] Validating VPC topology for %s (%s)", vpcID, stackName)
	vpc := terratestAWS.GetVpcByID(t, vpcID, cfg.Region)
	require.NotNil(t, vpc, "VPC object must be retrievable from AWS")
	require.NotNil(t, vpc.CidrBlock, "VPC CidrBlock must not be nil")
	assert.NotEmpty(t, *vpc.CidrBlock, "VPC CidrBlock must be non-empty")

	// 2. Assert Public Subnets have route to IGW
	t.Logf("🌐 [In-Place] Validating Public Subnet routing")
	assert.True(t, terratestAWS.IsPublicSubnet(t, pubSubnet1, cfg.Region), fmt.Sprintf("Subnet %s must be Public", pubSubnet1))
	assert.True(t, terratestAWS.IsPublicSubnet(t, pubSubnet2, cfg.Region), fmt.Sprintf("Subnet %s must be Public", pubSubnet2))

	// 3. Assert Private Subnets are isolated
	t.Logf("🔒 [In-Place] Validating Private Subnet isolation")
	assert.False(t, terratestAWS.IsPublicSubnet(t, privSubnet1, cfg.Region), fmt.Sprintf("Subnet %s must be Private", privSubnet1))
	assert.False(t, terratestAWS.IsPublicSubnet(t, privSubnet2, cfg.Region), fmt.Sprintf("Subnet %s must be Private", privSubnet2))

	// 4. Assert SSM Parameter registration for downstream stacks
	ssmClient := ssm.NewFromConfig(cfg.awsConfig)
	pubParamName := fmt.Sprintf("/nextcloud/%s/infra/public-subnets", cfg.Environment)
	paramRes, err := ssmClient.GetParameter(context.TODO(), &ssm.GetParameterInput{
		Name: aws.String(pubParamName),
	})
	require.NoError(t, err, fmt.Sprintf("SSM Parameter %s must exist", pubParamName))
	require.NotNil(t, paramRes.Parameter.Value, "SSM Parameter value must not be nil")
	assert.Contains(t, *paramRes.Parameter.Value, pubSubnet1, "SSM Parameter must contain PublicSubnet1Id")

	t.Logf("✅ [In-Place] Module 01 Networking verification passed for %s", stackName)
}
