"""
Is this vector fit to be compared?

In plain words: the whole decision rests on comparing fingerprints (embeddings). A fingerprint that is
broken - the wrong size, full of NaN, all zeros, or not scaled to length 1 - would still produce *a* number
when compared, and that number could look like an ordinary "no match". So every vector is checked at the
door of the search, and a bad one is reported as what it is: a PROCESSING ERROR with a reason, never as
"unknown person". The same check protects the stored reference fingerprints when the gallery index is
rebuilt: a corrupted one is set aside and marked failed instead of silently poisoning every search.
"""

from __future__ import annotations

import numpy as np

from ...core.errors import ProcessingFailed

UNIT_TOLERANCE = 1e-3  # an L2-normalised float32 vector has length 1 to within this


class InvalidEmbedding(ProcessingFailed):
    """The vector cannot be compared. ``message`` says exactly why."""

    code = "invalid_embedding"


def check_embedding(vector: np.ndarray, dim: int) -> np.ndarray:
    """Return ``vector`` as float32 if it is one finite, unit-length vector of ``dim`` numbers; otherwise raise."""
    array = np.asarray(vector)
    if array.ndim != 1:
        raise InvalidEmbedding(f"The embedding must be a single vector, but has shape {tuple(array.shape)}.")
    if array.shape[0] != dim:
        raise InvalidEmbedding(f"The embedding has {array.shape[0]} numbers but this model produces {dim}: it comes from a different model.")
    try:
        array = array.astype(np.float32, copy=False)
    except (TypeError, ValueError) as exc:
        raise InvalidEmbedding("The embedding contains values that are not numbers.") from exc
    if not np.isfinite(array).all():
        raise InvalidEmbedding("The embedding contains NaN or infinite values.")
    length = float(np.linalg.norm(array))
    if length == 0.0:
        raise InvalidEmbedding("The embedding has zero length, so it carries no information and cannot be compared.")
    if abs(length - 1.0) > UNIT_TOLERANCE:
        raise InvalidEmbedding(f"The embedding has length {length:.4f} instead of 1: it was not normalised, so similarities would be wrong.")
    return array
