#!/usr/bin/env bash
set -euo pipefail
PROJECT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

export PYTHONPATH=$PROJECT/src
export OPENBLAS_NUM_THREADS=1
RESULTS=$PROJECT/runtime/results
nvidia-smi
python3 -m multi_star.benchmark --backend numpy --formations 128 --satellites 9 --image-size 128 --seed 20261118 --output "$RESULTS/benchmark-numpy.json"
XLA_PYTHON_CLIENT_MEM_FRACTION=0.70 JAX_PLATFORMS=cuda /home/uvela/venvs/nanograv/bin/python -m multi_star.benchmark --backend jax --formations 128 --satellites 9 --image-size 128 --seed 20261118 --output "$RESULTS/benchmark-jax.json"
