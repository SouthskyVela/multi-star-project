#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUNTIME="$PROJECT/runtime"
IMAGE=registry.localhost:5001/multi-star-main:0.3.2
export KUBECONFIG="$RUNTIME/kubeconfig.yaml"
LOG="$RUNTIME/results/deploy-main-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee "$LOG") 2>&1

echo '=== storage guard ==='
if [[ $(docker info --format '{{.DockerRootDir}}') != /var/lib/docker ]]; then
  echo 'Docker root is outside the dedicated VHDX layout' >&2
  exit 1
fi

echo '=== build and push main image ==='
if [[ ${SKIP_BUILD:-0} != 1 ]]; then
  docker build --file "$PROJECT/deploy/docker/main-satellite.Dockerfile" --tag "$IMAGE" "$PROJECT"
fi
docker push "$IMAGE"

echo '=== deploy three main satellites ==='
kubectl apply -f "$PROJECT/deploy/kubernetes/main-satellites.yaml"
kubectl rollout status statefulset/main-sat -n multi-star --timeout=240s
kubectl wait --for=condition=Ready pod -n multi-star -l app=main-sat --timeout=180s
kubectl get pods -n multi-star -o wide
kubectl get pvc -n multi-star
kubectl get lease -n multi-star multi-star-control -o wide

echo '=== deploy leader-discovering dashboard proxy ==='
kubectl apply -f "$PROJECT/deploy/kubernetes/dashboard.yaml"
kubectl rollout status deployment/dashboard -n multi-star --timeout=180s
kubectl wait --for=condition=Ready pod -n multi-star -l app=dashboard --timeout=120s
kubectl get pods -n multi-star -l app=dashboard -o wide

echo '=== query active leader and real snapshot through dashboard proxy ==='
kubectl exec -n multi-star small-sat-0 -- python -c 'import json,urllib.request; d=json.load(urllib.request.urlopen("http://dashboard.multi-star.svc.cluster.local:8082/api/snapshot",timeout=15)); print(json.dumps({"leader":d["leader"],"mode":d["mode"],"plan_version":d["plan_version"],"small_satellites":len(d["small_satellites"]),"baseline_count":d["metrics"].get("baseline_count")},indent=2))'

echo "DEPLOY_MAIN_OK log=$LOG"
