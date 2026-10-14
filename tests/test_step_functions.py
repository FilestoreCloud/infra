"""
Automated Test Suite for Modular Step Functions State Machines & SSM Runbook Decommissioning.
Validates:
1. Micro-Workflow Separation: 4 distinct state machines (Provision, Suspend, Resume, Deprovision).
2. Amazon States Language (ASL) JSON Syntax & AST Structural Integrity.
3. State Transition Matrix: Next, Choice, Catch, End/Fail integrity (Zero Orphan States).
4. Saga Pattern Rollback Invariants for Tenant Provisioning.
5. End-to-End State Machine Simulation (Happy Paths, Failure Rollback, Health Check Retry).
6. Complete Decommissioning of SSM Runbook & Associated Automation Roles.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Set
import pytest
import yaml

MODULE_TEMPLATE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../infra/modules/06-superadmin/template.yaml")
)

EXPECTED_STATE_MACHINES = [
    "TenantProvisioningStateMachine",
    "TenantSuspensionStateMachine",
    "TenantResumptionStateMachine",
    "TenantDeprovisioningStateMachine",
]


class CloudFormationLoader(yaml.SafeLoader):
    """YAML Loader that ignores CloudFormation intrinsic tags."""
    pass


def _cfn_tag_constructor(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


CloudFormationLoader.add_multi_constructor("!", _cfn_tag_constructor)


@pytest.fixture(scope="module")
def cfn_template() -> Dict[str, Any]:
    """Load and parse the 06-superadmin CloudFormation template."""
    assert os.path.exists(MODULE_TEMPLATE_PATH), f"Template not found at {MODULE_TEMPLATE_PATH}"
    with open(MODULE_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        data = yaml.load(f, Loader=CloudFormationLoader)
    return data


def parse_asl_definition(raw_asl: str) -> Dict[str, Any]:
    """Substitute CloudFormation placeholders and parse ASL JSON."""
    clean_asl = re.sub(r"\$\{([^}]+)\}", r"mock_\1", raw_asl)
    return json.loads(clean_asl)


# ==============================================================================
# 1. MODULAR SEPARATION & RESOURCE INTEGRITY
# ==============================================================================
def test_modular_state_machines_exist_and_isolated(cfn_template):
    """Verify all 4 distinct State Machines exist and monolithic machine is deleted."""
    resources = cfn_template.get("Resources", {})

    for sm_name in EXPECTED_STATE_MACHINES:
        assert sm_name in resources, f"Missing modular state machine: {sm_name}"
        resource = resources[sm_name]
        assert resource.get("Type") == "AWS::StepFunctions::StateMachine"
        props = resource.get("Properties", {})
        assert props.get("StateMachineType") == "STANDARD"
        assert "RoleArn" in props
        assert "DefinitionString" in props

    # Verify monolithic State Machine has been permanently removed
    assert "TenantLifecycleStateMachine" not in resources, (
        "TenantLifecycleStateMachine must be removed in favor of modular state machines"
    )


# ==============================================================================
# 2. ASL SYNTAX & GRAPH INTEGRITY TESTS
# ==============================================================================
@pytest.mark.parametrize("state_machine_name", EXPECTED_STATE_MACHINES)
def test_asl_syntax_and_structure(cfn_template, state_machine_name):
    """Verify ASL JSON parses without error and has valid top-level schema."""
    resource = cfn_template["Resources"][state_machine_name]
    raw_asl = resource["Properties"]["DefinitionString"]
    asl = parse_asl_definition(raw_asl)

    assert "Comment" in asl and len(asl["Comment"]) > 0
    assert "StartAt" in asl
    assert "States" in asl
    assert isinstance(asl["States"], dict)
    assert asl["StartAt"] in asl["States"], (
        f"StartAt state '{asl['StartAt']}' is not present in States for {state_machine_name}"
    )


@pytest.mark.parametrize("state_machine_name", EXPECTED_STATE_MACHINES)
def test_asl_state_transitions_and_no_orphans(cfn_template, state_machine_name):
    """
    Validate that all state transitions (Next, Choices, Default, Catch) are valid
    and no orphan (unreachable) states exist in the definition.
    """
    resource = cfn_template["Resources"][state_machine_name]
    asl = parse_asl_definition(resource["Properties"]["DefinitionString"])
    states = asl["States"]
    all_state_names = set(states.keys())

    reachable_states: Set[str] = {asl["StartAt"]}
    frontier = [asl["StartAt"]]

    while frontier:
        curr = frontier.pop(0)
        curr_def = states[curr]

        next_targets: List[str] = []

        if "Next" in curr_def:
            target = curr_def["Next"]
            assert target in all_state_names, (
                f"State '{curr}' in {state_machine_name} has invalid Next: '{target}'"
            )
            next_targets.append(target)

        if curr_def.get("Type") == "Choice":
            for choice in curr_def.get("Choices", []):
                if "Next" in choice:
                    c_next = choice["Next"]
                    assert c_next in all_state_names, (
                        f"Choice rule in '{curr}' has invalid Next: '{c_next}'"
                    )
                    next_targets.append(c_next)
            if "Default" in curr_def:
                default_target = curr_def["Default"]
                assert default_target in all_state_names, (
                    f"Choice '{curr}' has invalid Default: '{default_target}'"
                )
                next_targets.append(default_target)

        if "Catch" in curr_def:
            for catch_rule in curr_def["Catch"]:
                catch_target = catch_rule.get("Next")
                assert catch_target in all_state_names, (
                    f"Catch in '{curr}' has invalid Next: '{catch_target}'"
                )
                next_targets.append(catch_target)

        # Terminal state check
        if curr_def.get("End") is True or curr_def.get("Type") in ("Fail", "Succeed"):
            pass
        else:
            assert len(next_targets) > 0, (
                f"State '{curr}' in {state_machine_name} is neither terminal nor has next transitions."
            )

        for nt in next_targets:
            if nt not in reachable_states:
                reachable_states.add(nt)
                frontier.append(nt)

    orphan_states = all_state_names - reachable_states
    assert len(orphan_states) == 0, (
        f"Found unreachable orphan states in {state_machine_name}: {orphan_states}"
    )


# ==============================================================================
# 3. SAGA ROLLBACK INVARIANTS (TENANT PROVISIONING)
# ==============================================================================
def test_saga_rollback_invariants_provisioning(cfn_template):
    """
    Verify TenantProvisioningStateMachine adheres to Saga Pattern:
    1. Critical tasks have Catch blocks.
    2. Catch blocks point to SagaRollback.
    3. SagaRollback leads to MarkProvisionFailed.
    4. MarkProvisionFailed ends in a Fail state.
    """
    resource = cfn_template["Resources"]["TenantProvisioningStateMachine"]
    asl = parse_asl_definition(resource["Properties"]["DefinitionString"])
    states = asl["States"]

    # 1. ProvisionTenantResources must catch errors and route to SagaRollback
    prov_state = states["ProvisionTenantResources"]
    assert "Catch" in prov_state, "ProvisionTenantResources MUST have Catch block for Saga pattern"
    catch_targets = [c.get("Next") for c in prov_state["Catch"]]
    assert "SagaRollback" in catch_targets, "ProvisionTenantResources Catch must transition to SagaRollback"

    # 2. CheckHealthStatus must catch errors and route to SagaRollback
    health_state = states["CheckHealthStatus"]
    assert "Catch" in health_state, "CheckHealthStatus MUST have Catch block for Saga pattern"
    health_catch = [c.get("Next") for c in health_state["Catch"]]
    assert "SagaRollback" in health_catch, "CheckHealthStatus Catch must transition to SagaRollback"

    # 3. SagaRollback must invoke cleanup action and transition to MarkProvisionFailed
    rollback_state = states["SagaRollback"]
    assert rollback_state.get("Type") == "Task"
    assert rollback_state.get("Next") == "MarkProvisionFailed"
    payload = rollback_state.get("Parameters", {}).get("Payload", {})
    assert payload.get("action") == "SAGA_CLEANUP_TENANT"

    # 4. MarkProvisionFailed must set status FAILED and transition to ProvisionFailed
    failed_state = states["MarkProvisionFailed"]
    assert failed_state.get("Next") == "ProvisionFailed"
    attr_values = failed_state.get("Parameters", {}).get("ExpressionAttributeValues", {})
    assert attr_values.get(":s", {}).get("S") == "FAILED"

    # 5. ProvisionFailed must be a Fail type
    terminal_fail = states["ProvisionFailed"]
    assert terminal_fail.get("Type") == "Fail"
    assert terminal_fail.get("Error") == "ProvisioningFailed"


# ==============================================================================
# 4. EXECUTION SIMULATOR / TRANSITION SEQUENCE TESTS
# ==============================================================================
def _simulate_machine(asl: Dict[str, Any], initial_input: Dict[str, Any], context: Dict[str, Any]) -> List[str]:
    """Lightweight State Machine simulator evaluating execution path."""
    current_state_name = asl["StartAt"]
    execution_path = []
    max_steps = 30
    step_count = 0

    while step_count < max_steps:
        step_count += 1
        execution_path.append(current_state_name)
        state_def = asl["States"][current_state_name]
        stype = state_def.get("Type", "Task")

        if state_def.get("End") is True or stype in ("Fail", "Succeed"):
            break

        if stype == "Task":
            # Check if simulation context triggers an error on this task
            if context.get(f"{current_state_name}_fail"):
                if "Catch" in state_def:
                    current_state_name = state_def["Catch"][0]["Next"]
                    continue
                else:
                    raise RuntimeError(f"Unhandled error in task {current_state_name}")
            current_state_name = state_def["Next"]

        elif stype == "Wait":
            current_state_name = state_def["Next"]

        elif stype == "Choice":
            matched = False
            for rule in state_def.get("Choices", []):
                var_key = rule.get("Variable")
                # Resolve simple variable lookup
                if var_key == "$.health_check.Payload.healthy":
                    val = context.get("healthy", False)
                    if rule.get("BooleanEquals") == val:
                        current_state_name = rule["Next"]
                        matched = True
                        break
            if not matched:
                current_state_name = state_def.get("Default")
                assert current_state_name is not None, "Choice state has no matching branch and no Default"
        else:
            current_state_name = state_def.get("Next")

    return execution_path


def test_simulation_provisioning_happy_path(cfn_template):
    """Simulate TenantProvisioning happy path from request to ACTIVE."""
    asl = parse_asl_definition(
        cfn_template["Resources"]["TenantProvisioningStateMachine"]["Properties"]["DefinitionString"]
    )
    path = _simulate_machine(
        asl,
        {"TenantId": "acme-corp", "StorageQuotaGB": 100, "CompanyDomain": "acme.cloud"},
        {"healthy": True},
    )

    expected = [
        "ProvisionMarkDynamoDB",
        "ProvisionTenantResources",
        "WaitForContainerHealthy",
        "CheckHealthStatus",
        "IsContainerHealthy",
        "SeedTenantData",
        "MarkProvisionActive",
        "PublishProvisionMetric",
    ]
    assert path == expected, f"Unexpected path: {path}"


def test_simulation_provisioning_failure_and_saga_rollback(cfn_template):
    """Simulate infrastructure failure during provisioning triggering Saga Rollback."""
    asl = parse_asl_definition(
        cfn_template["Resources"]["TenantProvisioningStateMachine"]["Properties"]["DefinitionString"]
    )
    path = _simulate_machine(
        asl,
        {"TenantId": "acme-corp"},
        {"ProvisionTenantResources_fail": True},
    )

    expected = [
        "ProvisionMarkDynamoDB",
        "ProvisionTenantResources",
        "SagaRollback",
        "MarkProvisionFailed",
        "ProvisionFailed",
    ]
    assert path == expected, f"Unexpected rollback path: {path}"


def test_simulation_suspension_machine(cfn_template):
    """Simulate TenantSuspension execution path."""
    asl = parse_asl_definition(
        cfn_template["Resources"]["TenantSuspensionStateMachine"]["Properties"]["DefinitionString"]
    )
    path = _simulate_machine(asl, {"TenantId": "acme-corp"}, {})

    expected = [
        "SuspendScaleECS",
        "MarkSuspendedDynamoDB",
        "PublishSuspendMetric",
    ]
    assert path == expected, f"Unexpected suspension path: {path}"


def test_simulation_resumption_machine(cfn_template):
    """Simulate TenantResumption execution path."""
    asl = parse_asl_definition(
        cfn_template["Resources"]["TenantResumptionStateMachine"]["Properties"]["DefinitionString"]
    )
    path = _simulate_machine(asl, {"TenantId": "acme-corp"}, {"healthy": True})

    expected = [
        "ResumeScaleECS",
        "WaitForResumeHealthy",
        "CheckResumeHealth",
        "IsResumeHealthy",
        "MarkResumedDynamoDB",
        "PublishResumeMetric",
    ]
    assert path == expected, f"Unexpected resumption path: {path}"


def test_simulation_deprovisioning_machine(cfn_template):
    """Simulate TenantDeprovisioning execution path."""
    asl = parse_asl_definition(
        cfn_template["Resources"]["TenantDeprovisioningStateMachine"]["Properties"]["DefinitionString"]
    )
    path = _simulate_machine(asl, {"TenantId": "acme-corp"}, {})

    expected = [
        "DeprovisionTenantResources",
        "MarkDeprovisionedDynamoDB",
        "PublishDeprovisionMetric",
    ]
    assert path == expected, f"Unexpected deprovisioning path: {path}"


# ==============================================================================
# 5. DECOMMISSIONING & PARITY VERIFICATION
# ==============================================================================
def test_ssm_runbook_fully_decommissioned(cfn_template):
    """
    Ensure legacy SSM Runbook, Automation IAM Role, and Parameters are completely eradicated.
    """
    resources = cfn_template.get("Resources", {})
    outputs = cfn_template.get("Outputs", {})

    # 1. SSM Resources must NOT exist
    assert "SSMTenantOperatorRunbook" not in resources, "SSMTenantOperatorRunbook must be removed"
    assert "SSMAutomationRole" not in resources, "SSMAutomationRole must be removed"
    assert "SSMAutomationRoleArn" not in resources, "SSMAutomationRoleArn SSM parameter must be removed"

    # 2. SSM Outputs must NOT exist
    assert "SSMRunbookName" not in outputs, "SSMRunbookName must be removed from Outputs"
    assert "SSMAutomationRoleArn" not in outputs, "SSMAutomationRoleArn must be removed from Outputs"

    # 3. All 4 modular State Machine ARNs must be exported in Outputs
    expected_outputs = [
        "TenantProvisioningStateMachineArn",
        "TenantSuspensionStateMachineArn",
        "TenantResumptionStateMachineArn",
        "TenantDeprovisioningStateMachineArn",
    ]
    for out_key in expected_outputs:
        assert out_key in outputs, f"Outputs missing exported state machine ARN: {out_key}"
        val = outputs[out_key]
        assert "Value" in val
        assert val["Value"] in (
            "TenantProvisioningStateMachine",
            "TenantSuspensionStateMachine",
            "TenantResumptionStateMachine",
            "TenantDeprovisioningStateMachine",
        )
        export = val.get("Export", {})
        assert "Name" in export
