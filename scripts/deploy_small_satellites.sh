#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUNTIME="$PROJECT/runtime"
IMAGE=registry.localhost:5001/multi-star-satellite:0.2.0
export KUBECONFIG="$RUNTIME/kubeconfig.yaml"
LOG="$RUNTIME/results/deploy-small-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$LOG") 2>&1

echo '=== storage guard ==='
docker info --format 'DockerRootDir={{.DockerRootDir}}'
if [[ $(docker info --format '{{.DockerRootDir}}') != /var/lib/docker ]]; then
  echo 'Docker root is outside the dedicated VHDX layout' >&2
  exit 1
fi

echo '=== build and push satellite image ==='
if [[ ${SKIP_BUILD:-0} != 1 ]]; then
  docker build --file "$PROJECT/deploy/docker/small-satellite.Dockerfile" --tag "$IMAGE" "$PROJECT"
else
  echo 'Skipping build because the identical image was already built.'
fi
docker push "$IMAGE"

echo '=== deploy nine stable small satellites ==='
kubectl apply -f "$PROJECT/deploy/kubernetes/small-satellites.yaml"
kubectl rollout status statefulset/small-sat -n multi-star --timeout=240s
kubectl wait --for=condition=Ready pod -n multi-star -l app=small-sat --timeout=180s
kubectl get pods -n multi-star -o wide
kubectl get pvc -n multi-star

echo '=== query every satellite status endpoint ==='
for ordinal in 0 1 2 3 4 5 6 7 8; do
  kubectl exec -n multi-star "small-sat-$ordinal" -- python -c 'import json,urllib.request; d=json.load(urllib.request.urlopen("http://127.0.0.1:8080/status")); print(d["satellite_id"],d["health"],d["position_m"])'
done

echo "DEPLOY_SMALL_OK log=$LOG"
