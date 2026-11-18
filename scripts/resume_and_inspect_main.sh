#!/usr/bin/env bash
set -u
PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

bash $PROJECT/scripts/start_containers_direct.sh || true
bash $PROJECT/scripts/inspect_main.sh
