#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export KUBECONFIG="$PROJECT/runtime/kubeconfig.yaml"
LOG="$PROJECT/runtime/results/inspect-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$LOG") 2>&1

kubectl get nodes -o wide
kubectl describe nodes
kubectl get pods -A -o wide
kubectl describe pods -n kube-system
kubectl get events -A --sort-by=.lastTimestamp

echo "INSPECT_OK log=$LOG"
