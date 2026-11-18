#!/usr/bin/env bash
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
  echo '必须以 root 运行' >&2
  exit 1
fi
if [[ ! -f /etc/docker/daemon.json ]]; then
  echo '缺少专用 Docker 配置' >&2
  exit 1
fi

jq '. + {"registry-mirrors": ["https://docker.m.daocloud.io"]}' /etc/docker/daemon.json > /etc/docker/daemon.json.tmp
mv /etc/docker/daemon.json.tmp /etc/docker/daemon.json
systemctl restart docker.service
docker info --format 'DockerRootDir={{.DockerRootDir}} Mirrors={{json .RegistryConfig.Mirrors}}'
