#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUNTIME="$PROJECT/runtime"
LOG="$RUNTIME/results/resume-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$LOG") 2>&1

echo '=== Docker readiness ==='
curl --silent --show-error --fail --unix-socket /var/run/docker.sock \
  --retry 60 --retry-connrefused --retry-all-errors --retry-delay 2 --retry-max-time 120 \
  --connect-timeout 2 --max-time 5 "http://localhost/info" > /dev/null

echo '=== direct Docker container recovery ==='
for name in k3d-multi-star-sim-server-0 k3d-multi-star-sim-agent-0 k3d-multi-star-sim-agent-1 k3d-multi-star-sim-agent-2 k3d-multi-star-sim-serverlb registry.localhost; do
  status=$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || echo missing)
  echo "$name $status"
  if [[ $status != running ]]; then
    docker start "$name"
    status=$(docker inspect --format '{{.State.Status}}' "$name")
    if [[ $status != running ]]; then
      echo "$name did not reach running state" >&2
      exit 1
    fi
  fi
done

export KUBECONFIG="$RUNTIME/kubeconfig.yaml"
python3 "$PROJECT/scripts/wait_api.py" --timeout 600
echo
kubectl wait --for=condition=Ready nodes --all --timeout=180s
kubectl wait --for=condition=Ready pod -n kube-system -l k8s-app=kube-dns --timeout=180s
kubectl wait --for=condition=Ready pod -n kube-system -l k8s-app=metrics-server --timeout=180s
kubectl wait --for=condition=Ready pod -n kube-system -l app=local-path-provisioner --timeout=180s
kubectl get nodes -o wide
kubectl get pods -A -o wide

echo '=== storage and resources ==='
docker info --format 'DockerRootDir={{.DockerRootDir}} Driver={{.Driver}} Cgroup={{.CgroupVersion}}'
docker stats --no-stream

echo "RESUME_OK log=$LOG"
