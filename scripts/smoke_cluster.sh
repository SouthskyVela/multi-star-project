#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUNTIME="$PROJECT/runtime"
CLUSTER=multi-star-sim
KUBECONFIG_PATH="$RUNTIME/kubeconfig.yaml"
LOG="$RUNTIME/results/smoke-$(date -u +%Y%m%dT%H%M%SZ).log"

exec > >(tee "$LOG") 2>&1

if [[ $(id -un) != msim ]]; then
  echo '请以 msim 用户运行，避免使用 root 创建集群' >&2
  exit 1
fi
if [[ $(stat -fc %T /sys/fs/cgroup) != cgroup2fs ]]; then
  echo '需要 cgroup v2' >&2
  exit 1
fi

echo '=== versions ==='
k3d version
kubectl version --client
docker version

echo '=== storage proof ==='
docker_root=$(docker info --format '{{.DockerRootDir}}')
if [[ $docker_root != /var/lib/docker ]]; then
  echo "意外 DockerRootDir：$docker_root" >&2
  exit 1
fi
findmnt -T "$docker_root" -o TARGET,SOURCE,FSTYPE
df -h "$docker_root"

echo '=== Docker smoke test ==='
docker run --rm hello-world

echo '=== create k3d cluster ==='
k3d cluster create --config "$PROJECT/deploy/k3d/cluster.yaml"
k3d kubeconfig get "$CLUSTER" > "$KUBECONFIG_PATH.tmp"
mv "$KUBECONFIG_PATH.tmp" "$KUBECONFIG_PATH"
export KUBECONFIG="$KUBECONFIG_PATH"
kubectl wait --for=condition=Ready nodes --all --timeout=180s
kubectl wait --for=condition=Ready pod -n kube-system -l k8s-app=kube-dns --timeout=180s
kubectl wait --for=condition=Ready pod -n kube-system -l k8s-app=metrics-server --timeout=180s
kubectl wait --for=condition=Ready pod -n kube-system -l app=local-path-provisioner --timeout=180s
kubectl get nodes -o wide --show-labels
kubectl get pods -A -o wide

echo '=== cluster and resource snapshot ==='
k3d cluster list
k3d node list
docker stats --no-stream
docker info --format 'DockerRootDir={{.DockerRootDir}} Driver={{.Driver}} Cgroup={{.CgroupVersion}} CPUs={{.NCPU}} Memory={{.MemTotal}}'

echo "SMOKE_OK log=$LOG kubeconfig=$KUBECONFIG_PATH"
