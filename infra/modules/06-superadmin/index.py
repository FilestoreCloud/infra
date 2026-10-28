import json
from tenant_operator_lambda import lambda_handler as operator_handler
from tenant_worker_lambda import lambda_handler as worker_handler

def lambda_handler(event, context):
    """
    Universal router for SuperAdmin Lambdas:
    Direct Step Functions task invokes go to worker_handler.
    API Gateway / HTTP / direct operator invokes go to operator_handler.
    """
    if isinstance(event, dict):
        if "requestContext" in event or "httpMethod" in event or "rawPath" in event:
            return operator_handler(event, context)
        action = event.get("action", "")
        # Specific worker actions
        if action.startswith("DEPROVISION_") or action.startswith("PROVISION_") or action in [
            "CREATE_DATABASE", "PROVISION_ECS", "DEPROVISION_ECS", "DEPROVISION_STORAGE",
            "RESTART_TASK", "SET_STATUS_WORKER"
        ]:
            return worker_handler(event, context)
    return operator_handler(event, context)
