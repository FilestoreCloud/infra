#!/usr/bin/env python3
"""
Storix Cloudflare DNS & Auto-Subdomain Lifecycle Manager
=========================================================
Automatically discovers ALB & CloudFront endpoints from AWS CloudFormation
and configures/cleans DNS records and Origin Rules on Cloudflare.

Usage:
    python3 manage_dns.py audit  --env prod --zone png261.dev [--token <CF_TOKEN>]
    python3 manage_dns.py sync   --env prod --zone png261.dev [--token <CF_TOKEN>]
    python3 manage_dns.py clean  --env prod --zone png261.dev [--token <CF_TOKEN>]
"""

import argparse
from collections import defaultdict
import json
import os
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
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"[ERROR] Cloudflare API {method} {path} failed: {e.code} - {err_body}")
        try:
            return json.loads(err_body)
        except Exception:
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


def audit_zone(env: str, zone_name: str, token: str | None = None):
    """Audit all Cloudflare DNS records, Origin Rules, and AWS endpoints."""
    alb_dns, cf_domain = get_aws_endpoints(env)
    print("\n" + "=" * 70)
    print(f"🔍 STORIX CLOUDFLARE & AWS DNS AUDIT REPORT (Env: {env})")
    print("=" * 70)
    print(f"  • Active AWS ALB DNS:            {alb_dns or 'NOT_DEPLOYED'}")
    print(f"  • Active AWS CloudFront Domain:  {cf_domain or 'NOT_DEPLOYED'}")
    print(f"  • Root Zone Domain:              {zone_name}")
    print("=" * 70)

    if not token:
        print("\n[ERROR] CLOUDFLARE_API_TOKEN is required for audit.")
        return

    zone_id = get_zone_id(zone_name, token)
    if not zone_id:
        print(f"[ERROR] Zone {zone_name} not found with provided token.")
        return

    print(f"\n[Zone ID]: {zone_id}")

    # 1. Fetch DNS records
    dns_res = cf_request("GET", f"/zones/{zone_id}/dns_records?per_page=100", token)
    records = dns_res.get("result", []) if dns_res else []
    print(f"\n📋 [DNS Records in Zone ({len(records)} found)]:")
    print(f"  {'TYPE':<6} {'NAME':<30} {'CONTENT':<45} {'PROXIED':<8} {'ID'}")
    print("  " + "-" * 115)
    for r in records:
        prox = "YES" if r.get("proxied") else "NO"
        print(f"  {r.get('type'):<6} {r.get('name'):<30} {r.get('content'):<45} {prox:<8} {r.get('id')}")

    # 2. Fetch Page Rules
    pr_res = cf_request("GET", f"/zones/{zone_id}/pagerules", token)
    page_rules = pr_res.get("result", []) if pr_res and pr_res.get("result") else []
    print(f"\n📜 [Cloudflare Page Rules ({len(page_rules)} found)]:")
    for pr in page_rules:
        targets = [t.get("constraint", {}).get("value") for t in pr.get("targets", [])]
        actions = [a.get("id") for a in pr.get("actions", [])]
        print(f"  • Targets: {targets} | Actions: {actions} | Status: {pr.get('status')}")

    # 3. Fetch Worker Routes
    wr_res = cf_request("GET", f"/zones/{zone_id}/workers/routes", token)
    worker_routes = wr_res.get("result", []) if wr_res and wr_res.get("result") else []
    print(f"\n⚡ [Cloudflare Worker Routes ({len(worker_routes)} found)]:")
    for wr in worker_routes:
        print(f"  • Pattern: {wr.get('pattern')} | Script: {wr.get('script')}")

    # 4. Fetch Custom Hostnames (SSL for SaaS)
    ch_res = cf_request("GET", f"/zones/{zone_id}/custom_hostnames", token)
    custom_hostnames = ch_res.get("result", []) if ch_res and ch_res.get("result") else []
    print(f"\n🌐 [Cloudflare Custom Hostnames ({len(custom_hostnames)} found)]:")
    for ch in custom_hostnames:
        print(f"  • Hostname: {ch.get('hostname')} | Origin: {ch.get('custom_origin_server')} | Status: {ch.get('status')}")

    # 5. Fetch Rulesets (all phases)
    rs_res = cf_request("GET", f"/zones/{zone_id}/rulesets", token)
    rulesets = rs_res.get("result", []) if rs_res and rs_res.get("result") else []
    print(f"\n⚙️ [Cloudflare Rulesets ({len(rulesets)} found)]:")
    for rs in rulesets:
        print(f"  • Name: {rs.get('name')} | Phase: {rs.get('phase')} | ID: {rs.get('id')}")
        # Fetch rules in this ruleset if authorized
        try:
            r_detail = cf_request("GET", f"/zones/{zone_id}/rulesets/{rs.get('id')}", token)
            if r_detail and (r_detail.get("result") or {}).get("rules"):
                for rule in r_detail["result"]["rules"]:
                    print(f"    -> Rule: {rule.get('description')} | Action: {rule.get('action')} | Expression: {rule.get('expression')} | Params: {json.dumps(rule.get('action_parameters', {}))}")
        except Exception as e:
            print(f"    (Could not fetch ruleset detail: {e})")

    # 6. Fetch Origin Rules entrypoint specifically
    or_res = cf_request("GET", f"/zones/{zone_id}/rulesets/phases/http_request_origin/entrypoint", token)
    if or_res and (or_res.get("result") or {}).get("rules"):
        print(f"\n🎯 [Existing Origin Rules ({len(or_res['result']['rules'])} found)]:")
        for rule in or_res["result"]["rules"]:
            print(f"  • {rule.get('description')} | Expression: {rule.get('expression')} | Params: {json.dumps(rule.get('action_parameters', {}))}")
    elif or_res and or_res.get("result"):
        print(f"\n🎯 [Origin Rules Entrypoint Result]: {or_res['result']}")
    else:
        print(f"\n🎯 [Origin Rules Entrypoint]: None or {or_res.get('errors') if or_res else 'Empty'}")

    # 3. Detect Discrepancies
    print("\n🚨 [Discrepancy Analysis]:")
    admin_name = f"admin.{zone_name}"
    admin_recs = [r for r in records if r.get("name") == admin_name]
    if not admin_recs:
        print(f"  ⚠️ No DNS record for {admin_name}!")
    else:
        for ar in admin_recs:
            if cf_domain and ar.get("content") != cf_domain:
                print(f"  ❌ MISMATCH for {admin_name}: points to '{ar.get('content')}', expected '{cf_domain}'!")
            else:
                print(f"  ✅ {admin_name} DNS record matches CloudFront '{cf_domain}'.")

    wildcard_name = f"*.{zone_name}"
    wildcard_recs = [r for r in records if r.get("name") in [wildcard_name, f"\\*.{zone_name}"]]
    if not wildcard_recs:
        print(f"  ⚠️ No DNS record for {wildcard_name}!")
    else:
        for wr in wildcard_recs:
            if alb_dns and wr.get("content") != alb_dns:
                print(f"  ❌ MISMATCH for {wildcard_name}: points to '{wr.get('content')}', expected '{alb_dns}'!")
            else:
                print(f"  ✅ {wildcard_name} DNS record matches ALB '{alb_dns}'.")


