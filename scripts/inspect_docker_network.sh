#!/usr/bin/env bash
set +e

echo '=== containers ==='
docker ps -a

echo '=== Docker networks ==='
docker network ls
docker network inspect k3d-multi-star-sim

echo '=== k3d container network settings ==='
for name in k3d-multi-star-sim-server-0 k3d-multi-star-sim-agent-0 k3d-multi-star-sim-agent-1 k3d-multi-star-sim-agent-2 k3d-multi-star-sim-serverlb registry.localhost; do
  echo "--- $name ---"
  docker inspect --format '{{json .NetworkSettings}}' "$name"
done

echo '=== recent server log ==='
docker logs --tail 80 k3d-multi-star-sim-server-0 2>&1
