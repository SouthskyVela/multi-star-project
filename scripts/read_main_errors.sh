#!/usr/bin/env bash
PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
set +e

export KUBECONFIG=$PROJECT/runtime/kubeconfig.yaml
for pod in main-sat-0 main-sat-1 main-sat-2; do
  echo "--- $pod ---"
  kubectl logs -n multi-star "$pod" --tail=180
done
