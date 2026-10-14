package terratest

import (
	"fmt"
	"strings"
	"testing"

	"github.com/aws/aws-sdk-go-v2/service/s3/types"
	"github.com/gruntwork-io/terratest/modules/aws"
	"github.com/gruntwork-io/terratest/modules/random"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestStorageModule verifies Module 03 Storage (S3 Multi-Tenant Vault & EFS).
func TestStorageModule(t *testing.T) {
	t.Parallel()

	region := GetDefaultRegion()
	uniqueID := strings.ToLower(random.UniqueId())
	envName := fmt.Sprintf("t%s", uniqueID[:6])

	// 1. Setup prerequisite networking & security
	netStackName := fmt.Sprintf("test-storix-net-%s", uniqueID)
	netTemplate := ResolveTemplatePath(t, "infra/modules/01-networking/template.yaml")
	defer DestroyCloudFormationStack(t, region, netStackName)
	DeployCloudFormationStack(t, region, netStackName, netTemplate, map[string]string{
		"EnvironmentName": envName,
	})
	netOutputs := GetStackOutputs(t, region, netStackName)

	secStackName := fmt.Sprintf("test-storix-sec-%s", uniqueID)
	secTemplate := ResolveTemplatePath(t, "infra/modules/02-security/template.yaml")
	defer DestroyCloudFormationStack(t, region, secStackName)
	DeployCloudFormationStack(t, region, secStackName, secTemplate, map[string]string{
		"EnvironmentName": envName,
		"VpcId":           netOutputs["VpcId"],
	})
	secOutputs := GetStackOutputs(t, region, secStackName)

	// 2. Deploy Module 03 (Storage)
	storageStackName := fmt.Sprintf("test-storix-store-%s", uniqueID)
	storageTemplate := ResolveTemplatePath(t, "infra/modules/03-storage/template.yaml")
	defer DestroyCloudFormationStack(t, region, storageStackName)

	DeployCloudFormationStack(t, region, storageStackName, storageTemplate, map[string]string{
		"EnvironmentName":    envName,
		"PublicSubnet1Id":    netOutputs["PublicSubnet1Id"],
		"PublicSubnet2Id":    netOutputs["PublicSubnet2Id"],
		"EFSSecurityGroupId": secOutputs["EFSSecurityGroupId"],
	})

	// 3. Assert Outputs & S3 Vault Capabilities
	storageOutputs := GetStackOutputs(t, region, storageStackName)
	bucketName, hasBucket := storageOutputs["S3VaultBucketName"]
	require.True(t, hasBucket, "Output S3VaultBucketName must exist")
	require.NotEmpty(t, bucketName, "Bucket name must not be empty")

	t.Logf("🔍 [Terratest] Asserting S3 bucket security for: %s", bucketName)
	aws.AssertS3BucketExists(t, region, bucketName)
	aws.AssertS3BucketVersioningExists(t, region, bucketName)
	aws.AssertS3BucketServerSideEncryption(t, region, bucketName, types.ServerSideEncryptionAes256)

	// 4. Test S3 Read/Write Data Canary
	testKey := fmt.Sprintf("canary/%s.txt", uniqueID)
	testContent := "Terratest storage verification payload"
	t.Logf("📝 [Terratest] Testing I/O to S3 Vault: %s", testKey)
	aws.PutS3ObjectContents(t, region, bucketName, testKey, strings.NewReader(testContent))

	readContent := aws.GetS3ObjectContents(t, region, bucketName, testKey)
	assert.Equal(t, testContent, readContent, "S3 read content must match written payload")
}
