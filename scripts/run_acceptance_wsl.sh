#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export KUBECONFIG="$PROJECT/runtime/kubeconfig.yaml"
REPORT="$PROJECT/runtime/results/acceptance-$(date -u +%Y%m%dT%H%M%SZ).json"

kubectl cp "$PROJECT/scripts/e2e_acceptance.py" multi-star/small-sat-0:/tmp/e2e_acceptance.py
kubectl exec -n multi-star small-sat-0 -- python /tmp/e2e_acceptance.py | tee "$REPORT"
cp "$REPORT" "$PROJECT/runtime/results/acceptance-latest.json"
python3 -m json.tool "$REPORT" > /dev/null
echo "ACCEPTANCE_OK report=$REPORT"
