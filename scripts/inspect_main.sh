#!/usr/bin/env bash
set +e

PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LOG="$PROJECT/runtime/results/main-inspect-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$LOG") 2>&1
export KUBECONFIG="$PROJECT/runtime/kubeconfig.yaml"
kubectl get pods -n multi-star -o wide --show-labels
kubectl get endpoints -n multi-star main-control -o yaml
kubectl get endpointslices -n multi-star -l kubernetes.io/service-name=main-control -o yaml
for name in main-sat-0 main-sat-1 main-sat-2; do
  echo "--- logs $name ---"
  kubectl logs -n multi-star "$name" --tail=100
done
echo "MAIN_INSPECT_LOG=$LOG"
