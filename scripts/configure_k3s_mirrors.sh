#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
for name in k3d-multi-star-sim-server-0 k3d-multi-star-sim-agent-0 k3d-multi-star-sim-agent-1 k3d-multi-star-sim-agent-2; do
  docker cp "$PROJECT/deploy/k3d/registries.yaml" "$name:/etc/rancher/k3s/registries.yaml"
  docker restart "$name"
done

exec bash "$PROJECT/scripts/start_containers_direct.sh"
