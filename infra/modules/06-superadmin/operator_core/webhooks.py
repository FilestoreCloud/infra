"""
Webhook management and notification dispatching module for Slack, Discord, PagerDuty, and custom webhooks.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .common import (
    ENVIRONMENT_NAME,
    TABLE_NAME,
    dynamodb,
    unmarshal_ddb_item,
)


def get_webhook_config():
    """Retrieve global webhook notification configuration."""
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    default_config = {
        "enabled": True,
        "slack_url": "",
        "discord_url": "",
        "pagerduty_key": "",
        "custom_url": "",
        "events": {
            "incident_declared": True,
            "circuit_breaker": True,
            "tenant_cloned": True,
            "agent_restarted": True,
        },
        "last_updated": now_iso,
    }
    try:
        res = dynamodb.get_item(
            TableName=TABLE_NAME, Key={"tenant_id": {"S": "SYSTEM#WEBHOOK_CONFIG"}}
        )
        if "Item" in res:
            item = unmarshal_ddb_item(res["Item"])
            cfg_raw = item.get("config")
            if isinstance(cfg_raw, dict):
                return cfg_raw
            elif isinstance(cfg_raw, str):
                return json.loads(cfg_raw)
    except Exception as e:
        print(f"Notice: Webhook config lookup fallback: {e}")
    return default_config


def save_webhook_config(config):
    """Persist global webhook notification configuration."""
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    config["last_updated"] = now_iso
    try:
        dynamodb.put_item(
            TableName=TABLE_NAME,
            Item={
                "tenant_id": {"S": "SYSTEM#WEBHOOK_CONFIG"},
                "config": {"S": json.dumps(config)},
                "last_updated": {"S": now_iso},
            },
        )
        return config
    except Exception as e:
        print(f"Error persisting webhook config: {e}")
        return config


def dispatch_webhook_notification(event_type, tenant_id, data=None):
    """Non-blocking notification dispatcher for Slack, Discord, PagerDuty, and Custom Webhooks."""
    config = get_webhook_config()
    if not config or not config.get("enabled", True):
        return

    events_map = config.get("events", {})
    ev_key = event_type.lower()
    if not events_map.get(ev_key, True):
        return

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data = data or {}
    dispatched = []

    # 1. Slack Incoming Webhook
    slack_url = config.get("slack_url", "").strip()
    if slack_url and slack_url.startswith("http"):
        try:
            severity = data.get("severity", "INFO")
            color = "#ef4444" if severity in ["SEV-1", "CRITICAL"] else "#ec7211"
            slack_payload = {
                "text": f"[{event_type}] Tenant: {tenant_id}",
                "attachments": [
                    {
                        "color": color,
                        "title": f"Nextcloud SaaS Alert: {event_type}",
                        "fields": [
                            {"title": "Tenant ID", "value": tenant_id, "short": True},
                            {
                                "title": "Environment",
                                "value": ENVIRONMENT_NAME,
                                "short": True,
                            },
                            {"title": "Timestamp", "value": now_iso, "short": False},
                            {
                                "title": "Payload Details",
                                "value": f"```{json.dumps(data, indent=2)[:1000]}```",
                                "short": False,
                            },
                        ],
                        "footer": "Nextcloud SaaS Super Admin Control Plane",
                    }
                ],
            }
            req = urllib.request.Request(
                slack_url,
                data=json.dumps(slack_payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "NextcloudSaaS-AlertManager/1.0",
                },
            )
            urllib.request.urlopen(req, timeout=3)
            dispatched.append("Slack")
        except Exception as e:
            print(f"Notice: Slack webhook dispatch error: {e}")

    # 2. Discord Webhook
    discord_url = config.get("discord_url", "").strip()
    if discord_url and discord_url.startswith("http"):
        try:
            discord_payload = {
                "content": f"🚨 **Nextcloud SaaS Event: {event_type}** | Tenant: `{tenant_id}`",
                "embeds": [
                    {
                        "title": f"Event: {event_type}",
                        "color": 15418708,
                        "fields": [
                            {"name": "Tenant", "value": tenant_id, "inline": True},
                            {"name": "Env", "value": ENVIRONMENT_NAME, "inline": True},
                            {"name": "Time", "value": now_iso, "inline": False},
                        ],
                        "description": f"```{json.dumps(data, indent=2)[:1000]}```",
                        "footer": {"text": "Nextcloud SaaS Super Admin"},
                    }
                ],
            }
            req = urllib.request.Request(
                discord_url,
                data=json.dumps(discord_payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "NextcloudSaaS-AlertManager/1.0",
                },
            )
            urllib.request.urlopen(req, timeout=3)
            dispatched.append("Discord")
        except Exception as e:
            print(f"Notice: Discord webhook dispatch error: {e}")

    # 3. PagerDuty Events API v2
    pd_key = config.get("pagerduty_key", "").strip()
    if pd_key:
        try:
            pd_payload = {
                "routing_key": pd_key,
                "event_action": "trigger",
                "payload": {
                    "summary": f"Nextcloud SaaS {event_type}: {tenant_id}",
                    "source": f"nextcloud-control-plane-{ENVIRONMENT_NAME}",
                    "severity": (
                        "critical" if data.get("severity") == "SEV-1" else "warning"
                    ),
                    "custom_details": data,
                },
            }
            req = urllib.request.Request(
                "https://events.pagerduty.com/v2/enqueue",
                data=json.dumps(pd_payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "NextcloudSaaS-AlertManager/1.0",
                },
            )
            urllib.request.urlopen(req, timeout=3)
            dispatched.append("PagerDuty")
        except Exception as e:
            print(f"Notice: PagerDuty webhook dispatch error: {e}")

    # 4. Custom Generic Webhook
    custom_url = config.get("custom_url", "").strip()
    if custom_url and custom_url.startswith("http"):
        try:
            custom_payload = {
                "event": event_type,
                "tenant_id": tenant_id,
                "environment": ENVIRONMENT_NAME,
                "timestamp": now_iso,
                "data": data,
            }
            req = urllib.request.Request(
                custom_url,
                data=json.dumps(custom_payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "NextcloudSaaS-AlertManager/1.0",
                    "X-Nextcloud-Event": event_type,
                },
            )
            urllib.request.urlopen(req, timeout=3)
            dispatched.append("Custom")
        except Exception as e:
            print(f"Notice: Custom webhook dispatch error: {e}")

    return dispatched


def test_webhook_endpoint(webhook_type, webhook_url):
    """Test webhook delivery with a sample notification."""
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if not webhook_url or not webhook_url.startswith("http"):
        return {
            "success": False,
            "error": "Invalid webhook URL: must start with http:// or https://",
        }

    try:
        if webhook_type == "slack":
            payload = {
                "text": "[Nextcloud SaaS Test Alert] Super Admin Webhook connectivity test",
                "attachments": [
                    {
                        "color": "#10b981",
                        "title": "✅ Super Admin Webhook Test Passed",
                        "text": f"Webhook integration verified successfully for environment `{ENVIRONMENT_NAME}` at {now_iso}.",
                        "footer": "Nextcloud SaaS Super Admin Control Plane",
                    }
                ],
            }
        elif webhook_type == "discord":
            payload = {
                "content": f"✅ **Nextcloud SaaS Webhook Test**: Connection verified successfully at {now_iso}!",
                "embeds": [
                    {
                        "title": "Webhook Connection Test",
                        "description": f"Target environment: `{ENVIRONMENT_NAME}`\nStatus: Operational",
                        "color": 1098257,
                    }
                ],
            }
        elif webhook_type == "pagerduty":
            payload = {
                "routing_key": webhook_url,
                "event_action": "trigger",
                "payload": {
                    "summary": f"Nextcloud SaaS Control Plane Test Alert ({ENVIRONMENT_NAME})",
                    "source": "nextcloud-super-admin-test",
                    "severity": "info",
                },
            }
            webhook_url = "https://events.pagerduty.com/v2/enqueue"
        else:
            payload = {
                "event": "TEST_ALERT",
                "message": "Super Admin Webhook connectivity verified successfully!",
                "timestamp": now_iso,
                "environment": ENVIRONMENT_NAME,
            }

        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "NextcloudSaaS-AlertManager/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            status = resp.status
            return {
                "success": True,
                "status_code": status,
                "message": f"Test alert delivered successfully (HTTP {status})",
            }
    except urllib.error.HTTPError as e:
        return {
            "success": False,
            "status_code": e.code,
            "error": f"HTTP {e.code}: {e.reason}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