def configure_origin_rules(zone_id: str, zone_name: str, cf_domain: str, token: str):
    """Ensure Cloudflare Origin Rules rewrite Host header for CloudFront and port 80 for ALB."""
    print("\n⚙️ Configuring Cloudflare Origin Rules...")
    admin_name = f"admin.{zone_name}"

    desired_rules = [
        {
            "description": f"Storix {admin_name} CloudFront Origin Route",
            "expression": f'(http.host eq "{admin_name}")',
            "action": "route",
            "action_parameters": {
                "origin": {
                    "host": cf_domain,
                    "port": 443,
                },
            },
            "enabled": True,
        },
        {
            "description": f"Storix Tenant Subdomains ALB Port 80 Route",
            "expression": f'(ends_with(http.host, ".{zone_name}") and http.host ne "{admin_name}")',
            "action": "route",
            "action_parameters": {
                "origin": {
                    "port": 80,
                },
            },
            "enabled": True,
        },
    ]

    payload = {"rules": desired_rules}
    res = cf_request("PUT", f"/zones/{zone_id}/rulesets/phases/http_request_origin/entrypoint", token, payload)
    if res and res.get("success"):
        print("  ✔ Successfully applied Cloudflare Origin Rules (Host Header override + ALB Port 80 route).")
    else:
        print(f"  ⚠️ Could not update Origin Rules (Token may lack Ruleset permissions): {res.get('errors') if res else 'Unknown'}")


