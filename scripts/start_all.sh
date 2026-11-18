#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export KUBECONFIG="$PROJECT/runtime/kubeconfig.yaml"
bash "$PROJECT/scripts/start_containers_direct.sh"
kubectl wait --for=condition=Available deployment/dashboard -n multi-star --timeout=180s
python3 "$PROJECT/scripts/reconcile_unknown_pods.py" --namespace multi-star
kubectl rollout status statefulset/main-sat -n multi-star --timeout=300s
python3 "$PROJECT/scripts/wait_small_satellites.py" --namespace multi-star --count 9 --timeout 300

if ! systemctl is-active --quiet multi-star-dashboard-forward.service; then
  echo 'dashboard 转发服务未运行；请检查 multi-star-dashboard-forward.service' >&2
  systemctl status multi-star-dashboard-forward.service --no-pager || true
  exit 1
fi
curl --fail --silent --show-error --connect-timeout 5 --max-time 20 "http://127.0.0.1:18082/healthz" > /dev/null
python3 - <<'PY'
import json
import urllib.request
with urllib.request.urlopen('http://127.0.0.1:18082/api/snapshot', timeout=20) as response:
    data = json.load(response)
print(json.dumps({
    'leader': data['leader'],
    'mode': data['mode'],
    'plan_version': data['plan_version'],
    'small_satellites': len(data['small_satellites']),
    'baseline_count': data['metrics'].get('baseline_count'),
}, ensure_ascii=False, indent=2))
PY

date -u +%Y-%m-%dT%H:%M:%SZ > "$PROJECT/runtime/results/last-start.txt"
echo 'START_OK'
echo '面板地址: http://127.0.0.1:18082'
echo '保持此控制台开启；关闭请使用项目根目录 stop.cmd。'
