#!/usr/bin/env bash
PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
set +e

export KUBECONFIG=$PROJECT/runtime/kubeconfig.yaml
kubectl get statefulset -n multi-star small-sat -o jsonpath='{.status}'
echo
kubectl get statefulset -n multi-star main-sat -o jsonpath='{.status}'
echo
kubectl get pods -n multi-star -o wide
