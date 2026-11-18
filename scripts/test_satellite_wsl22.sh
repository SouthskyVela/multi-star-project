#!/usr/bin/env bash
set -euo pipefail
PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

export PYTHONPATH=$PROJECT/src
export OPENBLAS_NUM_THREADS=1
python3 -m unittest discover -s $PROJECT/tests -p 'test*satellite*.py' -v
