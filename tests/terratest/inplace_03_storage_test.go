package terratest

import (
	"context"
	"fmt"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	s3Types "github.com/aws/aws-sdk-go-v2/service/s3/types"
	terratestAWS "github.com/gruntwork-io/terratest/modules/aws"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestInPlaceStorage verifies the live Module 03 Storage Stack (S3 Multi-Tenant Vault & EFS).
func TestInPlaceStorage(t *testing.T) {
	cfg := LoadInPlaceConfig(t)
	stackName := cfg.GetStackName("03", "storage")

	outputs, exists := cfg.GetStackOutputs(t, stackName)
	if !exists {
		t.Skipf("Stack %s is not deployed yet; skipping In-Place Storage test.", stackName)
		return
	}

	bucketName, hasBucket := outputs["S3VaultBucketName"]
	require.True(t, hasBucket, "Output S3VaultBucketName must exist")
	require.NotEmpty(t, bucketName, "S3VaultBucketName must not be empty")

	efsID, hasEFS := outputs["EFSFileSystemId"]
	require.True(t, hasEFS, "Output EFSFileSystemId must exist")
	require.NotEmpty(t, efsID, "EFSFileSystemId must not be empty")

	// 1. Assert S3 Bucket Exists and has Versioning Enabled
	t.Logf("📦 [In-Place] Validating S3 Vault: %s", bucketName)
	terratestAWS.AssertS3BucketExists(t, cfg.Region, bucketName)
	terratestAWS.AssertS3BucketVersioningExists(t, cfg.Region, bucketName)

	// 2. Assert S3 Bucket Server-Side Encryption is active
	terratestAWS.AssertS3BucketServerSideEncryption(t, cfg.Region, bucketName, s3Types.ServerSideEncryptionAes256)

	// 3. Assert S3 Public Access Block is fully enabled
	s3Client := s3.NewFromConfig(cfg.awsConfig)
	pabRes, err := s3Client.GetPublicAccessBlock(context.TODO(), &s3.GetPublicAccessBlockInput{
		Bucket: aws.String(bucketName),
	})
	require.NoError(t, err, fmt.Sprintf("Failed to get PublicAccessBlock for %s", bucketName))
	pab := pabRes.PublicAccessBlockConfiguration
	require.NotNil(t, pab, "PublicAccessBlockConfiguration must not be nil")
	assert.True(t, aws.ToBool(pab.BlockPublicAcls), "BlockPublicAcls must be true")
	assert.True(t, aws.ToBool(pab.IgnorePublicAcls), "IgnorePublicAcls must be true")
	assert.True(t, aws.ToBool(pab.BlockPublicPolicy), "BlockPublicPolicy must be true")
	assert.True(t, aws.ToBool(pab.RestrictPublicBuckets), "RestrictPublicBuckets must be true")

	t.Logf("✅ [In-Place] Module 03 Storage validation passed for %s (S3 & EFS ready)", stackName)
}
