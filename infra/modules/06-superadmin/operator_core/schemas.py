"""
Pydantic v2 Contract and Data Model Schemas for Storix Control Plane.
Guarantees schema invariants across API endpoints, Lambda events, and DynamoDB records.
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class TenantStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    INITIALIZING = "INITIALIZING"
    PROVISIONING = "PROVISIONING"
    DEPROVISIONING = "DEPROVISIONING"
    FAILED = "FAILED"


class TenantRecord(BaseModel):
    tenant_id: str = Field(
        ...,
        min_length=3,
        max_length=64,
        pattern=r"^[a-z0-9-]+$",
        description="Tenant identifier in lowercase alphanumeric with hyphens",
    )
    domain: str = Field(..., description="Tenant public FQDN")
    status: TenantStatus = TenantStatus.INITIALIZING
    quota_gb: int = Field(100, ge=1, le=100000, description="Allocated storage quota in GB")
    admin_email: Optional[str] = None
    created_at: Optional[str] = None

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        trimmed = v.strip().lower()
        if trimmed == "*":
            raise ValueError("Bare wildcard '*' is strictly forbidden as a tenant domain")
        if len(trimmed) < 3:
            raise ValueError("Domain must have at least 3 characters")
        return trimmed


class AuditLogEvent(BaseModel):
    event_id: str = Field(..., min_length=1)
    timestamp: str = Field(..., min_length=10)
    actor: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    status: str = Field(..., pattern=r"^(SUCCESS|DENIED|FAILED)$")
    target: Optional[str] = "system"
    details: Optional[str] = None
    ip_address: Optional[str] = None


class SessionTokenClaims(BaseModel):
    user: str = Field(..., min_length=1)
    sub: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    mfa: bool = True
    exp: int = Field(..., gt=0)
    nonce: str = Field(..., min_length=8)


class WebhookNotification(BaseModel):
    event: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    timestamp: str = Field(..., min_length=10)
    payload: dict = Field(default_factory=dict)
