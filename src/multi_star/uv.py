"""Three-dimensional formations, far-field uv sampling, and dirty beams."""

from __future__ import annotations

from collections import deque
from numbers import Integral

import numpy as np

from .backends import get_backend, to_numpy

SPEED_OF_LIGHT_M_S = 299_792_458.0
DEFAULT_SATELLITE_COUNT = 9
_FORMATIONS = {"ring", "y", "spiral"}


def _satellite_count(value: int) -> int:
    if not isinstance(value, Integral) or isinstance(value, bool):
        raise TypeError("n_satellites must be an integer")
    count = int(value)
    if count < 2:
        raise ValueError("n_satellites must be at least 2")
    return count


def _image_size(value: int) -> int:
    if not isinstance(value, Integral) or isinstance(value, bool):
        raise TypeError("image_size must be an integer")
    size = int(value)
    if size < 4:
        raise ValueError("image_size must be at least 4")
    return size


def _positive_finite(value: float, name: str) -> float:
    result = float(value)
    if not np.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


def generate_formation(
    formation: str = "ring",
    n_satellites: int = DEFAULT_SATELLITE_COUNT,
    radius_m: float = 1000.0,
    *,
    vertical_scale_m: float | None = None,
    seed: int = 0,
) -> np.ndarray:
    """Generate a non-coincident ring, three-arm Y, or spiral formation.

    The coordinates are three-dimensional and centered near the origin.  The
    seed controls a common rotation about z, not the number of satellites.
    """
    kind = formation.lower()
    if kind not in _FORMATIONS:
        raise ValueError(f"Unknown formation {formation!r}; choose ring, y, or spiral")
    count = _satellite_count(n_satellites)
    radius = _positive_finite(radius_m, "radius_m")
    height = radius * 0.1 if vertical_scale_m is None else float(vertical_scale_m)
    if not np.isfinite(height):
        raise ValueError("vertical_scale_m must be finite")
    phase = np.random.default_rng(seed).uniform(0.0, 2.0 * np.pi)

    if kind == "ring":
        index = np.arange(count, dtype=np.float64)
        theta = 2.0 * np.pi * index / count + phase
        positions = np.column_stack(
            (radius * np.cos(theta), radius * np.sin(theta),
             height * np.sin(2.0 * theta + 0.37))
        )
    elif kind == "spiral":
        index = np.arange(count, dtype=np.float64)
        theta = 4.0 * np.pi * index / count + phase
        radial = radius * (index + 1.0) / count
        positions = np.column_stack(
            (radial * np.cos(theta), radial * np.sin(theta),
             height * (radial / radius) * np.sin(theta))
        )
    else:
        positions = np.zeros((count, 3), dtype=np.float64)
        levels = (count - 1 + 2) // 3
        for index in range(1, count):
            arm = (index - 1) % 3
            level = (index - 1) // 3 + 1
            theta = np.pi / 2.0 + arm * 2.0 * np.pi / 3.0 + phase
            radial = radius * level / levels
            positions[index] = (
                radial * np.cos(theta),
                radial * np.sin(theta),
                height * (level / levels) * np.sin(theta + 0.5 * arm),
            )

    ii, jj = np.triu_indices(count, 1)
    separations = np.linalg.norm(positions[ii] - positions[jj], axis=1)
    if np.any(separations <= np.finfo(np.float64).eps * radius):
        raise RuntimeError("Formation generation produced coincident satellites")
    return positions


