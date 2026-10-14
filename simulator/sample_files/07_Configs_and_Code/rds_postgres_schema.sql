-- Storix Dedicated Tenant Initial Database Schema
CREATE TABLE IF NOT EXISTS oc_storix_metadata (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    provisioned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    storage_quota_bytes BIGINT NOT NULL,
    ai_assistant_enabled BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_storix_tenant_id ON oc_storix_metadata(tenant_id);
