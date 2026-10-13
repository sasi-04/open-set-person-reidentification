"""
Measuring speed and memory honestly.

In plain words: we never quote a latency we have not measured on the machine
running the code. This module measures the embedding backbone in steady state
(after warm-up), reports the usual percentiles, and reads the process's peak
memory from the operating system. Model-loading and warm-up time are reported
separately because they happen once, not per request.
"""

from __future__ import annotations

import os
import platform
import time

import numpy as np
import psutil
import torch


def peak_memory_mb() -> float | None:
    """Peak resident memory of this process in MB (Windows: peak working set)."""
    info = psutil.Process(os.getpid()).memory_info()
    peak = getattr(info, "peak_wset", None) or getattr(info, "rss", None)
    return None if peak is None else round(peak / 2**20, 1)


def percentiles(values_ms: list[float]) -> dict:
    if not values_ms:
        return {"n": 0}
    data = np.asarray(values_ms)
    return {
        "n": int(len(data)),
        "mean": round(float(data.mean()), 2),
        "p50": round(float(np.percentile(data, 50)), 2),
        "p95": round(float(np.percentile(data, 95)), 2),
        "p99": round(float(np.percentile(data, 99)), 2),
        "min": round(float(data.min()), 2),
        "max": round(float(data.max()), 2),
    }


def measure_embedding_latency(extractor, crops: list[np.ndarray], *, single_runs: int = 30, batch_size: int = 16) -> dict:
    """Latency of embedding ONE crop at a time, and throughput for a batch, after warm-up."""
    crops = [c for c in crops if c is not None]
    if not crops:
        return {}
    for crop in crops[:3]:  # warm-up calls are excluded from the statistics
        extractor.embed([crop])

    single = []
    for i in range(single_runs):
        began = time.perf_counter()
        extractor.embed([crops[i % len(crops)]])
        single.append((time.perf_counter() - began) * 1000)

    batch = [crops[i % len(crops)] for i in range(batch_size)]
    extractor.embed(batch)  # warm the batch shape
    began = time.perf_counter()
    for _ in range(3):
        extractor.embed(batch)
    per_batch = (time.perf_counter() - began) / 3

    return {
        "single_crop_ms": percentiles(single),
        "batch": {
            "batch_size": batch_size,
            "ms_per_crop": round(per_batch / batch_size * 1000, 2),
            "throughput_crops_per_second": round(batch_size / per_batch, 2),
        },
    }


def environment_info() -> dict:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "numpy": np.__version__,
        "cpu_count": os.cpu_count(),
        "torch_threads": torch.get_num_threads(),
        "total_memory_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "peak_memory_mb": peak_memory_mb(),
    }