def sync_records(env: str, zone_name: str, token: str | None = None):
    """Upsert CNAME records for Wildcard Tenants, SuperAdmin Console, and Apex domain."""
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
        {
            "name": zone_name,
            "type": "CNAME",
            "content": cf_domain,
            "proxied": True,
            "comment": f"storix-{env}-root-apex",
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

    # List ALL existing records
    existing = cf_request("GET", f"/zones/{zone_id}/dns_records?per_page=100", token)
    records_by_name = defaultdict(list)
    if existing and existing.get("result"):
        for rec in existing["result"]:
            records_by_name[rec["name"]].append(rec)

    for d in desired_records:
        if not d["content"]:
            print(f"[SKIP] Skipping {d['name']} because target endpoint is not available.")
            continue

        matching_recs = records_by_name.get(d["name"]) or records_by_name.get(f"\\*.{zone_name}", [])

        record_payload = {
            "type": d["type"],
            "name": d["name"],
            "content": d["content"],
            "ttl": 1,
            "proxied": d["proxied"],
            "comment": d["comment"],
        }

        if matching_recs:
            # Update the first matching record
            first_rec = matching_recs[0]
            rec_id = first_rec["id"]
            res = cf_request("PUT", f"/zones/{zone_id}/dns_records/{rec_id}", token, record_payload)
            if res and res.get("success"):
                print(f"  ✔ Updated: {d['name']} ➔ {d['content']}")
            else:
                print(f"  ❌ Update failed for {d['name']}: {res}")

            # Delete any duplicate / conflicting records with the same name
            for dup in matching_recs[1:]:
                dup_id = dup["id"]
                del_res = cf_request("DELETE", f"/zones/{zone_id}/dns_records/{dup_id}", token)
                if del_res and del_res.get("success"):
                    print(f"  🗑 Deleted duplicate/stale record for {d['name']} ({dup.get('content')}) [ID: {dup_id}]")
        else:
            res = cf_request("POST", f"/zones/{zone_id}/dns_records", token, record_payload)
            if res and res.get("success"):
                print(f"  ✔ Created: {d['name']} ➔ {d['content']}")
            else:
                print(f"  ❌ Creation failed for {d['name']}: {res}")

    # Configure Origin Rules if CloudFront endpoint exists
    if cf_domain:
        try:
            configure_origin_rules(zone_id, zone_name, cf_domain, token)
        except Exception as e:
            print(f"  [WARN] Origin rule configuration exception: {e}")


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
    parser.add_argument("action", choices=["status", "audit", "sync", "clean"], help="Action to execute")
    parser.add_argument("--env", default="dev", help="Target environment (default: dev)")
    parser.add_argument("--zone", default="png261.dev", help="Cloudflare root zone (default: png261.dev)")
    parser.add_argument("--token", default=os.environ.get("CLOUDFLARE_API_TOKEN"), help="Cloudflare API Token")
    args = parser.parse_args()

    if args.action == "status":
        alb, cf = get_aws_endpoints(args.env)
        print(f"ALB: {alb}\nCloudFront: {cf}")
    elif args.action == "audit":
        audit_zone(args.env, args.zone, args.token)
    elif args.action == "sync":
        sync_records(args.env, args.zone, args.token)
    elif args.action == "clean":
        clean_records(args.env, args.zone, args.token)


if __name__ == "__main__":
    main()
