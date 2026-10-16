"""Pydantic data models for Storix Multi-Tenant Real-Time Simulation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class TenantUserModel(BaseModel):
    username: str
    display_name: str
    email: str
    role: str = "User"  # TenantAdmin, User, ServiceAccount
    quota_gb: int = 50
    storage_used_gb: float = 0.0
    status: str = "ACTIVE"
    mfa_enabled: bool = False
    password_hash: Optional[str] = None
    mfa_secret: Optional[str] = None
    last_login: Optional[str] = None
    created_at: Optional[str] = None


class AwsTopologyModel(BaseModel):
    cluster_name: str
    service_name: str
    launch_type: str = "FARGATE"
    task_family: str
    alb_target_group_name: str
    alb_routing_rule: str
    health_check_path: str = "/status.php"
    database_name: str
    database_engine: str = "PostgreSQL 16.3"
    database_endpoint: str
    efs_id: str
    efs_access_point_id: str
    efs_mount_path: str
    s3_vault_prefix: str
    secrets_manager_path: str
    vpc_id: str
    subnets: List[str]
    security_group_id: str


class IncidentModel(BaseModel):
    incident_id: str
    title: str
    severity: str = "MEDIUM"  # CRITICAL, HIGH, MEDIUM, LOW
    status: str = "OPEN"  # OPEN, RESOLVED
    description: str
    root_cause: Optional[str] = None
    action_taken: Optional[str] = None
    reported_by: str = "System"
    reported_at: str
    resolved_at: Optional[str] = None


class TelemetryMetricsModel(BaseModel):
    current_cpu_percent: float
    current_memory_mb: float
    memory_limit_mb: float = 1024.0
    active_connections: int
    requests_per_minute: int
    storage_used_gb: float
    quota_gb: int
    time_series_cpu: List[Dict[str, Any]] = []
    time_series_memory: List[Dict[str, Any]] = []


class TenantModel(BaseModel):
    id: str
    tenant_id: str
    domain: str
    status: str = "ACTIVE"  # ACTIVE, SUSPENDED, INCIDENT, DEGRADED, MAINTENANCE
    admin_email: str
    quota_gb: int = 100
    storage_used_gb: float = 0.0
    service_name: str
    database_name: str
    release_channel: str = "STABLE"  # STABLE, BETA, CANARY
    created_at: str
    last_updated: str
    accounts: List[TenantUserModel] = []
    aws_topology: Optional[AwsTopologyModel] = None
    metrics: Optional[TelemetryMetricsModel] = None
    incident: Optional[IncidentModel] = None
    incidents_history: List[IncidentModel] = []


class AuditLogModel(BaseModel):
    event_id: str
    timestamp: str
    actor: str
    role: str = "SuperAdmin"
    action: str
    target: str
    status: str = "SUCCESS"  # SUCCESS, FAILED
    details: Optional[str] = None
    ip_address: str = "127.0.0.1"
    user_agent: str = "Mozilla/5.0"


class SimulationPayloadModel(BaseModel):
    environment: str = "prod"
    generated_at: str
    tenants: List[TenantModel]
    audit_logs: List[AuditLogModel]
    total_tenants: int
    total_users: int
    total_audit_logs: int
