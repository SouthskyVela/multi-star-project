#!/usr/bin/env bash
set -euo pipefail
PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

if [[ $(id -u) -ne 0 ]]; then
  echo '必须以 root 在 multi-star-sim 内运行' >&2
  exit 1
fi

cat > /etc/systemd/system/multi-star-dashboard-forward.service <<EOF
[Unit]
Description=Multi-Star dashboard kubectl port-forward
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=msim
Group=msim
Environment=HOME=/home/msim
Environment=KUBECONFIG=$PROJECT/runtime/kubeconfig.yaml
WorkingDirectory=$PROJECT
ExecStart=/usr/local/bin/kubectl port-forward -n multi-star --address 127.0.0.1 service/dashboard 18082:8082
Restart=always
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now multi-star-dashboard-forward.service
systemctl status multi-star-dashboard-forward.service --no-pager
