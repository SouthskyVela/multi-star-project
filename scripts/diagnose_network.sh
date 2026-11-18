#!/usr/bin/env bash
set +e

echo '=== DNS ==='
getent ahosts registry-1.docker.io

echo '=== WSL gateway ==='
gateway=$(ip route show default | cut -d' ' -f3)
echo "$gateway"

echo '=== direct registry HTTPS ==='
curl --head --connect-timeout 8 --max-time 15 "https://registry-1.docker.io/v2/" 2>&1

echo '=== Windows proxy through WSL gateway ==='
curl --head --connect-timeout 8 --max-time 15 --proxy "http://$gateway:7890" "https://registry-1.docker.io/v2/" 2>&1

echo '=== proxy TCP port ==='
timeout 8 bash -c "</dev/tcp/$gateway/7890" 2>&1

echo '=== direct HTTPS with DoH-provided addresses ==='
for ip in 52.20.61.205 52.20.47.70 44.197.32.100 3.232.125.55 54.84.13.204; do
  echo "--- $ip ---"
  curl --head --silent --show-error --connect-timeout 5 --max-time 10 --resolve "registry-1.docker.io:443:$ip" "https://registry-1.docker.io/v2/" 2>&1
done
