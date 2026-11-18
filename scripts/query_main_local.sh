#!/usr/bin/env bash
set -euo pipefail
PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

export KUBECONFIG=$PROJECT/runtime/kubeconfig.yaml
for pod in main-sat-0 main-sat-1 main-sat-2; do
  base="http://$pod.main-sat.multi-star.svc.cluster.local:8081"
  echo "--- $pod status ---"
  kubectl exec -n multi-star small-sat-0 -- env TARGET_URL="$base/status" python -c 'import json,os,urllib.request; print(json.dumps(json.load(urllib.request.urlopen(os.environ["TARGET_URL"],timeout=10)),indent=2))'
  echo "--- $pod audit ---"
  kubectl exec -n multi-star small-sat-0 -- env TARGET_URL="$base/api/snapshot" python -c 'import json,os,urllib.request; d=json.load(urllib.request.urlopen(os.environ["TARGET_URL"],timeout=10)); print(json.dumps(d.get("events",[])[-20:],indent=2))'
done
