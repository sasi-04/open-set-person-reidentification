"""
The "same-clothing" (low inter-class variance) evaluation subset.

In plain words: the hard cases for open-set ReID are strangers who dress like
an enrolled person. Benchmarks like Market-1501 do NOT label clothing, so we
cannot pretend a ground-truth "same clothing" attribute exists. Instead:

PROXY (default)  For every query we measure how similar its torso and leg
                 COLOURS are to the closest OTHER enrolled person, using simple
                 HSV colour histograms. The queries in the top quartile of that
                 similarity form the "hard subset".
                   * unknown query: closest colour match among ALL enrolled people
                   * known query:   closest colour match among OTHER enrolled people
                 The proxy never looks at the ReID model, the decision threshold
                 or any test outcome, so the subset cannot be cherry-picked
                 after seeing results. It is a proxy, and the report says so.

MANUAL (override) If ``<dataset>/hard_subset.json`` exists - a list of image
                 paths relative to the dataset folder that a human annotated as
                 "wearing similar clothing to another enrolled person" - it is
                 used instead of the proxy. This is the mechanism for genuine
                 ground-truth annotation.

File format:  {"hard_queries": ["0002/c1_0001.jpg", "0007/c3_0004.jpg"]}
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from ..cv.imaging import load_rgb_file
from .datasets import ImageRecord
from .protocol import SplitProtocol

# Body regions as fractions of crop height; side margins avoid most background.
_TORSO = (0.22, 0.50)
_LEGS = (0.52, 0.82)
_COLUMNS = (0.20, 0.80)
_HIST_BINS = (8, 3, 3)  # hue x saturation x value


def color_descriptor(rgb: np.ndarray) -> np.ndarray:
    """144-number clothing-colour fingerprint (torso + legs), square-rooted so a dot product = Bhattacharyya."""
    resized = cv2.resize(rgb, (64, 128), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(resized, cv2.COLOR_RGB2HSV)
    parts = []
    for top, bottom in (_TORSO, _LEGS):
        region = hsv[int(top * 128) : int(bottom * 128), int(_COLUMNS[0] * 64) : int(_COLUMNS[1] * 64)]
        histogram = cv2.calcHist([region], [0, 1, 2], None, list(_HIST_BINS), [0, 180, 0, 256, 0, 256]).flatten()
        histogram /= histogram.sum() + 1e-9
        parts.append(np.sqrt(histogram))
    return np.concatenate(parts).astype(np.float32)


def colour_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """(N, 144) x (M, 144) -> (N, M) similarity in [0, 1] (mean Bhattacharyya of torso and legs)."""
    return (a @ b.T) / 2.0


def describe_records(records: list[ImageRecord]) -> np.ndarray:
    if not records:
        return np.zeros((0, 2 * int(np.prod(_HIST_BINS))), dtype=np.float32)
    return np.stack([color_descriptor(load_rgb_file(r.path)) for r in records])


def manual_hard_paths(dataset_root: Path) -> set[str] | None:
    """Relative paths listed in ``hard_subset.json`` (None if the file does not exist)."""
    path = dataset_root / "hard_subset.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(p).replace("\\", "/") for p in payload.get("hard_queries", [])}


def hard_query_mask(
    split: SplitProtocol,
    query_records: list[ImageRecord],
    is_known: np.ndarray,
    *,
    dataset_root: Path,
    quantile: float = 0.75,
) -> tuple[np.ndarray, dict]:
    """Boolean mask over ``query_records`` marking the hard subset, plus a description of how it was made."""
    manual = manual_hard_paths(dataset_root)
    if manual is not None:
        mask = np.array(
            [r.path.relative_to(dataset_root).as_posix() in manual if r.path.is_relative_to(dataset_root) else False
             for r in query_records]
        )
        return mask, {"method": "manual annotation", "source": "hard_subset.json", "queries": int(mask.sum())}

    gallery_desc = describe_records(split.gallery)
    query_desc = describe_records(query_records)
    similarity = colour_similarity(query_desc, gallery_desc)  # (Q, G)
    gallery_ids = np.array([r.identity for r in split.gallery])

    difficulty = np.zeros(len(query_records))
    for row, record in enumerate(query_records):
        # Known queries are compared with OTHER people only: their own photos are not a "look-alike".
        candidates = similarity[row] if not is_known[row] else np.where(gallery_ids != record.identity, similarity[row], -1.0)
        difficulty[row] = candidates.max() if len(candidates) else 0.0

    mask = np.zeros(len(query_records), dtype=bool)
    for group in (is_known, ~is_known):  # separate cut-offs so both kinds are represented
        if group.any():
            cutoff = np.quantile(difficulty[group], quantile)
            mask |= group & (difficulty >= cutoff)
    return mask, {
        "method": "colour-histogram proxy (label-free, model-independent)",
        "quantile": quantile,
        "regions": "torso + legs, HSV 8x3x3 histograms, Bhattacharyya similarity",
        "queries": int(mask.sum()),
        "note": "A proxy for same-clothing look-alikes - Market-1501 has no clothing labels.",
    }
