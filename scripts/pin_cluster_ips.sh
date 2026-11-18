#!/usr/bin/env bash
set -euo pipefail
PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

NETWORK=k3d-multi-star-sim
export KUBECONFIG=$PROJECT/runtime/kubeconfig.yaml

pin() {
  local name=$1
  local ip=$2
  echo "Pinning $name to $ip"
  docker network disconnect --force "$NETWORK" "$name" 2>/dev/null || true
  docker network connect --ip "$ip" "$NETWORK" "$name"
}

pin k3d-multi-star-sim-agent-2 172.45.0.13
pin k3d-multi-star-sim-agent-0 172.45.0.11
pin k3d-multi-star-sim-agent-1 172.45.0.12
pin k3d-multi-star-sim-serverlb 172.45.0.14
pin registry.localhost 172.45.0.15

if [[ $(docker inspect --format '{{.State.Status}}' k3d-multi-star-sim-server-0) != running ]]; then
  docker start k3d-multi-star-sim-server-0
fi

docker restart k3d-multi-star-sim-agent-0 k3d-multi-star-sim-agent-1 k3d-multi-star-sim-agent-2
docker restart k3d-multi-star-sim-serverlb registry.localhost

echo '=== fixed addresses ==='
for name in k3d-multi-star-sim-server-0 k3d-multi-star-sim-agent-0 k3d-multi-star-sim-agent-1 k3d-multi-star-sim-agent-2 k3d-multi-star-sim-serverlb registry.localhost; do
  docker inspect --format '{{.Name}} {{json .NetworkSettings.Networks}}' "$name"
done

curl --silent --show-error --insecure --output /dev/null \
  --retry 90 --retry-connrefused --retry-all-errors --retry-delay 2 --retry-max-time 240 \
  --connect-timeout 3 --max-time 5 "https://127.0.0.1:6443/readyz"
kubectl wait --for=condition=Ready nodes --all --timeout=180s
kubectl wait --for=condition=Ready pod -n kube-system -l k8s-app=kube-dns --timeout=180s
kubectl wait --for=condition=Ready pod -n kube-system -l k8s-app=metrics-server --timeout=180s
kubectl wait --for=condition=Ready pod -n kube-system -l app=local-path-provisioner --timeout=180s
kubectl get nodes -o wide
kubectl get pods -A -o wide

echo 'PIN_AND_RECOVERY_OK'
