#!/usr/bin/env bash
set -euo pipefail
PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

export PYTHONPATH=$PROJECT/src
export OPENBLAS_NUM_THREADS=1
python3 -m multi_star.formation_preview \
  --output $PROJECT/runtime/results/formation-preview.png \
  --metrics $PROJECT/runtime/results/formation-metrics.json \
  --satellites 9 --radius-m 5000 --frequency-hz 100000000 --seed 20261118
