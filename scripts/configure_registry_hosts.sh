#!/usr/bin/env bash
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
  echo '必须以 root 运行' >&2
  exit 1
fi

cp -n /etc/hosts /etc/hosts.pre-multi-star
if ! getent hosts registry.localhost >/dev/null 2>&1; then
  echo '127.0.0.1 registry.localhost' >> /etc/hosts
fi
cat > /etc/wsl.conf <<'EOF'
[boot]
systemd=true

[user]
default=msim

[network]
generateHosts=false
EOF
getent hosts registry.localhost
