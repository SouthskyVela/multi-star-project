#!/usr/bin/env bash
set -euo pipefail
PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

export KUBECONFIG=$PROJECT/runtime/kubeconfig.yaml
kubectl apply -f $PROJECT/deploy/kubernetes/small-satellites.yaml
kubectl apply -f $PROJECT/deploy/kubernetes/main-satellites.yaml
