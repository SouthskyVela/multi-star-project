#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
systemctl stop multi-star-dashboard-forward.service || true
sync
date -u +%Y-%m-%dT%H:%M:%SZ > "$PROJECT/runtime/results/last-stop.txt"
echo 'STOP_OK: dashboard 转发已停止，multi-star-sim 即将由 stop.cmd 终止。'
echo '所有镜像、Pod 配置、PVC、VHDX 和验收数据均保留。'
