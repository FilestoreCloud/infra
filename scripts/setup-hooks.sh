#!/usr/bin/env bash
# ==============================================================================
# Helper to initialize and activate .githook from repository scripts
# ==============================================================================

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
"$ROOT_DIR/.githook/setup.sh"
