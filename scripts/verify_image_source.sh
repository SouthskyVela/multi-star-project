#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export KUBECONFIG="$PROJECT/runtime/kubeconfig.yaml"
FILES=(backends.py benchmark.py coordinator.py dashboard_proxy.py formation_preview.py lease.py main_satellite_service.py satellite.py small_satellite_service.py upload.py uv.py static/dashboard.html static/test-events.csv)

for file in "${FILES[@]}"; do
  host_hash=$(sha256sum "$PROJECT/src/multi_star/$file" | cut -d' ' -f1)
  pod_hash=$(kubectl exec -n multi-star main-sat-0 -- sha256sum "/app/src/multi_star/$file" | cut -d' ' -f1)
  if [[ $host_hash != "$pod_hash" ]]; then
    echo "MISMATCH $file host=$host_hash pod=$pod_hash" >&2
    exit 1
  fi
  echo "MATCH $file $host_hash"
done

echo 'IMAGE_SOURCE_MATCH_OK'
