"""
The in-memory gallery index.

In plain words: the database is the source of truth for who is enrolled; this
class is a fast read-only copy of all reference embeddings kept in RAM as one
matrix, so a query is a single matrix multiplication. Whenever the gallery
changes (enroll, add images, delete, rebuild) the service builds a NEW
snapshot and swaps it in. Readers always see a complete, consistent snapshot,
and the ``version`` number changes every time - that is our cache invalidation.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from .ranking import best_score_per_identity, cosine_similarity, rank_identities
from .types import Candidate
from .validation import check_embedding


@dataclass(frozen=True)
class IndexEntry:
    reference_id: str
    image_uid: str
    embedding: np.ndarray  # (D,) float32, L2-normalised


@dataclass(frozen=True)
class IndexSnapshot:
    version: int
    embeddings: np.ndarray  # (R, D) rows grouped by identity
    image_uids: tuple[str, ...]  # (R,)
    reference_ids: tuple[str, ...]  # (I,) one per identity, sorted
    block_starts: np.ndarray  # (I,) first row of each identity
    image_counts: tuple[int, ...]  # (I,)

    @property
    def n_identities(self) -> int:
        return len(self.reference_ids)

    @property
    def n_images(self) -> int:
        return len(self.image_uids)


class GalleryIndex:
    def __init__(self, dim: int) -> None:
        self.dim = dim
        self._lock = threading.Lock()
        self._snapshot = self._empty(version=0)

    def _empty(self, version: int) -> IndexSnapshot:
        return IndexSnapshot(
            version=version,
            embeddings=np.zeros((0, self.dim), dtype=np.float32),
            image_uids=(),
            reference_ids=(),
            block_starts=np.zeros(0, dtype=np.int64),
            image_counts=(),
        )

    @property
    def snapshot(self) -> IndexSnapshot:
        return self._snapshot

    def replace(self, entries: Iterable[IndexEntry]) -> IndexSnapshot:
        """Rebuild the whole index from ``entries`` and publish it atomically."""
        ordered = sorted(entries, key=lambda entry: (entry.reference_id, entry.image_uid))
        with self._lock:
            version = self._snapshot.version + 1
            if not ordered:
                self._snapshot = self._empty(version)
                return self._snapshot

            matrix = np.stack([entry.embedding for entry in ordered]).astype(np.float32, copy=False)
            if matrix.shape[1] != self.dim:
                raise ValueError(f"Embedding dimension {matrix.shape[1]} does not match index dimension {self.dim}")

            reference_ids: list[str] = []
            starts: list[int] = []
            counts: list[int] = []
            for row, entry in enumerate(ordered):
                if not reference_ids or reference_ids[-1] != entry.reference_id:
                    reference_ids.append(entry.reference_id)
                    starts.append(row)
                    counts.append(0)
                counts[-1] += 1

            self._snapshot = IndexSnapshot(
                version=version,
                embeddings=matrix,
                image_uids=tuple(entry.image_uid for entry in ordered),
                reference_ids=tuple(reference_ids),
                block_starts=np.asarray(starts, dtype=np.int64),
                image_counts=tuple(counts),
            )
            return self._snapshot

    def search(self, query: np.ndarray, top_k: int) -> list[Candidate]:
        """Rank enrolled identities for one query embedding. Empty gallery -> empty list."""
        snapshot = self._snapshot  # grab once: a concurrent replace() cannot change it under us
        # A broken query vector is an ERROR, not an "unknown person" - even when the gallery is empty.
        query = check_embedding(query, self.dim)
        if snapshot.n_identities == 0:
            return []
        image_scores = cosine_similarity(query[None, :], snapshot.embeddings)
        identity_scores = best_score_per_identity(image_scores, snapshot.block_starts)
        order, values = rank_identities(identity_scores, top_k)

        candidates = []
        for position, (index, value) in enumerate(zip(order[0], values[0], strict=True)):
            start, count = int(snapshot.block_starts[index]), snapshot.image_counts[index]
            # Which reference image gave this identity its best score? (shown as "closest reference")
            best_row = start + int(np.argmax(image_scores[0, start : start + count]))
            candidates.append(
                Candidate(
                    rank=position + 1,
                    reference_id=snapshot.reference_ids[index],
                    score=float(value),
                    best_image_uid=snapshot.image_uids[best_row],
                    n_images=count,
                )
            )
        return candidates
