"""
Computing and caching embeddings for evaluation images.

In plain words: embedding thousands of benchmark images on a CPU takes minutes,
and an ablation study needs the SAME embeddings many times. So every embedding
is computed once and saved to disk, keyed by

    dataset + image path + file size + model weights fingerprint

Change the model (or the image) and the cache entry is simply not found, so a
stale number can never sneak into a result. Two flavours are stored side by
side: ``plain`` and ``mirrored`` (horizontally flipped). Flip test-time
augmentation is then ``normalise(plain + mirrored)`` - no extra model passes.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

from ..cv.embedding.extractor import OSNetExtractor
from ..cv.geometry import pad_to_person_aspect
from ..cv.imaging import load_rgb_file
from .datasets import ImageRecord

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]


class EvaluationCancelled(Exception):
    """Raised inside long loops when the user cancels a running job."""


def _cache_path(cache_dir: Path, dataset: str, extractor: OSNetExtractor, mirrored: bool) -> Path:
    safe_dataset = "".join(c if c.isalnum() or c in "-_" else "_" for c in dataset)
    kind = "mirrored" if mirrored else "plain"
    # Folded and un-folded networks agree to ~1e-6, but never mix them in one cache: reruns stay exactly reproducible.
    optimised = "f" if getattr(extractor, "optimisations", ()) else "n"
    return cache_dir / f"emb_{safe_dataset}_{extractor.name}_{extractor.weights_sha256[:12]}{optimised}_{kind}.npz"


def _key(record: ImageRecord, root: Path) -> str:
    relative = record.path.relative_to(root).as_posix() if record.path.is_relative_to(root) else record.path.name
    return f"{relative}|{record.path.stat().st_size}"


def normalise_rows(matrix: np.ndarray) -> np.ndarray:
    return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


def embed_records(
    records: list[ImageRecord],
    extractor: OSNetExtractor,
    *,
    cache_dir: Path,
    dataset: str,
    dataset_root: Path,
    mirrored: bool = False,
    progress: ProgressCallback | None = None,
    cancelled: Callable[[], bool] | None = None,
    timings: list[float] | None = None,
) -> np.ndarray:
    """Return an (N, D) matrix aligned with ``records``; only uncached images are run through the model.

    ``timings`` (optional) collects per-image model latency in milliseconds for the performance report.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = _cache_path(cache_dir, dataset, extractor, mirrored)
    cached: dict[str, np.ndarray] = {}
    if cache_file.is_file():
        try:
            with np.load(cache_file, allow_pickle=False) as stored:
                cached = dict(zip(stored["keys"].tolist(), stored["matrix"], strict=True))
        except (OSError, ValueError, KeyError):
            logger.warning("Embedding cache %s is unreadable; recomputing.", cache_file.name)

    keys = [_key(record, dataset_root) for record in records]
    missing = [i for i, key in enumerate(keys) if key not in cached]
    total = len(missing)
    logger.info("Embedding %d new images for %s (%d cached)", total, dataset, len(records) - total)

    batch = max(8, extractor.batch_size)
    done = 0
    for start in range(0, total, batch):
        if cancelled and cancelled():
            raise EvaluationCancelled()
        chunk = missing[start : start + batch]
        crops = [pad_to_person_aspect(load_rgb_file(records[i].path)) for i in chunk]
        began = time.perf_counter()
        vectors = extractor.embed_mirrored(crops) if mirrored else extractor.embed(crops)
        elapsed_ms = (time.perf_counter() - began) * 1000
        if timings is not None:
            timings.extend([elapsed_ms / len(chunk)] * len(chunk))
        for i, vector in zip(chunk, vectors, strict=True):
            cached[keys[i]] = vector
        done += len(chunk)
        if progress:
            progress(done, total)

    if total:
        _save_cache(cache_file, cached)
    return np.stack([cached[key] for key in keys]).astype(np.float32, copy=False)


def _save_cache(cache_file: Path, cached: dict[str, np.ndarray]) -> None:
    """Write via a temp file + rename so an interrupted run never leaves a half-written cache."""
    temporary = cache_file.with_name(cache_file.name + ".tmp.npz")
    np.savez(temporary, keys=np.array(list(cached), dtype=str), matrix=np.stack(list(cached.values())))
    os.replace(temporary, cache_file)
