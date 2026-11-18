#!/usr/bin/env bash
set -euo pipefail

echo "multi-star-sim runtime keepalive started at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exec tail -f /dev/null
