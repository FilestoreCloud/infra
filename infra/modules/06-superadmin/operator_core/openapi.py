"""
Storix Control Plane — OpenAPI 3.1 Specification Generator
Generates machine-readable OpenAPI documentation for all SuperAdmin REST routes.
"""

from typing import Any, Dict


def get_openapi_spec() -> Dict[str, Any]:
    """Generates complete OpenAPI 3.1.0 schema for the Storix SuperAdmin API."""
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Storix SaaS Multi-Tenant Control Plane API",
            "version": "2.0.0",
            "description": "Enterprise Control Plane REST API for Nextcloud Fleet Orchestration, Tenant Provisioning, Observability, and OCC Automation.",
            "contact": {
                "name": "Storix Platform Engineering",
                "url": "https://storix.cloud",
            },
        },
        "servers": [
            {"url": "/api/v1", "description": "SuperAdmin API Gateway Base Path"}
        ],
        "paths": {
            "/auth/login": {
                "post": {
                    "summary": "Authenticate SuperAdmin or Operator",
                    "operationId": "loginUser",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "password"],
                                    "properties": {
                                        "username": {"type": "string", "example": "admin"},
                                        "password": {"type": "string", "format": "password", "example": "StorixAdmin2026!Secure"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Authentication successful",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {"type": "string", "example": "OK"},
                                            "token": {"type": "string", "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."},
                                            "role": {"type": "string", "example": "SUPER_ADMIN"},
                                        },
                                    }
                                }
                            },
                        },
                        "401": {"description": "Invalid credentials"},
                    },
                }
            },
            "/tenants": {
                "get": {
                    "summary": "List all registered fleet tenants",
                    "operationId": "listTenants",
                    "security": [{"BearerAuth": []}],
                    "responses": {
                        "200": {
                            "description": "List of tenants with health and quota status",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {"type": "string", "example": "OK"},
                                            "tenants": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "tenantId": {"type": "string", "example": "dev-tenant"},
                                                        "status": {"type": "string", "enum": ["ACTIVE", "SUSPENDED", "PROVISIONING"]},
                                                        "plan": {"type": "string", "example": "ENTERPRISE"},
                                                        "storageQuotaGb": {"type": "integer", "example": 50},
                                                    },
                                                },
                                            },
                                        },
                                    }
                                }
                            },
                        }
                    },
                },
                "post": {
                    "summary": "Provision a new tenant asynchronously via Step Functions Saga",
                    "operationId": "provisionTenant",
                    "security": [{"BearerAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["tenantId"],
                                    "properties": {
                                        "tenantId": {"type": "string", "example": "acme-corp"},
                                        "plan": {"type": "string", "default": "STANDARD"},
                                        "storageQuotaGb": {"type": "integer", "default": 20},
                                        "customDomain": {"type": "string", "example": "files.acme.com"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {"description": "Tenant provisioning saga initiated"},
                    },
                },
            },
            "/tenants/{tenantId}/suspend": {
                "post": {
                    "summary": "Scale tenant down to zero (FinOps Suspend)",
                    "operationId": "suspendTenant",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {"name": "tenantId", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {
                        "200": {"description": "Tenant suspended successfully"},
                    },
                }
            },
            "/tenants/{tenantId}/resume": {
                "post": {
                    "summary": "Scale tenant up to active service (Resume)",
                    "operationId": "resumeTenant",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {"name": "tenantId", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {
                        "200": {"description": "Tenant resumed successfully"},
                    },
                }
            },
            "/tenants/{tenantId}/occ": {
                "post": {
                    "summary": "Execute Nextcloud OCC Command on tenant container",
                    "operationId": "executeOCC",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {"name": "tenantId", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["command"],
                                    "properties": {
                                        "command": {"type": "string", "example": "status"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "OCC execution completed with stdout/stderr"},
                    },
                }
            },
            "/observability/telemetry": {
                "get": {
                    "summary": "Retrieve aggregated fleet telemetry metrics",
                    "operationId": "getFleetTelemetry",
                    "security": [{"BearerAuth": []}],
                    "responses": {
                        "200": {"description": "Telemetry metrics returned"},
                    },
                }
            },
        },
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                }
            }
        },
    }
