package terratest

import (
	"fmt"
	"strings"
	"testing"

	"github.com/gruntwork-io/terratest/modules/aws"
	"github.com/gruntwork-io/terratest/modules/random"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestNetworkingModule deploys and verifies Module 01 (Networking: VPC, Subnets, Routing).
func TestNetworkingModule(t *testing.T) {
	t.Parallel()

	region := GetDefaultRegion()
	uniqueID := strings.ToLower(random.UniqueId())
	stackName := fmt.Sprintf("test-storix-net-%s", uniqueID)
	templatePath := ResolveTemplatePath(t, "infra/modules/01-networking/template.yaml")

	params := map[string]string{
		"EnvironmentName": fmt.Sprintf("t%s", uniqueID[:6]),
		"VpcCidr":         "10.200.0.0/16",
	}

	// Clean up stack when the test completes
	defer DestroyCloudFormationStack(t, region, stackName)

	// 1. Deploy the CloudFormation Stack
	DeployCloudFormationStack(t, region, stackName, templatePath, params)

	// 2. Fetch Stack Outputs
	outputs := GetStackOutputs(t, region, stackName)
	vpcID, hasVpc := outputs["VpcId"]
	require.True(t, hasVpc, "Output VpcId must exist")
	require.NotEmpty(t, vpcID, "VpcId must not be empty")

	pubSubnet1, hasPub1 := outputs["PublicSubnet1Id"]
	require.True(t, hasPub1, "Output PublicSubnet1Id must exist")
	privSubnet1, hasPriv1 := outputs["PrivateSubnet1Id"]
	require.True(t, hasPriv1, "Output PrivateSubnet1Id must exist")

	// 3. Assert AWS Resource State via Terratest AWS Helpers
	t.Logf("🔍 [Terratest] Asserting VPC properties for: %s", vpcID)
	vpc := aws.GetVpcByID(t, vpcID, region)
	require.NotNil(t, vpc.CidrBlock, "VPC CidrBlock must not be nil")
	assert.Equal(t, "10.200.0.0/16", *vpc.CidrBlock, "VPC CIDR block should match requested value")

	// Verify Public subnet is truly public (has IGW route)
	isPublic := aws.IsPublicSubnet(t, pubSubnet1, region)
	assert.True(t, isPublic, fmt.Sprintf("Subnet %s must be recognized as a Public Subnet", pubSubnet1))

	// Verify Private subnet is not public
	isPrivatePublic := aws.IsPublicSubnet(t, privSubnet1, region)
	assert.False(t, isPrivatePublic, fmt.Sprintf("Subnet %s must be Private (no direct IGW route)", privSubnet1))
}
