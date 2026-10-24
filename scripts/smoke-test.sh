#!/usr/bin/env bash
# Read-only health check of the lab. Never changes the cluster.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/demo.sh" preflight "$@"
