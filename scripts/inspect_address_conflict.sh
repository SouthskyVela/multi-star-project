#!/usr/bin/env bash
set +e

docker ps -a
docker network inspect --format '{{json .Containers}}' k3d-multi-star-sim
for name in k3d-multi-star-sim-server-0 k3d-multi-star-sim-agent-0 k3d-multi-star-sim-agent-1 k3d-multi-star-sim-agent-2 k3d-multi-star-sim-serverlb registry.localhost; do
  docker inspect --format '{{.Name}} state={{.State.Status}} ipam={{json .NetworkSettings.Networks}}' "$name"
done
