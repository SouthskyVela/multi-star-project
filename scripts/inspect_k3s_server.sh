#!/usr/bin/env bash
set +e

echo '=== containers ==='
docker ps -a
echo '=== K3s server log tail ==='
docker logs --tail 200 k3d-multi-star-sim-server-0 2>&1
echo '=== listening ports ==='
ss -lntp
