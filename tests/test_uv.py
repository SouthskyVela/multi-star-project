"""Unit tests for formation uv sampling and batched dirty beams."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import numpy as np

from multi_star.backends import get_backend
from multi_star.benchmark import main as benchmark_main
from multi_star.uv import (
    SPEED_OF_LIGHT_M_S,
    baseline_vectors,
    batch_dirty_beams,
    dirty_beam,
    generate_formation,
    project_baselines,
    projection_matrix,
    psf_metrics,
)


class FormationTests(unittest.TestCase):
    def test_configurable_formations_have_unique_three_dimensional_positions(self):
        for kind in ("ring", "y", "spiral"):
            for count in (2, 5, 9, 14):
                with self.subTest(kind=kind, count=count):
                    positions = generate_formation(kind, count, seed=4)
                    self.assertEqual(positions.shape, (count, 3))
                    self.assertTrue(np.all(np.isfinite(positions)))
                    ii, jj = np.triu_indices(count, 1)
                    distances = np.linalg.norm(positions[ii] - positions[jj], axis=1)
                    self.assertTrue(np.all(distances > 0.0))
                    self.assertTrue(np.any(np.abs(positions[:, 2]) > 0.0))

    def test_seed_is_reproducible_and_count_is_not_fixed(self):
        first = generate_formation("spiral", 11, seed=123)
        second = generate_formation("spiral", 11, seed=123)
        np.testing.assert_array_equal(first, second)
        self.assertNotEqual(generate_formation("ring", 10).shape[0], 9)

    def test_invalid_formations_and_counts(self):
        with self.assertRaises(ValueError):
            generate_formation("triangle")
        with self.assertRaises(ValueError):
            generate_formation("ring", 1)


class BaselineProjectionTests(unittest.TestCase):
    def test_unique_baseline_count_and_order(self):
        for count in (2, 3, 9, 12):
            positions = generate_formation("ring", count)
            baselines, indices = baseline_vectors(positions, return_indices=True)
            self.assertEqual(baselines.shape, (count * (count - 1) // 2, 3))
            ii, jj = np.triu_indices(count, 1)
            np.testing.assert_array_equal(indices, np.column_stack((ii, jj)))
            np.testing.assert_allclose(baselines, positions[jj] - positions[ii])
            self.assertTrue(np.all(indices[:, 0] < indices[:, 1]))

    def test_projection_is_orthonormal_and_w_points_to_source(self):
        for source in ([0.0, 0.0, 2.0], [0.2, -0.4, 1.0], [1.0, 0.0, 0.0]):
            axes = projection_matrix(source)
            np.testing.assert_allclose(axes @ axes.T, np.eye(3), atol=1.0e-14)
            normalized = np.asarray(source, dtype=float) / np.linalg.norm(source)
            np.testing.assert_allclose(axes[2], normalized, atol=1.0e-14)

    def test_uvw_reconstructs_baselines_and_lambda_scaling(self):
        positions = generate_formation("y", 8)
        baselines = baseline_vectors(positions)
        source = np.array([0.3, -0.2, 0.7])
        axes = projection_matrix(source)
        frequency = 137_000_000.0
        uvw_m, uv_lambda = project_baselines(baselines, frequency, source)
        np.testing.assert_allclose(uvw_m @ axes, baselines, atol=1.0e-10)
        np.testing.assert_allclose(
            uv_lambda, uvw_m * frequency / SPEED_OF_LIGHT_M_S, rtol=1.0e-14
        )

    def test_optional_conjugate_points(self):
        baselines = baseline_vectors(generate_formation("spiral", 6))
        uvw, uv = project_baselines(
            baselines, 100_000_000.0, [0.1, 0.2, 1.0], return_conjugate=True
        )
        count = baselines.shape[0]
        self.assertEqual(uvw.shape, (2 * count, 3))
        self.assertEqual(uv.shape, (2 * count, 3))
        np.testing.assert_array_equal(uvw[count:], -uvw[:count])
        np.testing.assert_array_equal(uv[count:], -uv[:count])


class DirtyBeamTests(unittest.TestCase):
    @staticmethod
    def _uv_for(positions, frequency=100_000_000.0):
        baselines = baseline_vectors(positions)
        return project_baselines(baselines, frequency, [0.2, -0.1, 1.0])[1]

    def test_grid_psf_is_conjugate_symmetric_and_peak_normalized(self):
        positions = generate_formation("ring", 7, radius_m=500.0)
        uv = self._uv_for(positions)
        limit = float(np.max(np.abs(uv[:, :2])) * 1.01)
        psf = dirty_beam(uv, image_size=48, max_uv_lambda=limit, backend="numpy")
        self.assertEqual(psf.shape, (48, 48))
        self.assertTrue(np.all(np.isfinite(psf)))
        # On an even FFT grid the Nyquist row/column is self-conjugate, so
        # point reflection is reverse followed by a one-pixel periodic roll.
        expected = np.roll(psf[::-1, ::-1], (1, 1), axis=(0, 1))
        np.testing.assert_allclose(psf, expected, atol=2.0e-14)
        self.assertAlmostEqual(float(np.max(np.abs(psf))), 1.0, places=14)
        self.assertAlmostEqual(float(psf[24, 24]), 1.0, places=14)

    def test_metrics_include_coverage_hole_sidelobes_and_fwhm_area(self):
        uv = self._uv_for(generate_formation("spiral", 10))
        limit = float(np.max(np.abs(uv[:, :2])) * 1.05)
        psf, metrics = dirty_beam(
            uv, 64, limit, backend="numpy", return_metrics=True
        )
        direct = psf_metrics(uv, psf, limit)
        self.assertEqual(metrics, direct)
        self.assertGreater(metrics["coverage_fraction"], 0.0)
        self.assertLessEqual(metrics["coverage_fraction"], 1.0)
        self.assertGreaterEqual(metrics["radial_coverage"], 0.0)
        self.assertLessEqual(metrics["radial_coverage"], 1.0)
        self.assertGreater(metrics["angular_coverage"], 0.0)
        self.assertGreater(metrics["center_hole_radius_lambda"], 0.0)
        self.assertAlmostEqual(metrics["psf_peak"], 1.0, places=14)
        self.assertGreaterEqual(metrics["sidelobe_peak"], 0.0)
        self.assertGreaterEqual(metrics["sidelobe_rms"], 0.0)
        self.assertGreaterEqual(metrics["main_lobe_fwhm_area_pixels"], 1)
        self.assertGreater(metrics["main_lobe_fwhm_area_sr"], 0.0)
        self.assertEqual(metrics["baseline_count"], 45)

    def test_uv_outside_grid_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "max_uv_lambda"):
            dirty_beam([[2000.0, 0.0, 0.0]], 32, 1000.0, backend="numpy")


class BatchTests(unittest.TestCase):
    def test_small_numpy_batch_matches_single_beams(self):
        positions = np.stack(
            [generate_formation(kind, 5, radius_m=700.0, seed=3)
             for kind in ("ring", "y", "spiral")]
        )
        frequency = 80_000_000.0
        source = [0.2, -0.1, 1.0]
        ii, jj = np.triu_indices(5, 1)
        maximum = np.max(np.linalg.norm(positions[:, jj] - positions[:, ii], axis=-1))
        limit = float(maximum * frequency / SPEED_OF_LIGHT_M_S * 1.05)
        batch = batch_dirty_beams(
            positions, frequency, source, 40, limit, backend="numpy"
        )
        self.assertEqual(batch.shape, (3, 40, 40))
        self.assertTrue(np.all(np.isfinite(batch)))
        expected = np.roll(batch[:, ::-1, ::-1], (1, 1), axis=(1, 2))
        np.testing.assert_allclose(batch, expected, atol=2.0e-14)
        np.testing.assert_allclose(np.max(np.abs(batch), axis=(-2, -1)), 1.0)
        for index in range(positions.shape[0]):
            uv = DirtyBeamTests._uv_for(positions[index], frequency)
            single = dirty_beam(uv, 40, limit, backend="numpy")
            np.testing.assert_allclose(batch[index], single, atol=2.0e-14)

    def test_invalid_backend_and_absent_cupy(self):
        with self.assertRaises(ValueError):
            get_backend("opencl")
        positions = np.stack(
            [generate_formation("ring", 4), generate_formation("y", 4)]
        )
        with self.assertRaises(ValueError):
            batch_dirty_beams(positions, 1.0e8, [0, 0, 1], 32, 1000, backend="cuda")

        with patch(
            "multi_star.backends.importlib.import_module",
            side_effect=ModuleNotFoundError("No module named 'cupy'"),
        ):
            self.assertIs(get_backend("auto"), np)
            with self.assertRaisesRegex(RuntimeError, "CuPy backend"):
                get_backend("cupy")

    def test_auto_falls_back_when_cuda_device_is_unavailable(self):
        with patch(
            "multi_star.backends.importlib.import_module"
        ) as import_module:
            runtime = import_module.return_value.cuda.runtime
            runtime.getDeviceCount.side_effect = RuntimeError("cudaErrorNoDevice")
            self.assertIs(get_backend("auto"), np)
            with self.assertRaisesRegex(RuntimeError, "no usable CUDA device"):
                get_backend("cupy")

            runtime.getDeviceCount.side_effect = None
            runtime.getDeviceCount.return_value = 0
            self.assertIs(get_backend("auto"), np)
            with self.assertRaisesRegex(RuntimeError, "no usable CUDA device"):
                get_backend("cupy")


class BenchmarkTests(unittest.TestCase):
    def test_json_benchmark_writes_only_explicit_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = benchmark_main([
                    "--backend", "numpy", "--formations", "2", "--shapes", "ring,y",
                    "--satellites", "4", "--image-size", "32", "--seed", "7",
                    "--output", str(output),
                ])
            parsed_stdout = json.loads(stdout.getvalue())
            parsed_file = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["backend"], "numpy")
            self.assertEqual(result["psf_shape"], [2, 32, 32])
            self.assertEqual(result["formation_count"], 2)
            self.assertEqual(result["shapes"], ["ring", "y"])
            self.assertNotIn("formations", result)
            self.assertTrue(result["psf_finite"])
            self.assertGreater(result["elapsed_seconds"], 0.0)
            self.assertGreater(result["formations_per_second"], 0.0)
            self.assertEqual(parsed_stdout, result)
            self.assertEqual(parsed_file, result)


if __name__ == "__main__":
    unittest.main()
