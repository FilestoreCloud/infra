"""
Storix Control Plane — EventBridge EventBus Integration
Publishes standard domain event schemas: TenantCreated, TenantSuspended, TenantResumed, StorageLimitReached.
"""

import json
import logging
import os
import time
from typing import Any, Dict

from operator_core.common import _LazyAwsClient

logger = logging.getLogger(__name__)

events_client = _LazyAwsClient("events", region_name=os.environ.get("AWS_REGION", "ap-southeast-1"))
ENVIRONMENT_NAME = os.environ.get("ENVIRONMENT_NAME", "dev")
EVENT_BUS_NAME = os.environ.get("EVENT_BUS_NAME", f"{ENVIRONMENT_NAME}-storix-tenant-events")


def publish_tenant_event(
    detail_type: str,
    tenant_id: str,
    data: Dict[str, Any],
    actor: str = "SYSTEM",
) -> bool:
    """
    Publishes a strongly-typed domain event to the custom EventBus.
    Standard Event Schemas:
      - TenantCreated: payload with plan, storage_quota_gb, custom_domain
      - TenantSuspended: payload with reason, previous_status
      - TenantResumed: payload with previous_status
      - StorageLimitReached: payload with current_usage_gb, quota_gb, percent_used
      - TenantCustomDomainRegistered: payload with custom_domain, status, cname_target
      - StorageQuotaWarning: payload with storage_used_gb, quota_gb, quota_utilization_pct, warning_level
      - TenantDataExportRequested: payload with database_name, download_url, expires_in_hours
      - TenantCryptoShredded: payload with status, shredded_at, compliance_standard
    """
    payload = {
        "metadata": {
            "tenantId": tenant_id,
            "timestamp": int(time.time()),
            "environment": ENVIRONMENT_NAME,
            "actor": actor,
        },
        "detail": data,
    }

    entry: Dict[str, Any] = {
        "Source": "storix.controlplane",
        "DetailType": detail_type,
        "Detail": json.dumps(payload),
        "EventBusName": EVENT_BUS_NAME,
    }

    try:
        response = events_client.put_events(Entries=[entry])  # type: ignore[list-item]
        failed_count = response.get("FailedEntryCount", 0)
        if failed_count > 0:
            logger.warning("Event publishing reported failures: %s", response.get("Entries", []))
            return False
        logger.info("Successfully emitted EventBridge event: %s for tenant %s", detail_type, tenant_id)
        return True
    except Exception as exc:
        logger.error("Failed to publish EventBridge event (%s): %s", detail_type, exc)
        return False
