"""Array-backend selection with an optional, lazily imported CuPy backend."""

from __future__ import annotations

import importlib
from types import ModuleType

import numpy as np


_VALID_BACKENDS = {"auto", "numpy", "cupy", "jax"}


def _cuda_unavailable(name: str, exc: Exception) -> ModuleType:
    if name == "auto":
        return np
    raise RuntimeError(
        "CuPy backend was requested, but no usable CUDA device is available. "
        "Use backend='numpy' or repair the CUDA/CuPy environment."
    ) from exc


def get_backend(name: str = "auto") -> ModuleType:
    """Return NumPy or CuPy; auto also verifies that a CUDA device is usable."""
    if name not in _VALID_BACKENDS:
        choices = ", ".join(sorted(_VALID_BACKENDS))
        raise ValueError(f"Unknown backend {name!r}; expected one of: {choices}")
    if name == "numpy":
        return np
    if name == "jax":
        try:
            jax = importlib.import_module("jax")
            jax.config.update("jax_enable_x64", True)
            if not any(device.platform == "gpu" for device in jax.devices()):
                raise RuntimeError("JAX reports no GPU device")
            return importlib.import_module("jax.numpy")
        except (ImportError, ModuleNotFoundError, RuntimeError) as exc:
            raise RuntimeError(
                "JAX GPU backend was requested, but JAX with a usable GPU is unavailable."
            ) from exc
    try:
        cupy = importlib.import_module("cupy")
    except (ImportError, ModuleNotFoundError) as exc:
        if name == "auto":
            return np
        raise RuntimeError(
            "CuPy backend was requested, but CuPy could not be imported. "
            "Use backend='numpy' or install a compatible CuPy build."
        ) from exc
    try:
        count = int(cupy.cuda.runtime.getDeviceCount())
    except Exception as exc:
        return _cuda_unavailable(name, exc)
    if count < 1:
        return _cuda_unavailable(name, RuntimeError("getDeviceCount returned zero"))
    return cupy


def backend_name(xp: ModuleType) -> str:
    """Return the public backend name for a resolved array module."""
    return "cupy" if xp.__name__ == "cupy" else "jax" if xp.__name__ == "jax.numpy" else "numpy"


def to_numpy(value):
    """Copy a backend array to NumPy without requiring CuPy for NumPy inputs."""
    if isinstance(value, np.ndarray):
        return value
    if hasattr(value, "get"):
        return value.get()
    return np.asarray(value)


def synchronize(xp: ModuleType) -> None:
    """Synchronize CUDA work for timing; NumPy execution is already synchronous."""
    if backend_name(xp) == "cupy":
        xp.cuda.runtime.deviceSynchronize()
    elif backend_name(xp) == "jax":
        importlib.import_module("jax").effects_barrier()
