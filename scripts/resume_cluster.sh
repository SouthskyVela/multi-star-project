#!/usr/bin/env bash
set -euo pipefail
PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

exec bash $PROJECT/scripts/start_containers_direct.sh
