#!/usr/bin/env bash
set -euo pipefail

for name in k3d-multi-star-sim-server-0 k3d-multi-star-sim-agent-0 k3d-multi-star-sim-agent-1 k3d-multi-star-sim-agent-2; do
  echo "--- $name ---"
  docker exec "$name" cat /etc/rancher/k3s/registries.yaml
done
