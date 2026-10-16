"""Core engine for generating realistic, production-grade Storix simulation data."""

from __future__ import annotations

import base64
import csv
import datetime
import hashlib
import math
import random
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from mimesis import Generic
from mimesis.locales import Locale

from .models import (
    AuditLogModel,
    AwsTopologyModel,
    IncidentModel,
    SimulationPayloadModel,
    TelemetryMetricsModel,
    TenantModel,
    TenantUserModel,
)


def hash_password(password: str, salt: str = "StorixSalt2026") -> str:
    """Hash password with PBKDF2-HMAC-SHA256 (identical to tenant_operator_lambda)."""
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}:{h.hex()}"


def generate_totp_secret() -> str:
    """Generate RFC 6238 32-character base32 secret."""
    return base64.b32encode(secrets.token_bytes(20)).decode("utf-8")


class SimulatorEngine:
    """Generates consistent, relational, and time-coherent simulation data."""

    def __init__(self, seed: int = 42, environment: str = "prod"):
        self.seed = seed
        self.environment = environment
        random.seed(seed)
        np.random.seed(seed)
        self.mimesis = Generic(locale=Locale.EN, seed=seed)

    def load_tenants_csv(self, csv_path: Path) -> List[Dict[str, Any]]:
        tenants = []
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                tenants.append({
                    "tenant_id": r["tenant_id"].strip(),
                    "org_name": r.get("org_name", "").strip(),
                    "domain": r["domain"].strip(),
                    "admin_email": r["admin_email"].strip(),
                    "quota_gb": int(r.get("quota_gb", 100)),
                    "status": r.get("status", "ACTIVE").strip(),
                    "release_channel": r.get("release_channel", "STABLE").strip(),
                })
        return tenants

    def load_users_csv(self, csv_path: Path) -> Dict[str, List[Dict[str, Any]]]:
        users_by_tenant: Dict[str, List[Dict[str, Any]]] = {}
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                t_id = r["tenant_id"].strip()
                if t_id not in users_by_tenant:
                    users_by_tenant[t_id] = []
                users_by_tenant[t_id].append({
                    "username": r["username"].strip(),
                    "display_name": r["display_name"].strip(),
                    "email": r["email"].strip(),
                    "role": r.get("role", "User").strip(),
                    "quota_gb": int(r.get("quota_gb", 50)),
                    "storage_used_gb": float(r.get("storage_used_gb", 0.0)),
                    "group": r.get("group", "General").strip(),
                    "mfa_enabled": r.get("mfa_enabled", "false").lower() == "true",
                })
        return users_by_tenant

    def generate_aws_topology(self, tenant_id: str, domain: str) -> AwsTopologyModel:
        clean_id = tenant_id.lower().replace("-", "_")
        return AwsTopologyModel(
            cluster_name=f"{self.environment}-nextcloud-cluster",
            service_name=f"service-{tenant_id}",
            task_family=f"{self.environment}-nextcloud-{tenant_id}",
            alb_target_group_name=f"tg-{tenant_id}"[:32],
            alb_routing_rule=f"HostHeader: {domain}",
            health_check_path="/status.php",
            database_name=f"nc_{clean_id}",
            database_endpoint=f"postgres.{self.environment}.internal:5432",
            efs_id="fs-0b7465bf80b2333eb",
            efs_access_point_id=f"fsap-nc-{clean_id[:10]}",
            efs_mount_path=f"/tenants/{tenant_id}/config",
            s3_vault_prefix=f"s3://{self.environment}-nextcloud-vault-649519997247/tenants/{tenant_id}/",
            secrets_manager_path=f"/nextcloud/{self.environment}/tenants/{tenant_id}/credentials",
            vpc_id="vpc-030257f65c0893745",
            subnets=["subnet-08096079734609710", "subnet-09f187042a9b47101"],
            security_group_id="sg-020acf11e92c99ca4",
        )

    def generate_metrics(self, tenant_id: str, status: str, quota_gb: int, storage_used: float) -> TelemetryMetricsModel:
        now = datetime.datetime.now(datetime.timezone.utc)
        # Diurnal pattern (sine wave over 24 hours)
        hour = now.hour
        # Peak at 14:00 (2 PM), low at 03:00 (3 AM)
        base_cpu = 15.0 + 25.0 * math.sin((hour - 8) / 12.0 * math.pi)
        base_cpu = max(5.0, min(80.0, base_cpu))

        if status == "INCIDENT":
            current_cpu = 88.5
            current_mem = 942.0
            active_conns = 420
            rpm = 1250
        elif status == "SUSPENDED":
            current_cpu = 0.0
            current_mem = 0.0
            active_conns = 0
            rpm = 0
        else:
            current_cpu = round(base_cpu + random.uniform(-3.0, 5.0), 1)
            current_mem = round(400.0 + (current_cpu * 5.0) + random.uniform(-20.0, 20.0), 1)
            active_conns = int(current_cpu * 1.5 + random.randint(5, 20))
            rpm = int(active_conns * 4.2)

        # Generate 24 hourly time-series points
        time_series_cpu = []
        time_series_mem = []
        for i in range(24, 0, -1):
            pt_time = now - datetime.timedelta(hours=i)
            h = pt_time.hour
            p_cpu = max(4.0, 15.0 + 25.0 * math.sin((h - 8) / 12.0 * math.pi) + random.uniform(-2.0, 3.0))
            if status == "INCIDENT" and i <= 3:
                p_cpu = min(92.0, p_cpu + 50.0)  # Incident spike in last 3 hours
            time_series_cpu.append({"timestamp": pt_time.strftime("%H:00"), "value": round(p_cpu, 1)})
            time_series_mem.append({"timestamp": pt_time.strftime("%H:00"), "value": round(380.0 + p_cpu * 5.5, 1)})

        return TelemetryMetricsModel(
            current_cpu_percent=current_cpu,
            current_memory_mb=current_mem,
            memory_limit_mb=1024.0,
            active_connections=active_conns,
            requests_per_minute=rpm,
            storage_used_gb=round(storage_used, 1),
            quota_gb=quota_gb,
            time_series_cpu=time_series_cpu,
            time_series_memory=time_series_mem,
        )

    def generate_incident(self, tenant_id: str, status: str) -> Tuple[Optional[IncidentModel], List[IncidentModel]]:
        now = datetime.datetime.now(datetime.timezone.utc)
        history = [
            IncidentModel(
                incident_id="INC-2026-0891",
                title="Transient 504 Gateway Timeout during automated daily backup",
                severity="MEDIUM",
                status="RESOLVED",
                description="Elevated latency during EFS daily snapshot synchronization.",
                root_cause="Concurrent I/O burst on EFS General Purpose bursting mode.",
                action_taken="Switched EFS provisioned throughput to 50 MB/s.",
                reported_by="System",
                reported_at=(now - datetime.timedelta(days=12)).isoformat(),
                resolved_at=(now - datetime.timedelta(days=12, hours=-1)).isoformat(),
            ),
            IncidentModel(
                incident_id="INC-2026-0942",
                title="LiteLLM AI Sidecar Memory Pressure",
                severity="LOW",
                status="RESOLVED",
                description="Occasional high token request caused Python process restart.",
                root_cause="Unbounded context window in document summary worker.",
                action_taken="Configured max_tokens limit in litellm config.",
                reported_by="System",
                reported_at=(now - datetime.timedelta(days=5)).isoformat(),
                resolved_at=(now - datetime.timedelta(days=5, hours=-2)).isoformat(),
            ),
        ]

        active_incident = None
        if status == "INCIDENT":
            active_incident = IncidentModel(
                incident_id="INC-2026-1044",
                title="PostgreSQL Database Connection Pool Exhaustion",
                severity="HIGH",
                status="OPEN",
                description="Connection limit reached on dedicated database replica during bulk sync.",
                root_cause="Nextcloud desktop clients holding idle connections above max_connections parameter.",
                action_taken="Automated script draining idle connections; tuning idle_in_transaction_session_timeout.",
                reported_by="System",
                reported_at=(now - datetime.timedelta(hours=2)).isoformat(),
            )
            history.insert(0, active_incident)

        return active_incident, history

    def generate_audit_logs(self, tenants: List[Dict[str, Any]], count: int = 150) -> List[AuditLogModel]:
        logs: List[AuditLogModel] = []
        now = datetime.datetime.now(datetime.timezone.utc)
        actions = [
            ("LOGIN", "SuperAdmin console session authentication"),
            ("VERIFY_MFA", "TOTP MFA challenge successfully validated"),
            ("TENANT_PROVISION", "Provisioned dedicated ECS Fargate service and database"),
            ("TENANT_SUSPEND", "Scaled down task count to 0 for FinOps cost reduction"),
            ("TENANT_RESUME", "Restored task count to 1 and re-enabled ALB listener routing"),
            ("USER_CREATE", "Provisioned new department team member in tenant directory"),
            ("QUOTA_UPDATE", "Adjusted storage quota threshold"),
            ("OCC_EXEC", "Executed administrative OCC command via terminal bridge"),
            ("PASSWORD_RESET", "Triggered secure administrative credential rotation"),
        ]

        # Generate timestamps backwards over 30 days
        for idx in range(count):
            days_ago = (count - idx) * (30.0 / count) + random.uniform(-0.1, 0.1)
            ts = (now - datetime.timedelta(days=days_ago)).isoformat()
            act, desc = random.choice(actions)
            t = random.choice(tenants)
            actor = random.choice(["superadmin@storix.io", "secops-bot", f"admin@{t['tenant_id']}.com"])
            ip = f"192.168.1.{random.randint(10, 250)}" if random.random() > 0.3 else f"10.0.{random.randint(1, 50)}.{random.randint(2, 250)}"

            logs.append(
                AuditLogModel(
                    event_id=f"evt-{idx+1000:04d}",
                    timestamp=ts,
                    actor=actor,
                    role="SuperAdmin",
                    action=act,
                    target=t["tenant_id"],
                    status="SUCCESS" if random.random() > 0.05 else "FAILED",
                    details=f"{desc} for tenant {t['tenant_id']}",
                    ip_address=ip,
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                )
            )

        # Sort logs chronologically
        logs.sort(key=lambda log_item: log_item.timestamp)
        return logs

    def build_full_simulation(
        self,
        tenants_csv_path: Path,
        users_csv_path: Path,
        audit_logs_count: int = 150,
    ) -> SimulationPayloadModel:
        raw_tenants = self.load_tenants_csv(tenants_csv_path)
        raw_users_by_tenant = self.load_users_csv(users_csv_path)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        tenant_models: List[TenantModel] = []
        total_users = 0

        for rt in raw_tenants:
            t_id = rt["tenant_id"]
            user_list = raw_users_by_tenant.get(t_id, [])
            total_users += len(user_list)

            # Compute tenant storage used as sum of user storage
            storage_used = sum(u["storage_used_gb"] for u in user_list)
            if storage_used == 0.0:
                storage_used = round(rt["quota_gb"] * random.uniform(0.15, 0.45), 1)

            user_models = [
                TenantUserModel(
                    username=u["username"],
                    display_name=u["display_name"],
                    email=u["email"],
                    role=u["role"],
                    quota_gb=u["quota_gb"],
                    storage_used_gb=u["storage_used_gb"],
                    status="ACTIVE" if rt["status"] != "SUSPENDED" else "DISABLED",
                    mfa_enabled=u["mfa_enabled"],
                    password_hash=hash_password(f"{u['username']}Pass2026!"),
                    mfa_secret=generate_totp_secret(),
                    created_at=now_iso,
                    last_login=now_iso,
                )
                for u in user_list
            ]

            topo = self.generate_aws_topology(t_id, rt["domain"])
            metrics = self.generate_metrics(t_id, rt["status"], rt["quota_gb"], storage_used)
            incident, incidents_hist = self.generate_incident(t_id, rt["status"])

            tenant_models.append(
                TenantModel(
                    id=t_id,
                    tenant_id=t_id,
                    domain=rt["domain"],
                    status=rt["status"],
                    admin_email=rt["admin_email"],
                    quota_gb=rt["quota_gb"],
                    storage_used_gb=round(storage_used, 1),
                    service_name=topo.service_name,
                    database_name=topo.database_name,
                    release_channel=rt["release_channel"],
                    created_at="2026-03-01T00:00:00Z",
                    last_updated=now_iso,
                    accounts=user_models,
                    aws_topology=topo,
                    metrics=metrics,
                    incident=incident,
                    incidents_history=incidents_hist,
                )
            )

        audit_logs = self.generate_audit_logs(raw_tenants, count=audit_logs_count)

        return SimulationPayloadModel(
            environment=self.environment,
            generated_at=now_iso,
            tenants=tenant_models,
            audit_logs=audit_logs,
            total_tenants=len(tenant_models),
            total_users=total_users,
            total_audit_logs=len(audit_logs),
        )
