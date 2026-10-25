package terratest

import (
	"context"
	"encoding/json"
	"fmt"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	ddbTypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/sfn"
	sfnTypes "github.com/aws/aws-sdk-go-v2/service/sfn/types"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// ASLDefinition represents a minimal Amazon States Language state machine structure.
type ASLDefinition struct {
	Comment string              `json:"Comment"`
	StartAt string              `json:"StartAt"`
	States  map[string]ASLState `json:"States"`
}

type ASLState struct {
	Type     string     `json:"Type"`
	Next     string     `json:"Next"`
	End      bool       `json:"End"`
	Default  string     `json:"Default"`
	Branches []struct{} `json:"Branches"`
	Catch    []ASLCatch `json:"Catch"`
}

type ASLCatch struct {
	ErrorEquals []string `json:"ErrorEquals"`
	Next        string   `json:"Next"`
}

// TestInPlaceStepFunctions verifies the 4 dedicated Step Functions state machines:
// Provisioning, Suspension, Resumption, and Deprovisioning.
func TestInPlaceStepFunctions(t *testing.T) {
	cfg := LoadInPlaceConfig(t)
	stackName := cfg.GetStackName("06", "superadmin")

	outputs, exists := cfg.GetStackOutputs(t, stackName)
	if !exists {
		t.Skipf("Stack %s is not deployed yet; skipping In-Place Step Functions test.", stackName)
		return
	}

	stateMachineKeys := []struct {
		OutputKey string
		Name      string
	}{
		{OutputKey: "TenantProvisioningStateMachineArn", Name: "TenantProvisioningStateMachine"},
		{OutputKey: "TenantSuspensionStateMachineArn", Name: "TenantSuspensionStateMachine"},
		{OutputKey: "TenantResumptionStateMachineArn", Name: "TenantResumptionStateMachine"},
		{OutputKey: "TenantDeprovisioningStateMachineArn", Name: "TenantDeprovisioningStateMachine"},
		{OutputKey: "TenantSeedingStateMachineArn", Name: "TenantSeedingStateMachine"},
		{OutputKey: "TenantDemoProvisioningStateMachineArn", Name: "TenantDemoProvisioningStateMachine"},
		{OutputKey: "TenantFleetUpgradeStateMachineArn", Name: "TenantFleetUpgradeStateMachine"},
	}

	sfnClient := sfn.NewFromConfig(cfg.awsConfig)

	for _, sm := range stateMachineKeys {
		t.Run(sm.Name, func(t *testing.T) {
			arn, ok := outputs[sm.OutputKey]
			require.True(t, ok, fmt.Sprintf("Output %s must exist in stack %s", sm.OutputKey, stackName))
			require.NotEmpty(t, arn, fmt.Sprintf("ARN for %s must not be empty", sm.Name))
			assert.Contains(t, arn, "arn:aws:states:", fmt.Sprintf("%s must be a valid Step Functions ARN", sm.Name))

			t.Logf("⚙️ [Step Functions] Describing state machine: %s (%s)", sm.Name, arn)
			desc, err := sfnClient.DescribeStateMachine(context.TODO(), &sfn.DescribeStateMachineInput{
				StateMachineArn: aws.String(arn),
			})
			require.NoError(t, err, fmt.Sprintf("Failed to describe state machine %s", arn))
			require.NotNil(t, desc, "Describe output must not be nil")

			// 1. Assert State Machine Status is ACTIVE
			assert.Equal(t, sfnTypes.StateMachineStatusActive, desc.Status, "State machine status must be ACTIVE")
			require.NotNil(t, desc.Definition, "Definition string must not be nil")

			// 2. Parse and Validate ASL JSON Definition
			var asl ASLDefinition
			err = json.Unmarshal([]byte(*desc.Definition), &asl)
			require.NoError(t, err, fmt.Sprintf("Failed to unmarshal ASL definition for %s", sm.Name))

			assert.NotEmpty(t, asl.StartAt, "StartAt field must be defined")
			assert.NotEmpty(t, asl.States, "States map must contain defined states")

			// StartAt state must exist
			_, startAtExists := asl.States[asl.StartAt]
			assert.True(t, startAtExists, fmt.Sprintf("StartAt state '%s' must exist in States", asl.StartAt))

			// 3. Verify State Transition Graph (No Orphan States or dangling transitions)
			for stateName, stateObj := range asl.States {
				if stateObj.Next != "" {
					_, nextExists := asl.States[stateObj.Next]
					assert.True(t, nextExists, fmt.Sprintf("State '%s' specifies Next='%s' which does not exist in %s", stateName, stateObj.Next, sm.Name))
				}
				if stateObj.Default != "" {
					_, defExists := asl.States[stateObj.Default]
					assert.True(t, defExists, fmt.Sprintf("State '%s' specifies Default='%s' which does not exist in %s", stateName, stateObj.Default, sm.Name))
				}
				for _, catcher := range stateObj.Catch {
					if catcher.Next != "" {
						_, catchNextExists := asl.States[catcher.Next]
						assert.True(t, catchNextExists, fmt.Sprintf("State '%s' specifies Catch.Next='%s' which does not exist in %s", stateName, catcher.Next, sm.Name))
					}
				}
			}

			// 4. Invariant: Provisioning state machine must have rollback / saga compensation states
			if sm.Name == "TenantProvisioningStateMachine" {
				hasRollback := false
				for sName := range asl.States {
					if containsAny(sName, "Rollback", "Compensat", "Cleanup", "Fail") {
						hasRollback = true
						break
					}
				}
				assert.True(t, hasRollback, "TenantProvisioningStateMachine must implement Saga rollback/compensation state")
			}

			// 4b. Invariant: Fleet Upgrade state machine must have Canary and Rollback states
			if sm.Name == "TenantFleetUpgradeStateMachine" {
				hasCanary := false
				hasRollback := false
				for sName := range asl.States {
					if containsAny(sName, "Canary") {
						hasCanary = true
					}
					if containsAny(sName, "Rollback") {
						hasRollback = true
					}
				}
				assert.True(t, hasCanary, "TenantFleetUpgradeStateMachine must implement Canary deployment states")
				assert.True(t, hasRollback, "TenantFleetUpgradeStateMachine must implement auto-rollback states")
			}

			// 4c. Invariant: AWS X-Ray Tracing & CloudWatch Logging Configuration
			if desc.TracingConfiguration != nil {
				assert.True(t, desc.TracingConfiguration.Enabled, "TracingConfiguration must be enabled for X-Ray distributed tracing")
			}
			if sm.Name == "TenantProvisioningStateMachine" || sm.Name == "TenantFleetUpgradeStateMachine" {
				if desc.LoggingConfiguration != nil {
					assert.Equal(t, sfnTypes.LogLevelAll, desc.LoggingConfiguration.Level, "LoggingConfiguration Level must be ALL")
				}
			}
		})
	}

	// 5. Verify Central CloudWatch Log Group for Step Functions
	sfnLogGroup, hasLogGroup := outputs["StepFunctionsLogGroupName"]
	assert.True(t, hasLogGroup, "Output StepFunctionsLogGroupName must exist in superadmin stack")
	assert.NotEmpty(t, sfnLogGroup, "StepFunctionsLogGroupName must not be empty")

	// 6. Verify SSM Runbook is fully decommissioned
	_, hasRunbook := outputs["SSMRunbookName"]
	assert.False(t, hasRunbook, "Legacy SSM Runbook must be fully decommissioned in favor of Step Functions")
	t.Logf("✅ [Terratest] All Modular Step Functions and Observability configurations validated.")
}

// TestInPlaceStepFunctions_ExecutionLifecycle triggers active Step Functions executions
// for tenant lifecycle state machines, polls until terminal state, and asserts SUCCEEDED.
func TestInPlaceStepFunctions_ExecutionLifecycle(t *testing.T) {
	cfg := LoadInPlaceConfig(t)
	stackName := cfg.GetStackName("06", "superadmin")

	outputs, exists := cfg.GetStackOutputs(t, stackName)
	if !exists {
		t.Skipf("Stack %s is not deployed yet; skipping In-Place Step Functions execution test.", stackName)
		return
	}

	suspensionArn, hasSusp := outputs["TenantSuspensionStateMachineArn"]
	require.True(t, hasSusp, fmt.Sprintf("Output TenantSuspensionStateMachineArn must exist in stack %s", stackName))
	require.NotEmpty(t, suspensionArn, "TenantSuspensionStateMachineArn must not be empty")

	deprovisionArn := outputs["TenantDeprovisioningStateMachineArn"]

	sfnClient := sfn.NewFromConfig(cfg.awsConfig)
	testTenantID := fmt.Sprintf("terratest-sfn-%d", time.Now().UnixNano()%100000000)
	t.Logf("🚀 [Step Functions] Testing active execution lifecycle with test tenant: %s", testTenantID)

	// Teardown Guardrail: ensure test tenant is purged even if assertions fail
	cleanedUp := false
	if deprovisionArn != "" {
		t.Cleanup(func() {
			if cleanedUp {
				return
			}
			t.Logf("🧹 [Teardown Guardrail] Ensuring cleanup for test tenant %s...", testTenantID)
			cleanupExecName := fmt.Sprintf("cleanup-%s-%d", testTenantID, time.Now().Unix())
			if len(cleanupExecName) > 80 {
				cleanupExecName = cleanupExecName[:80]
			}
			cleanupInput, _ := json.Marshal(map[string]string{
				"TenantId":  testTenantID,
				"tenant_id": testTenantID,
			})
			_, _ = sfnClient.StartExecution(context.TODO(), &sfn.StartExecutionInput{
				StateMachineArn: aws.String(deprovisionArn),
				Name:            aws.String(cleanupExecName),
				Input:           aws.String(string(cleanupInput)),
			})
		})
	}

	// 1. Trigger Tenant Suspension State Machine
	execName := fmt.Sprintf("exec-susp-%s-%d", testTenantID, time.Now().Unix())
	if len(execName) > 80 {
		execName = execName[:80]
	}
	inputBytes, err := json.Marshal(map[string]string{
		"TenantId":  testTenantID,
		"tenant_id": testTenantID,
	})
	require.NoError(t, err, "Failed to marshal Step Functions input")

	t.Logf("▶️ [Step Functions] Starting execution on %s (Name: %s)...", suspensionArn, execName)
	startRes, err := sfnClient.StartExecution(context.TODO(), &sfn.StartExecutionInput{
		StateMachineArn: aws.String(suspensionArn),
		Name:            aws.String(execName),
		Input:           aws.String(string(inputBytes)),
	})
	require.NoError(t, err, "StartExecution failed for TenantSuspensionStateMachine")
	require.NotNil(t, startRes, "StartExecution result must not be nil")
	executionArn := *startRes.ExecutionArn
	t.Logf("📡 [Step Functions] Execution started: %s", executionArn)

	// 2. Poll execution status via DescribeExecution until terminal state
	var finalDesc *sfn.DescribeExecutionOutput
	require.Eventually(t, func() bool {
		desc, err := sfnClient.DescribeExecution(context.TODO(), &sfn.DescribeExecutionInput{
			ExecutionArn: aws.String(executionArn),
		})
		if err != nil {
			t.Logf("DescribeExecution error (retrying): %v", err)
			return false
		}
		finalDesc = desc
		return desc.Status != sfnTypes.ExecutionStatusRunning
	}, 3*time.Minute, 2*time.Second, "Step Functions suspension execution did not complete within 3 minutes")

	require.NotNil(t, finalDesc, "Terminal DescribeExecution output must not be nil")
	t.Logf("🏁 [Step Functions] Execution %s finished with status: %s", executionArn, finalDesc.Status)

	// 3. Assert completion status equals SUCCEEDED
	assert.Equal(t, sfnTypes.ExecutionStatusSucceeded, finalDesc.Status,
		fmt.Sprintf("Step Functions execution %s failed: status=%s, error=%v, cause=%v",
			executionArn, finalDesc.Status, aws.ToString(finalDesc.Error), aws.ToString(finalDesc.Cause)))

	// 4. Also trigger and verify Deprovisioning State Machine if configured
	if deprovisionArn != "" {
		deprovExecName := fmt.Sprintf("exec-deprov-%s-%d", testTenantID, time.Now().Unix())
		if len(deprovExecName) > 80 {
			deprovExecName = deprovExecName[:80]
		}
		t.Logf("▶️ [Step Functions] Starting deprovisioning execution on %s...", deprovisionArn)
		deprovStart, err := sfnClient.StartExecution(context.TODO(), &sfn.StartExecutionInput{
			StateMachineArn: aws.String(deprovisionArn),
			Name:            aws.String(deprovExecName),
			Input:           aws.String(string(inputBytes)),
		})
		require.NoError(t, err, "StartExecution failed for TenantDeprovisioningStateMachine")
		deprovArn := *deprovStart.ExecutionArn

		var deprovDesc *sfn.DescribeExecutionOutput
		require.Eventually(t, func() bool {
			desc, err := sfnClient.DescribeExecution(context.TODO(), &sfn.DescribeExecutionInput{
				ExecutionArn: aws.String(deprovArn),
			})
			if err != nil {
				return false
			}
			deprovDesc = desc
			return desc.Status != sfnTypes.ExecutionStatusRunning
		}, 3*time.Minute, 2*time.Second, "Step Functions deprovisioning execution did not complete within 3 minutes")

		require.NotNil(t, deprovDesc, "Deprovision DescribeExecution output must not be nil")
		assert.Equal(t, sfnTypes.ExecutionStatusSucceeded, deprovDesc.Status,
			fmt.Sprintf("Deprovision execution %s failed: status=%s, error=%v, cause=%v",
				deprovArn, deprovDesc.Status, aws.ToString(deprovDesc.Error), aws.ToString(deprovDesc.Cause)))

		cleanedUp = true

		// 5. Verify that the DynamoDB registry item for the test tenant is purged
		ddbClient := dynamodb.NewFromConfig(cfg.awsConfig)
		tableName := fmt.Sprintf("%s-nextcloud-tenant-registry", cfg.Environment)
		getItemRes, ddbErr := ddbClient.GetItem(context.TODO(), &dynamodb.GetItemInput{
			TableName: aws.String(tableName),
			Key: map[string]ddbTypes.AttributeValue{
				"tenant_id": &ddbTypes.AttributeValueMemberS{Value: testTenantID},
			},
		})
		if ddbErr == nil {
			assert.Empty(t, getItemRes.Item, "Tenant DynamoDB registry record must be purged by TenantDeprovisioningStateMachine")
		}
	}
}

func containsAny(s string, substrs ...string) bool {
	for _, sub := range substrs {
		if len(s) >= len(sub) && (s == sub || fmt.Sprintf("%v", s) != "") {
			for i := 0; i+len(sub) <= len(s); i++ {
				if s[i:i+len(sub)] == sub {
					return true
				}
			}
		}
	}
	return false
}
