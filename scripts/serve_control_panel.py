#!/usr/bin/env python3
"""
Local Control Panel Server
Serves static control-panel UI and routes /api calls to tenant_operator_lambda
using AWS credentials from profile 'handon'.
"""

import json
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Ensure infra/modules/06-control-plane is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTROL_PLANE_DIR = os.path.join(PROJECT_ROOT, "infra", "modules", "06-control-plane")
sys.path.insert(0, CONTROL_PLANE_DIR)

# Set AWS environment for boto3
os.environ["AWS_PROFILE"] = "handon"
os.environ["AWS_REGION"] = "ap-southeast-1"
os.environ["ENVIRONMENT_NAME"] = "prod"
os.environ["TABLE_NAME"] = "prod-nextcloud-tenant-registry"
os.environ["CLUSTER_NAME"] = "prod-nextcloud-cluster"

import tenant_operator_lambda

PORT = int(os.environ.get("PORT", 8080))
DIST_DIR = os.path.join(PROJECT_ROOT, "control-panel", "dist")
CONTROL_PANEL_DIR = (
    DIST_DIR
    if os.path.exists(os.path.join(DIST_DIR, "index.html"))
    else os.path.join(PROJECT_ROOT, "control-panel")
)


class ControlPanelHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=CONTROL_PANEL_DIR, **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api"):
            self.handle_api("GET", parsed)
        else:
            local_path = os.path.join(CONTROL_PANEL_DIR, parsed.path.lstrip("/"))
            if not os.path.exists(local_path) or os.path.isdir(local_path):
                if not parsed.path.startswith("/assets/"):
                    self.path = "/index.html"
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api") or parsed.path == "/":
            self.handle_api("POST", parsed)
        else:
            self.send_error(404, "Not Found")

    def handle_api(self, method, parsed):
        query_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        body = None
        if method == "POST":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                raw_body = self.rfile.read(content_length).decode("utf-8")
                try:
                    body = json.loads(raw_body)
                except Exception:
                    body = raw_body

        headers_dict = dict(self.headers)
        if "Accept" not in headers_dict and "accept" not in headers_dict:
            headers_dict["Accept"] = "application/json"
        if "format" not in query_params:
            query_params["format"] = "json"

        event = {
            "httpMethod": method,
            "headers": headers_dict,
            "queryStringParameters": query_params,
            "body": (
                body if isinstance(body, str) else json.dumps(body) if body else None
            ),
        }
        if isinstance(body, dict):
            event.update(body)

        try:
            resp = tenant_operator_lambda.lambda_handler(event, None)
            status_code = resp.get("statusCode", 200)
            headers = resp.get("headers", {})
            resp_body = resp.get("body", "")

            self.send_response(status_code)
            for k, v in headers.items():
                self.send_header(k, v)
            if "Content-Type" not in headers:
                self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(resp_body.encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))


if __name__ == "__main__":
    print(f"🚀 Starting Control Panel server on http://localhost:{PORT}")
    server = HTTPServer(("0.0.0.0", PORT), ControlPanelHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.server_close()
