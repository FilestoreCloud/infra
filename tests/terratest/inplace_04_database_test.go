package terratest

import (
	"context"
	"fmt"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestInPlaceDatabase verifies the live Module 04 RDS PostgreSQL Database & Secrets.
func TestInPlaceDatabase(t *testing.T) {
	cfg := LoadInPlaceConfig(t)
	stackName := cfg.GetStackName("04", "database")

	outputs, exists := cfg.GetStackOutputs(t, stackName)
	if !exists {
		t.Skipf("Stack %s is not deployed yet; skipping In-Place Database test.", stackName)
		return
	}

	dbEndpoint, hasEndpoint := outputs["DatabaseEndpoint"]
	require.True(t, hasEndpoint, "Output DatabaseEndpoint must exist")
	require.NotEmpty(t, dbEndpoint, "DatabaseEndpoint must not be empty")

	dbSecretArn, hasSecret := outputs["DBSecretArn"]
	require.True(t, hasSecret, "Output DBSecretArn must exist")
	require.NotEmpty(t, dbSecretArn, "DBSecretArn must not be empty")

	// 1. Assert Database Endpoint format
	t.Logf("🐘 [In-Place] Validating RDS PostgreSQL Endpoint: %s", dbEndpoint)
	assert.Contains(t, dbEndpoint, "rds.amazonaws.com", "DatabaseEndpoint must be an RDS private endpoint")

	// 2. Assert Secret existence & readiness in AWS Secrets Manager
	smClient := secretsmanager.NewFromConfig(cfg.awsConfig)
	secRes, err := smClient.DescribeSecret(context.TODO(), &secretsmanager.DescribeSecretInput{
		SecretId: aws.String(dbSecretArn),
	})
	require.NoError(t, err, fmt.Sprintf("Failed to describe DB secret at %s", dbSecretArn))
	require.NotNil(t, secRes.Name, "Secret name must not be nil")
	assert.Nil(t, secRes.DeletedDate, "Database secret must not be scheduled for deletion")

	t.Logf("✅ [In-Place] Module 04 Database validation passed for %s (Secret: %s)", stackName, *secRes.Name)
}
