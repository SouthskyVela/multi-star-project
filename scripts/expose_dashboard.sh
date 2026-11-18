#!/usr/bin/env bash
set -euo pipefail
PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

export KUBECONFIG=$PROJECT/runtime/kubeconfig.yaml
exec kubectl port-forward -n multi-star --address 127.0.0.1 service/dashboard 18082:8082
