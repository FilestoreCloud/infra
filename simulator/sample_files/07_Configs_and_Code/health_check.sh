#!/usr/bin/env bash
set -euo pipefail

echo "==> Checking Storix Container Health Status..."
STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/status.php || echo "000")

if [ "$STATUS_CODE" -eq 200 ]; then
    echo "✓ Nextcloud container status: HEALTHY (200 OK)"
    exit 0
else
    echo "✗ Nextcloud health check failed with HTTP: $STATUS_CODE"
    exit 1
fi
