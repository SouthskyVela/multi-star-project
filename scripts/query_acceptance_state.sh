#!/usr/bin/env bash
set -euo pipefail
PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

export KUBECONFIG=$PROJECT/runtime/kubeconfig.yaml
for pod in small-sat-7 small-sat-8; do
  kubectl exec -n multi-star small-sat-0 -- env TARGET="http://$pod.small-sat.multi-star.svc.cluster.local:8080/status" python -c 'import json,os,urllib.request; d=json.load(urllib.request.urlopen(os.environ["TARGET"],timeout=10)); print(json.dumps({"id":d["satellite_id"],"health":d["health"],"highest_epoch":d["highest_epoch"],"highest_plan_version":d["highest_plan_version"],"current_command_id":d["current_command_id"],"task_states":{k:v["state"] for k,v in [(t["command"]["command_id"],t) for t in d["tasks"]]}},indent=2))'
done
kubectl exec -n multi-star small-sat-0 -- python -c 'import json,urllib.request; d=json.load(urllib.request.urlopen("http://dashboard.multi-star.svc.cluster.local:8082/api/snapshot",timeout=15)); print(json.dumps({"leader":d["leader"],"mode":d["mode"],"plan_version":d["plan_version"],"metrics":d["metrics"],"small_satellites":d["small_satellites"],"events":d["events"][-12:]},indent=2))'
