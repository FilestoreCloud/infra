#!/usr/bin/env python3
"""
Storix Cloudflare DNS & Auto-Subdomain Lifecycle Manager
=========================================================
Automatically discovers ALB & CloudFront endpoints from AWS CloudFormation
and configures/cleans DNS records on Cloudflare (via Cloudflare API or CLI).

Usage:
    python3 manage_dns.py status --env dev --zone png261.dev
    python3 manage_dns.py sync   --env dev --zone png261.dev [--token <CF_TOKEN>]
    python3 manage_dns.py clean  --env dev --zone png261.dev [--token <CF_TOKEN>]
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import boto3

CF_API_BASE = "https://api.cloudflare.com/client/v4"


def get_aws_endpoints(env: str, region: str = "ap-southeast-1"):
    """Query CloudFormation outputs for ALB DNS and CloudFront Web Domain."""
    cf_client = boto3.client("cloudformation", region_name=region)
    alb_dns = None
    cloudfront_domain = None

    try:
        compute_stack = cf_client.describe_stacks(StackName=f"{env}-nextcloud-05-compute")
        for output in compute_stack["Stacks"][0].get("Outputs", []):
            if output["OutputKey"] in ["LoadBalancerDNSName", "LoadBalancerDNS"]:
                alb_dns = output["OutputValue"]
                break
    except Exception as e:
        print(f"[WARN] Could not retrieve compute stack outputs: {e}")

    try:
        admin_stack = cf_client.describe_stacks(StackName=f"{env}-nextcloud-06-superadmin")
        for output in admin_stack["Stacks"][0].get("Outputs", []):
            if output["OutputKey"] in ["AdminWebDomainName", "AdminWebURL"]:
                val = output["OutputValue"]
                cloudfront_domain = val.replace("https://", "").replace("http://", "").rstrip("/")
                break
    except Exception as e:
        print(f"[WARN] Could not retrieve superadmin stack outputs: {e}")

    return alb_dns, cloudfront_domain


def cf_request(method: str, path: str, token: str, data: dict = None):
    """Execute authenticated Cloudflare v4 REST API request."""
    url = f"{CF_API_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"[ERROR] Cloudflare API {method} {path} failed: {e.code} - {err_body}")
        return None
    except Exception as exc:
        print(f"[ERROR] Cloudflare API connection failed: {exc}")
        return None


def get_zone_id(zone_name: str, token: str) -> str | None:
    """Find Zone ID by root domain name."""
    res = cf_request("GET", f"/zones?name={zone_name}", token)
    if res and res.get("success") and res.get("result"):
        return res["result"][0]["id"]
    return None


def sync_records(env: str, zone_name: str, token: str | None = None):
    """Upsert CNAME records for Wildcard Tenants and SuperAdmin Console."""
    alb_dns, cf_domain = get_aws_endpoints(env)
    print("\n" + "=" * 60)
    print(f"🚀 STORIX DNS RESOLUTION CONFIGURATION (Environment: {env})")
    print("=" * 60)
    print(f"  • Target ALB DNS Name:          {alb_dns or 'NOT_DEPLOYED'}")
    print(f"  • Target CloudFront Domain:     {cf_domain or 'NOT_DEPLOYED'}")
    print(f"  • Base Domain Zone:             {zone_name}")
    print("=" * 60)

    desired_records = [
        {
            "name": f"*.{zone_name}",
            "type": "CNAME",
            "content": alb_dns,
            "proxied": True,
            "comment": f"storix-{env}-tenant-wildcard",
        },
        {
            "name": f"dev-tenant.{zone_name}",
            "type": "CNAME",
            "content": alb_dns,
            "proxied": True,
            "comment": f"storix-{env}-dev-tenant",
        },
        {
            "name": f"admin.{zone_name}",
            "type": "CNAME",
            "content": cf_domain,
            "proxied": True,
            "comment": f"storix-{env}-admin-console",
        },
    ]

    if not token:
        print("\n[INFO] No Cloudflare API Token provided.")
        print("To complete manual configuration on Cloudflare Dashboard:")
        for r in desired_records:
            if r["content"]:
                print(f"  ➜ Record: {r['type']:<5} {r['name']:<25} ➔ {r['content']} (Proxied: {r['proxied']})")
        return

    zone_id = get_zone_id(zone_name, token)
    if not zone_id:
        print(f"[ERROR] Zone {zone_name} not found with provided token.")
        return

    # List existing records
    existing = cf_request("GET", f"/zones/{zone_id}/dns_records?per_page=100", token)
    records_by_name = {}
    if existing and existing.get("result"):
        for rec in existing["result"]:
            records_by_name[rec["name"]] = rec

    for d in desired_records:
        if not d["content"]:
            print(f"[SKIP] Skipping {d['name']} because target endpoint is not available.")
            continue

        target_name = d["name"].replace("*.", "") if d["name"].startswith("*.") else d["name"]
        existing_rec = records_by_name.get(d["name"]) or records_by_name.get(f"\\*.{zone_name}")

        record_payload = {
            "type": d["type"],
            "name": d["name"],
            "content": d["content"],
            "ttl": 1,
            "proxied": d["proxied"],
            "comment": d["comment"],
        }

        if existing_rec:
            rec_id = existing_rec["id"]
            res = cf_request("PUT", f"/zones/{zone_id}/dns_records/{rec_id}", token, record_payload)
            if res and res.get("success"):
                print(f"  ✔ Updated: {d['name']} ➔ {d['content']}")
        else:
            res = cf_request("POST", f"/zones/{zone_id}/dns_records", token, record_payload)
            if res and res.get("success"):
                print(f"  ✔ Created: {d['name']} ➔ {d['content']}")


def clean_records(env: str, zone_name: str, token: str | None = None):
    """Remove all Storix-managed DNS records for the environment."""
    if not token:
        print("[INFO] No Cloudflare API Token provided. Skipping automated remote DNS purge.")
        return

    zone_id = get_zone_id(zone_name, token)
    if not zone_id:
        return

    existing = cf_request("GET", f"/zones/{zone_id}/dns_records?per_page=100", token)
    if not existing or not existing.get("result"):
        return

    match_prefix = f"storix-{env}-"
    for rec in existing["result"]:
        comment = rec.get("comment") or ""
        if match_prefix in comment:
            cf_request("DELETE", f"/zones/{zone_id}/dns_records/{rec['id']}", token)
            print(f"  🗑 Deleted record: {rec['name']} ({rec['content']})")


def main():
    parser = argparse.ArgumentParser(description="Storix Cloudflare DNS Manager")
    parser.add_argument("action", choices=["status", "sync", "clean"], help="Action to execute")
    parser.add_argument("--env", default="dev", help="Target environment (default: dev)")
    parser.add_argument("--zone", default="png261.dev", help="Cloudflare root zone (default: png261.dev)")
    parser.add_argument("--token", default=os.environ.get("CLOUDFLARE_API_TOKEN"), help="Cloudflare API Token")
    args = parser.parse_args()

    if args.action == "status":
        alb, cf = get_aws_endpoints(args.env)
        print(f"ALB: {alb}\nCloudFront: {cf}")
    elif args.action == "sync":
        sync_records(args.env, args.zone, args.token)
    elif args.action == "clean":
        clean_records(args.env, args.zone, args.token)


if __name__ == "__main__":
    main()
