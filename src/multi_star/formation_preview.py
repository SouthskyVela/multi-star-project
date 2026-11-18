"""Generate a reproducible formation / uv / PSF comparison figure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .uv import baseline_vectors, dirty_beam, generate_formation, project_baselines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--satellites", type=int, default=9)
    parser.add_argument("--radius-m", type=float, default=5000.0)
    parser.add_argument("--frequency-hz", type=float, default=100_000_000.0)
    parser.add_argument("--seed", type=int, default=20261118)
    args = parser.parse_args()

    shapes = ("ring", "y", "spiral")
    source = np.array([0.2, -0.1, 1.0])
    positions = [generate_formation(shape, args.satellites, args.radius_m, seed=args.seed) for shape in shapes]
    uv_sets = [project_baselines(baseline_vectors(p), args.frequency_hz, source)[1] for p in positions]
    max_uv = float(max(np.max(np.abs(uv[:, :2])) for uv in uv_sets) * 1.05)

    figure = plt.figure(figsize=(15, 12), facecolor="#11151c", constrained_layout=True)
    figure.suptitle(
        f"Deep-space v0 | {args.frequency_hz / 1e6:.0f} MHz | {args.satellites} small satellites | no main-satellite baselines",
        color="#e6edf3", fontsize=15,
    )
    records = {}
    for row, (shape, xyz, uv) in enumerate(zip(shapes, positions, uv_sets)):
        psf, metrics = dirty_beam(uv, 128, max_uv, backend="numpy", return_metrics=True)
        records[shape] = metrics

        ax_xyz = figure.add_subplot(3, 3, row * 3 + 1)
        ax_xyz.set_facecolor("#11151c")
        iso_x = (xyz[:, 0] - xyz[:, 1]) * np.cos(np.pi / 6)
        iso_y = xyz[:, 2] + (xyz[:, 0] + xyz[:, 1]) * np.sin(np.pi / 6)
        ax_xyz.scatter(iso_x, iso_y, c=xyz[:, 2], cmap="viridis", s=48)
        for index in range(xyz.shape[0]):
            ax_xyz.text(iso_x[index], iso_y[index], f"{index}", color="#e6edf3", fontsize=8)
        ax_xyz.set_title(f"{shape.upper()} | N={args.satellites}, baselines={len(baseline_vectors(xyz))}", color="#e6edf3")
        ax_xyz.set_xlabel("Isometric projected X (m)", color="#b4c2d0")
        ax_xyz.set_ylabel("Projected Y + Z (m); color = Z", color="#b4c2d0")
        ax_xyz.tick_params(colors="#b4c2d0", labelsize=8)
        ax_xyz.set_aspect("equal", adjustable="box")
        ax_xyz.grid(color="#3a4352", linewidth=0.4, alpha=0.5)

        ax_uv = figure.add_subplot(3, 3, row * 3 + 2)
        ax_uv.set_facecolor("#171b23")
        uv_display = np.concatenate((uv[:, :2], -uv[:, :2]), axis=0)
        ax_uv.scatter(uv_display[:, 0], uv_display[:, 1], s=15, c="#85b7eb", alpha=0.85)
        ax_uv.set_title("Conjugate uv sampling", color="#e6edf3")
        ax_uv.set_xlabel("u (wavelengths)", color="#b4c2d0")
        ax_uv.set_ylabel("v (wavelengths)", color="#b4c2d0")
        ax_uv.set_aspect("equal", adjustable="box")
        ax_uv.tick_params(colors="#b4c2d0", labelsize=8)
        ax_uv.grid(color="#3a4352", linewidth=0.4, alpha=0.5)

        ax_psf = figure.add_subplot(3, 3, row * 3 + 3)
        image = ax_psf.imshow(psf, origin="lower", cmap="coolwarm", vmin=-1.0, vmax=1.0)
        ax_psf.set_title("Dirty beam / PSF", color="#e6edf3")
        ax_psf.tick_params(colors="#b4c2d0", labelsize=8)
        ax_psf.set_xlabel("Image pixel", color="#b4c2d0")
        ax_psf.set_ylabel("Image pixel", color="#b4c2d0")
        ax_psf.text(
            0.03, 0.03,
            f"grid coverage={metrics['coverage_fraction']:.3f}\npeak sidelobe={metrics['sidelobe_peak']:.3f}\nFWHM area={metrics['main_lobe_fwhm_area_pixels']} px",
            transform=ax_psf.transAxes, color="#e6edf3", fontsize=9,
            bbox={"facecolor": "#11151c", "edgecolor": "#3a4352", "alpha": 0.85},
        )
        colorbar = figure.colorbar(image, ax=ax_psf, fraction=0.046, pad=0.04)
        colorbar.ax.tick_params(colors="#b4c2d0", labelsize=8)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, dpi=180, facecolor=figure.get_facecolor())
    plt.close(figure)
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"image": str(args.output), "metrics": str(args.metrics), "max_uv_lambda": max_uv}))


if __name__ == "__main__":
    main()
