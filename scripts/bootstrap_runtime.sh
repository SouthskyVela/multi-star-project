#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
DOWNLOADS="$PROJECT/runtime/downloads"
USER_NAME=msim

if [[ $(id -u) -ne 0 ]]; then
  echo '必须以 root 在 multi-star-sim 内运行' >&2
  exit 1
fi

if [[ ! -f /etc/os-release ]]; then
  echo '无法识别 Linux 系统' >&2
  exit 1
fi
. /etc/os-release
if [[ ${ID:-} != ubuntu || ${VERSION_ID:-} != 24.04 ]]; then
  echo "仅允许在专用 Ubuntu 24.04 环境执行，当前为 ${ID:-unknown} ${VERSION_ID:-unknown}" >&2
  exit 1
fi

for path in "$DOWNLOADS/k3d-linux-amd64" "$DOWNLOADS/k3d-checksums.txt" "$DOWNLOADS/kubectl" "$DOWNLOADS/kubectl-v1.37.2.sha256"; do
  if [[ ! -f $path ]]; then
    echo "缺少已下载文件：$path" >&2
    exit 1
  fi
done

cd "$DOWNLOADS"
expected_k3d=
while read -r checksum asset; do
  if [[ $asset == _dist/k3d-linux-amd64 ]]; then
    expected_k3d=$checksum
  fi
done < k3d-checksums.txt
actual_k3d=$(sha256sum k3d-linux-amd64 | cut -d' ' -f1)
if [[ -z $expected_k3d || $actual_k3d != "$expected_k3d" ]]; then
  echo 'k3d SHA-256 校验失败' >&2
  exit 1
fi
expected_kubectl=$(tr -d '[:space:]' < kubectl-v1.37.2.sha256)
actual_kubectl=$(sha256sum kubectl | cut -d' ' -f1)
if [[ $actual_kubectl != "$expected_kubectl" ]]; then
  echo 'kubectl SHA-256 校验失败' >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl jq python3 python3-venv docker.io docker-buildx

install -m 0755 "$DOWNLOADS/k3d-linux-amd64" /usr/local/bin/k3d
install -m 0755 "$DOWNLOADS/kubectl" /usr/local/bin/kubectl

if ! id -u "$USER_NAME" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$USER_NAME"
fi
usermod -aG sudo,docker "$USER_NAME"

cat > /etc/wsl.conf <<'EOF'
[boot]
systemd=true

[user]
default=msim

[network]
generateHosts=false
EOF
cp -n /etc/hosts /etc/hosts.pre-multi-star 2>/dev/null || true
if ! getent hosts registry.localhost >/dev/null 2>&1; then
  echo '127.0.0.1 registry.localhost' >> /etc/hosts
fi

install -d -m 0755 /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{
  "data-root": "/var/lib/docker",
  "registry-mirrors": ["https://docker.m.daocloud.io"],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "25m",
    "max-file": "3"
  }
}
EOF

systemctl enable docker.service containerd.service

printf '\nBootstrap complete. Docker root: /var/lib/docker (inside this dedicated VHDX).\n'
printf 'Restart only multi-star-sim before running smoke_cluster.sh as msim.\n'
