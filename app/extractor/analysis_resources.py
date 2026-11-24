"""Bound native pools before importing numerical libraries in analysis workers.

Defaults match the full-demo equivalence/memory qualification. Explicit user
environment overrides are retained. This changes concurrency, never sampling.
"""
import os


def configure_native_threads(environ=None, cpus=None):
    environ = os.environ if environ is None else environ
    cpus = max(1, (os.cpu_count() or 1) if cpus is None else cpus)
    defaults = {'RAYON_NUM_THREADS': str(min(8, cpus)),
                'POLARS_MAX_THREADS': str(min(4, cpus)),
                'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
    for key, value in defaults.items():
        environ.setdefault(key, value)
    return {key: environ[key] for key in defaults}
