#!/usr/bin/env bash
set -euo pipefail
PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

export KUBECONFIG=$PROJECT/runtime/kubeconfig.yaml
kubectl exec -n multi-star main-sat-2 -- python -c 'import multi_star.main_satellite_service as m; print("module",m.__file__); print("has_command_dict",hasattr(m,"_command_dict")); print("has_event_mapper",hasattr(m,"_event_from_request"))'
kubectl exec -n multi-star main-sat-2 -- sha256sum /app/src/multi_star/main_satellite_service.py /usr/local/lib/python3.12/site-packages/multi_star/main_satellite_service.py
kubectl exec -n multi-star main-sat-2 -- tail -n 45 /usr/local/lib/python3.12/site-packages/multi_star/main_satellite_service.py
