#!/usr/bin/env bash
set +e

echo '=== system ==='
systemctl is-system-running
systemctl is-active docker.service containerd.service
systemctl --failed --no-pager

echo '=== containers ==='
docker ps -a
for id in $(docker ps -aq); do
  docker inspect --format '{{.Name}} status={{.State.Status}} running={{.State.Running}} exit={{.State.ExitCode}} error={{.State.Error}}' "$id"
done

echo '=== listening ports ==='
ss -lntp

echo '=== Docker log tail ==='
journalctl -b -u docker.service --no-pager -n 60

echo '=== K3s server log tail ==='
docker logs --tail 160 k3d-multi-star-sim-server-0 2>&1

echo '=== K3s agent log tails ==='
for name in k3d-multi-star-sim-agent-0 k3d-multi-star-sim-agent-1 k3d-multi-star-sim-agent-2; do
  echo "--- $name ---"
  docker logs --tail 80 "$name" 2>&1
done
