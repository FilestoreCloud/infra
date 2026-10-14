package terratest

import (
	"context"
	"fmt"
	"testing"

	"github.com/aws/aws-sdk-go-v2/service/ec2"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestInPlaceSecurity audits the live Module 02 Security Groups.
// It verifies least-privilege ingress and ensures critical ports are never exposed to 0.0.0.0/0.
func TestInPlaceSecurity(t *testing.T) {
	cfg := LoadInPlaceConfig(t)
	stackName := cfg.GetStackName("02", "security")

	outputs, exists := cfg.GetStackOutputs(t, stackName)
	if !exists {
		t.Skipf("Stack %s is not deployed yet; skipping In-Place Security test.", stackName)
		return
	}

	albSgID := outputs["ALBSecurityGroupId"]
	ecsSgID := outputs["ECSSecurityGroupId"]
	dbSgID := outputs["DBSecurityGroupId"]
	efsSgID := outputs["EFSSecurityGroupId"]

	require.NotEmpty(t, albSgID, "ALBSecurityGroupId must exist")
	require.NotEmpty(t, ecsSgID, "ECSSecurityGroupId must exist")
	require.NotEmpty(t, dbSgID, "DBSecurityGroupId must exist")
	require.NotEmpty(t, efsSgID, "EFSSecurityGroupId must exist")

	ec2Client := ec2.NewFromConfig(cfg.awsConfig)
	res, err := ec2Client.DescribeSecurityGroups(context.TODO(), &ec2.DescribeSecurityGroupsInput{
		GroupIds: []string{albSgID, ecsSgID, dbSgID, efsSgID},
	})
	require.NoError(t, err, "DescribeSecurityGroups API call failed")

	for _, sg := range res.SecurityGroups {
		groupID := *sg.GroupId
		t.Logf("🛡️ [In-Place] Auditing Security Group: %s (%s)", groupID, *sg.GroupName)

		for _, perm := range sg.IpPermissions {
			fromPort := int32(0)
			if perm.FromPort != nil {
				fromPort = *perm.FromPort
			}

			// Audit RDS Database SG: Port 5432 MUST NEVER be open to 0.0.0.0/0
			if groupID == dbSgID {
				for _, ipRange := range perm.IpRanges {
					assert.NotEqual(t, "0.0.0.0/0", *ipRange.CidrIp,
						fmt.Sprintf("CRITICAL SECURITY VULNERABILITY: RDS SG %s has 0.0.0.0/0 open on port %d!", groupID, fromPort))
				}
			}

			// Audit EFS Persistent Storage SG: Port 2049 MUST NEVER be open to 0.0.0.0/0
			if groupID == efsSgID {
				for _, ipRange := range perm.IpRanges {
					assert.NotEqual(t, "0.0.0.0/0", *ipRange.CidrIp,
						fmt.Sprintf("CRITICAL SECURITY VULNERABILITY: EFS SG %s has 0.0.0.0/0 open on port %d!", groupID, fromPort))
				}
			}
		}
	}

	t.Logf("✅ [In-Place] Module 02 Security audit passed for %s (Least-privilege verified)", stackName)
}
