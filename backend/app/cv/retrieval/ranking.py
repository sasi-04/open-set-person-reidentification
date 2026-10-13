"""
Similarity and ranking math (pure numpy, no I/O).

In plain words: given the fingerprint of a query person and the fingerprints of
all enrolled reference images, answer "which ENROLLED PEOPLE look most like
the query, and how much?". Two functions do the work:

  * ``cosine_similarity``       - every embedding has length 1, so a plain dot
                                  product IS the cosine similarity (range -1..1).
  * ``best_score_per_identity`` - a person has several reference images; the
                                  person's score is the score of their BEST
                                  matching image ("max over references").

Gallery strategy (documented decision, used identically in serving and in the
evaluation code because both import this file): we keep the individual image
embeddings of each identity - no averaged prototype - and score an identity by
its best-matching image. Identity ranking breaks exact ties by the identity's
position in the gallery, so results are deterministic.
"""

from __future__ import annotations

import numpy as np


def cosine_similarity(queries: np.ndarray, references: np.ndarray) -> np.ndarray:
    """(Q, D) x (R, D) -> (Q, R) similarity matrix. Inputs must already be L2-normalised."""
    if queries.ndim != 2 or references.ndim != 2 or queries.shape[1] != references.shape[1]:
        raise ValueError(f"Incompatible shapes {queries.shape} and {references.shape}")
    similarity = queries @ references.T
    return np.clip(similarity, -1.0, 1.0, out=similarity)


def best_score_per_identity(similarities: np.ndarray, block_starts: np.ndarray) -> np.ndarray:
    """Collapse image-level scores (Q, R) into identity-level scores (Q, I).

    ``block_starts[i]`` is the column where identity ``i``'s images begin; the
    reference columns must be grouped by identity (the gallery index guarantees it).
    """
    return np.maximum.reduceat(similarities, block_starts, axis=1)


def rank_identities(scores: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Top-k identity indices and scores per query, best first.

    ``scores`` is (Q, I). A *stable* sort on the negated scores means that equal
    scores keep their gallery order, which makes the output fully deterministic.
    """
    k = max(1, min(k, scores.shape[1]))
    order = np.argsort(-scores, axis=1, kind="stable")[:, :k]
    return order, np.take_along_axis(scores, order, axis=1)
