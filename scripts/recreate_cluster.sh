#!/usr/bin/env bash
set -euo pipefail
PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

exists=false
while read -r name _; do
  if [[ $name == multi-star-sim ]]; then
    exists=true
  fi
done < <(k3d cluster list --no-headers)
if [[ $exists == true ]]; then
  k3d cluster delete multi-star-sim
fi

exec bash $PROJECT/scripts/smoke_cluster.sh
