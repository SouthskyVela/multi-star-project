"""Command-line benchmark for batched formation dirty beams."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from .backends import backend_name, get_backend, synchronize, to_numpy
from .uv import SPEED_OF_LIGHT_M_S, batch_dirty_beams, generate_formation


def _formation_count(value: str) -> int:
    count = int(value)
    if count <= 0:
        raise argparse.ArgumentTypeError("--formations must be a positive integer")
    return count


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark genuinely batched ring/Y/spiral dirty-beam synthesis."
    )
    parser.add_argument("--backend", choices=("auto", "numpy", "cupy", "jax"), default="auto")
    parser.add_argument(
        "--formations", type=_formation_count, default=3,
        help="Number of distinct candidate formations to generate (default: 3)",
    )
    parser.add_argument(
        "--shapes", nargs="+", default=["ring", "y", "spiral"],
        help="Shape cycle, separated by spaces or commas (default: ring y spiral)",
    )
    parser.add_argument("--satellites", type=int, default=9)
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Optional JSON output path; no file is written unless this is supplied",
    )
    return parser


def _shape_names(values: list[str]) -> list[str]:
    names = [name.strip().lower() for value in values for name in value.split(",")]
    names = [name for name in names if name]
    if not names:
        raise ValueError("At least one shape is required")
    return names


def main(argv: list[str] | None = None) -> dict:
    """Run the benchmark, print measured JSON, and optionally save that JSON."""
    args = _parser().parse_args(argv)
    shapes = _shape_names(args.shapes)
    positions = np.stack([
        generate_formation(
            shapes[index % len(shapes)], args.satellites, seed=args.seed + index
        )
        for index in range(args.formations)
    ])
    frequency_hz = 100_000_000.0
    source_unit = np.array([0.2, -0.1, 1.0], dtype=np.float64)
    ii, jj = np.triu_indices(args.satellites, 1)
    maximum_baseline_m = float(
        np.max(np.linalg.norm(positions[:, jj, :] - positions[:, ii, :], axis=-1))
    )
    max_uv_lambda = max(
        10.0,
        float(np.ceil(1.05 * maximum_baseline_m * frequency_hz / SPEED_OF_LIGHT_M_S)),
    )

    if args.warmups < 0 or args.repeats < 1:
        raise ValueError("--warmups must be >=0 and --repeats must be positive")

    xp = get_backend(args.backend)
    synchronize(xp)
    psfs = None
    warmup_seconds = 0.0
    for _ in range(args.warmups):
        warmup_started = time.perf_counter()
        psfs = batch_dirty_beams(
            positions, frequency_hz, source_unit, args.image_size, max_uv_lambda,
            backend=args.backend,
        )
        synchronize(xp)
        warmup_seconds += time.perf_counter() - warmup_started
    iteration_seconds = []
    for _ in range(args.repeats):
        started = time.perf_counter()
        psfs = batch_dirty_beams(
            positions, frequency_hz, source_unit, args.image_size, max_uv_lambda,
            backend=args.backend,
        )
        synchronize(xp)
        iteration_seconds.append(time.perf_counter() - started)
    elapsed_seconds = float(sum(iteration_seconds) / len(iteration_seconds))

    host_psfs = to_numpy(psfs)
    result = {
        "requested_backend": args.backend,
        "backend": backend_name(xp),
        "timing_scope": "mean host-to-backend batch_dirty_beams call and synchronization after warmup",
        "warmup_seconds": float(warmup_seconds),
        "warmup_count": int(args.warmups),
        "repeat_count": int(args.repeats),
        "iteration_seconds": iteration_seconds,
        "elapsed_seconds": elapsed_seconds,
        "formations_per_second": float(args.formations / elapsed_seconds),
        "formation_count": int(args.formations),
        "shapes": shapes,
        "satellites": int(args.satellites),
        "image_size": int(args.image_size),
        "psf_shape": list(host_psfs.shape),
        "psf_dtype": str(host_psfs.dtype),
        "psf_finite": bool(np.all(np.isfinite(host_psfs))),
        "psf_peak_max_min": float(host_psfs.max(axis=(-2, -1)).min()),
        "psf_peak_max_max": float(host_psfs.max(axis=(-2, -1)).max()),
        "frequency_hz": frequency_hz,
        "source_unit": source_unit.tolist(),
        "max_uv_lambda": max_uv_lambda,
        "seed": int(args.seed),
    }
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return result


if __name__ == "__main__":
    main()
