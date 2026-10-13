"""Small shared data type for retrieval results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    """One enrolled identity proposed for a query, with its retrieval score.

    ``score`` is a cosine similarity (-1..1). It is a *retrieval score*, not a
    probability - see ``open_set/confidence.py`` for the calibrated version.

    With face matching switched on, ``score`` is the score of the evidence the candidate was judged by (``basis``) and
    ``face_score`` / ``body_score`` hold what each fingerprint says separately (None = that fingerprint was not available).
    """

    rank: int  # 1 = most similar
    reference_id: str
    score: float
    best_image_uid: str | None = None  # which reference image produced the score
    n_images: int | None = None  # how many reference images this identity has
    basis: str = "body"  # "face" or "body": which fingerprint produced ``score``
    face_score: float | None = None
    body_score: float | None = None
    face_image_uid: str | None = None  # the reference image whose face matched best