def baseline_vectors(positions, *, return_indices: bool = False):
    """Return the N(N-1)/2 unique baselines for i<j, in metres."""
    array = np.asarray(positions, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 3 or array.shape[0] < 2:
        raise ValueError("positions must have shape (N, 3), with N >= 2")
    if not np.all(np.isfinite(array)):
        raise ValueError("positions must contain only finite values")
    ii, jj = np.triu_indices(array.shape[0], 1)
    baselines = array[jj] - array[ii]
    if return_indices:
        return baselines, np.column_stack((ii, jj))
    return baselines


def projection_matrix(source_unit) -> np.ndarray:
    """Return orthonormal u/v/w row axes for a far-field source direction."""
    source = np.asarray(source_unit, dtype=np.float64)
    if source.shape != (3,) or not np.all(np.isfinite(source)):
        raise ValueError("source_unit must be a finite three-vector")
    norm = np.linalg.norm(source)
    if norm == 0.0:
        raise ValueError("source_unit must not be the zero vector")
    w_axis = source / norm
    reference = np.array([0.0, 0.0, 1.0])
    if abs(np.dot(reference, w_axis)) > 0.95:
        reference = np.array([1.0, 0.0, 0.0])
    u_axis = np.cross(reference, w_axis)
    u_axis /= np.linalg.norm(u_axis)
    v_axis = np.cross(w_axis, u_axis)
    return np.stack((u_axis, v_axis, w_axis))


def project_baselines(
    baselines_m,
    frequency_hz: float,
    source_unit,
    *,
    return_conjugate: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Project far-field baselines onto orthogonal u/v/w axes.

    Returns ``(uvw_m, uv_lambda)``.  No near-field curvature or Fresnel
    approximation is applied.  With ``return_conjugate``, the second half of
    each output is the negative of the first half for display or gridding.
    """
    baselines = np.asarray(baselines_m, dtype=np.float64)
    if baselines.ndim != 2 or baselines.shape[1] != 3:
        raise ValueError("baselines_m must have shape (N(N-1)/2, 3)")
    if not np.all(np.isfinite(baselines)):
        raise ValueError("baselines_m must contain only finite values")
    frequency = _positive_finite(frequency_hz, "frequency_hz")
    uvw_m = baselines @ projection_matrix(source_unit).T
    uv_lambda = uvw_m * (frequency / SPEED_OF_LIGHT_M_S)
    if return_conjugate:
        uvw_m = np.concatenate((uvw_m, -uvw_m), axis=0)
        uv_lambda = np.concatenate((uv_lambda, -uv_lambda), axis=0)
    return uvw_m, uv_lambda


def _validated_uv(xp, uv_lambda):
    uv = xp.asarray(uv_lambda, dtype=xp.float64)
    if uv.ndim not in (2, 3) or uv.shape[-1] not in (2, 3):
        raise ValueError("uv_lambda must have shape (M, 3) or (B, M, 3)")
    if uv.shape[-2] < 1 or (uv.ndim == 3 and uv.shape[0] < 1):
        raise ValueError("at least one uv sample is required")
    if not bool(xp.all(xp.isfinite(uv))):
        raise ValueError("uv_lambda must contain only finite values")
    return uv[..., :2]


def _batch_psf_from_uv(xp, uv, image_size: int, max_uv_lambda: float):
    """Grid B batches at once using offset bincount and a batched inverse FFT."""
    if uv.ndim == 2:
        uv = uv[xp.newaxis, :, :]
    batch_count = uv.shape[0]
    conjugate = xp.concatenate((uv, -uv), axis=1)
    limit = max_uv_lambda
    tolerance = limit * 1.0e-12 + 1.0e-12
    if bool(xp.any(xp.abs(conjugate) > limit + tolerance)):
        raise ValueError("uv samples exceed max_uv_lambda; increase the uv extent")

    # FFT samples are periodic.  A modulo grid keeps +/-uv at exact Hermitian
    # partner pixels for both odd and even image sizes, including the edges.
    scale = image_size / (2.0 * limit)
    indices = (xp.rint(conjugate * scale) + image_size // 2).astype(xp.int64)
    indices = xp.mod(indices, image_size)
    flat_index = indices[..., 1] * image_size + indices[..., 0]
    offsets = xp.arange(batch_count, dtype=xp.int64)[:, xp.newaxis]
    flat_index = flat_index + offsets * (image_size * image_size)
    histogram = xp.bincount(
        flat_index.reshape(-1), minlength=batch_count * image_size * image_size
    ).reshape(batch_count, image_size, image_size).astype(xp.float64)

    shifted = xp.fft.ifftshift(histogram, axes=(-2, -1))
    psf = xp.fft.fftshift(
        xp.fft.ifft2(shifted, axes=(-2, -1)), axes=(-2, -1)
    ).real
    peaks = xp.max(xp.abs(psf), axis=(-2, -1), keepdims=True)
    if bool(xp.any(peaks <= 0.0)):
        raise RuntimeError("Dirty beam normalization failed because its peak is zero")
    return psf / peaks


def dirty_beam(
    uv_lambda,
    image_size: int = 256,
    max_uv_lambda: float = 1000.0,
    *,
    backend: str = "auto",
    return_metrics: bool = False,
):
    """Compute a nearest-neighbour, conjugate-symmetric, peak-normalized PSF."""
    size = _image_size(image_size)
    limit = _positive_finite(max_uv_lambda, "max_uv_lambda")
    xp = get_backend(backend)
    uv = _validated_uv(xp, uv_lambda)
    if uv.ndim != 2:
        raise ValueError("dirty_beam expects one uv array with shape (M, 3)")
    psf = _batch_psf_from_uv(xp, uv, size, limit)[0]
    if return_metrics:
        metrics = psf_metrics(to_numpy(uv), to_numpy(psf), limit)
        return psf, metrics
    return psf


def batch_dirty_beams(
    positions,
    frequency_hz: float,
    source_unit,
    image_size: int = 256,
    max_uv_lambda: float = 1000.0,
    *,
    backend: str = "auto",
):
    """Compute B independent dirty beams without a Python loop over batches.

    ``positions`` has shape ``(B, N, 3)``.  Baseline construction, conjugate
    gridding with batch-offset ``bincount``, normalization, and the inverse FFT
    are all batched in the selected array backend.
    """
    size = _image_size(image_size)
    limit = _positive_finite(max_uv_lambda, "max_uv_lambda")
    frequency = _positive_finite(frequency_hz, "frequency_hz")
    xp = get_backend(backend)
    array = xp.asarray(positions, dtype=xp.float64)
    if array.ndim != 3 or array.shape[-1] != 3 or array.shape[0] < 1 or array.shape[1] < 2:
        raise ValueError("positions must have shape (B, N, 3), with B >= 1 and N >= 2")
    if not bool(xp.all(xp.isfinite(array))):
        raise ValueError("positions must contain only finite values")

    ii_np, jj_np = np.triu_indices(array.shape[1], 1)
    ii = xp.asarray(ii_np)
    jj = xp.asarray(jj_np)
    baselines = array[:, jj, :] - array[:, ii, :]
    axes = xp.asarray(projection_matrix(source_unit), dtype=xp.float64)
    uvw_m = xp.einsum("bmk,lk->bml", baselines, axes)
    uv_lambda = uvw_m[..., :2] * (frequency / SPEED_OF_LIGHT_M_S)
    return _batch_psf_from_uv(xp, uv_lambda, size, limit)


def _coverage_histogram(uv: np.ndarray, image_size: int, max_uv_lambda: float):
    conjugate = np.concatenate((uv[:, :2], -uv[:, :2]), axis=0)
    scale = image_size / (2.0 * max_uv_lambda)
    indices = (np.rint(conjugate * scale) + image_size // 2).astype(np.int64)
    indices = np.mod(indices, image_size)
    flat = indices[:, 1] * image_size + indices[:, 0]
    return np.bincount(flat, minlength=image_size * image_size).reshape(
        image_size, image_size
    )


def _main_lobe_mask(psf: np.ndarray) -> np.ndarray:
    center = (psf.shape[0] // 2, psf.shape[1] // 2)
    threshold = 0.5 * psf[center]
    mask = np.zeros(psf.shape, dtype=bool)
    queue = deque([center])
    mask[center] = True
    while queue:
        row, column = queue.popleft()
        for neighbor in ((row - 1, column), (row + 1, column),
                         (row, column - 1), (row, column + 1)):
            nr, nc = neighbor
            if (0 <= nr < psf.shape[0] and 0 <= nc < psf.shape[1]
                    and not mask[nr, nc] and psf[nr, nc] >= threshold):
                mask[nr, nc] = True
                queue.append(neighbor)
    return mask


def psf_metrics(uv_lambda, psf, max_uv_lambda: float) -> dict:
    """Measure uv coverage, the central hole, sidelobes, and FWHM main-lobe area."""
    uv = np.asarray(uv_lambda, dtype=np.float64)
    image = np.asarray(psf, dtype=np.float64)
    if uv.ndim != 2 or uv.shape[1] not in (2, 3) or uv.shape[0] < 1:
        raise ValueError("uv_lambda must have shape (M, 3) or (M, 2)")
    if image.ndim != 2 or image.shape[0] != image.shape[1] or image.shape[0] < 4:
        raise ValueError("psf must be a square 2-D array with size at least 4")
    if not np.all(np.isfinite(uv)) or not np.all(np.isfinite(image)):
        raise ValueError("uv_lambda and psf must contain only finite values")
    limit = _positive_finite(max_uv_lambda, "max_uv_lambda")
    if np.any(np.abs(uv[:, :2]) > limit * (1.0 + 1.0e-12) + 1.0e-12):
        raise ValueError("uv samples exceed max_uv_lambda")

    size = image.shape[0]
    histogram = _coverage_histogram(uv, size, limit)
    sampled = histogram > 0
    radii = np.linalg.norm(uv[:, :2], axis=1)
    nonzero_radii = radii[radii > 0.0]
    radial_limit = np.sqrt(2.0) * limit
    radial_bin_count = max(8, min(64, size // 4))
    radial_edges = np.linspace(0.0, radial_limit, radial_bin_count + 1)
    radial_hist, _ = np.histogram(np.concatenate((radii, radii)), bins=radial_edges)

    conjugate_uv = np.concatenate((uv[:, :2], -uv[:, :2]), axis=0)
    angles = np.mod(np.arctan2(conjugate_uv[:, 1], conjugate_uv[:, 0]), 2.0 * np.pi)
    angular_bin_count = 36
    angular_hist, _ = np.histogram(
        angles, bins=np.linspace(0.0, 2.0 * np.pi, angular_bin_count + 1)
    )

    center = (size // 2, size // 2)
    if image[center] <= 0.0:
        raise ValueError("psf must have a positive central peak")
    main_lobe = _main_lobe_mask(image)
    sidelobes = image[~main_lobe]
    pixel_scale_rad = 1.0 / (2.0 * limit)
    area_pixels = int(main_lobe.sum())
    area_sr = float(area_pixels * pixel_scale_rad**2)

    return {
        "baseline_count": int(uv.shape[0]),
        "conjugate_sample_count": int(2 * uv.shape[0]),
        "image_size": size,
        "sampled_cells": int(sampled.sum()),
        "total_cells": int(size * size),
        "coverage_fraction": float(sampled.mean()),
        "radial_coverage": float(np.count_nonzero(radial_hist) / radial_bin_count),
        "radial_bin_count": radial_bin_count,
        "radial_occupancy": radial_hist.astype(bool).astype(int).tolist(),
        "angular_coverage": float(np.count_nonzero(angular_hist) / angular_bin_count),
        "angular_bin_count": angular_bin_count,
        "angular_occupancy": angular_hist.astype(bool).astype(int).tolist(),
        "uv_min_radius_lambda": float(radii.min()),
        "uv_max_radius_lambda": float(radii.max()),
        "center_hole_radius_lambda": (
            float(nonzero_radii.min()) if nonzero_radii.size else None
        ),
        "psf_peak": float(image[center]),
        "sidelobe_peak": float(np.max(np.abs(sidelobes))) if sidelobes.size else 0.0,
        "sidelobe_rms": (
            float(np.sqrt(np.mean(sidelobes**2))) if sidelobes.size else 0.0
        ),
        "main_lobe_fwhm_area_pixels": area_pixels,
        "main_lobe_fwhm_area_sr": area_sr,
        "main_lobe_fwhm_equivalent_radius_rad": float(np.sqrt(area_sr / np.pi)),
        "image_pixel_scale_rad": float(pixel_scale_rad),
    }
