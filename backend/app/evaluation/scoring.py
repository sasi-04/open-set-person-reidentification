"""
From embeddings to the per-query results table.

In plain words: given the embeddings of a split's gallery and queries, this
produces one row per query - best identity score, margin to the runner-up,
was it the right person, where did the true person rank - using EXACTLY the
same ranking functions the live API uses (``cv/retrieval/ranking.py``).

Cross-camera rule (Market-1501 convention): when a KNOWN query comes from
camera 3, gallery photos of that same person from camera 3 are ignored, because
matching two frames from the same camera is too easy and would inflate the
numbers. Only the TRUE identity's same-camera photos are removed; other
people's photos are never touched, so strangers are not given an unfair
handicap. A known query whose person has no gallery photo from another camera
cannot be scored fairly and is dropped (and counted in the report).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..cv.retrieval.ranking import best_score_per_identity, cosine_similarity
from .datasets import ImageRecord
from .metrics import QueryScores, cmc, mean_average_precision
from .protocol import SplitProtocol


@dataclass
class ScoredSplit:
    qs: QueryScores
    query_records: list[ImageRecord]  # aligned with the rows of ``qs``
    mean_ap: float | None
    cmc: list[float]
    dropped_known_queries: int  # known queries without a cross-camera gallery photo
    # --- "who exactly won?" - used by the failure inspection and the threshold sandbox. Each list is
    # aligned with the rows of ``qs``. They are extra detail only: nothing in the metrics depends on them.
    top1_identity: list[str] = field(default_factory=list)  # the enrolled person the matcher picked
    top1_gallery_record: list[ImageRecord | None] = field(default_factory=list)  # the enrolled photo that matched best
    true_score: np.ndarray | None = None  # similarity to the query's TRUE person (NaN for strangers)

    def counts(self) -> dict:
        return {
            "known_queries": self.qs.n_known,
            "unknown_queries": self.qs.n_unknown,
            "dropped_known_queries": self.dropped_known_queries,
        }


def score_split(
    split: SplitProtocol,
    gallery_embeddings: np.ndarray,
    known_embeddings: np.ndarray,
    unknown_embeddings: np.ndarray,
    *,
    cross_camera: bool,
) -> ScoredSplit:
    # --- arrange the gallery so each person's images are contiguous -----------------
    order = sorted(range(len(split.gallery)), key=lambda i: (split.gallery[i].identity, split.gallery[i].path.name))
    gallery = [split.gallery[i] for i in order]
    g_emb = gallery_embeddings[order]
    g_ids = np.array([r.identity for r in gallery])
    g_cams = np.array([-1 if r.camera is None else r.camera for r in gallery])

    identities = sorted(set(g_ids.tolist()))
    id_index = {identity: i for i, identity in enumerate(identities)}
    block_starts = np.array([int(np.flatnonzero(g_ids == identity)[0]) for identity in identities])

    # --- similarities, with same-camera true-identity images switched off --------------
    queries = split.known_queries + split.unknown_queries
    q_emb = np.vstack([known_embeddings, unknown_embeddings]) if len(queries) else np.zeros((0, g_emb.shape[1]))
    n_known = len(split.known_queries)
    similarity = cosine_similarity(q_emb, g_emb)

    ignore = np.zeros(similarity.shape, dtype=bool)
    if cross_camera:
        for row, record in enumerate(split.known_queries):
            if record.camera is not None:
                ignore[row] = (g_ids == record.identity) & (g_cams == record.camera)
    masked = np.where(ignore, -np.inf, similarity)
    identity_scores = best_score_per_identity(masked, block_starts)  # (Q, I)

    # --- which known queries can be evaluated? ---------------------------------------
    true_index = np.array([id_index[r.identity] for r in split.known_queries], dtype=int)
    true_score = identity_scores[np.arange(n_known), true_index] if n_known else np.zeros(0)
    keep_known = np.isfinite(true_score)
    dropped = int((~keep_known).sum())
    keep_rows = np.concatenate([np.flatnonzero(keep_known), np.arange(n_known, len(queries))]).astype(int)

    # --- top-1 / top-2 per query --------------------------------------------------------
    ranking = np.argsort(-identity_scores, axis=1, kind="stable")
    top1_index = ranking[:, 0]
    top1_score = np.take_along_axis(identity_scores, top1_index[:, None], axis=1)[:, 0]
    if identity_scores.shape[1] > 1:
        top2_score = np.take_along_axis(identity_scores, ranking[:, 1:2], axis=1)[:, 0]
        margin = np.where(np.isfinite(top2_score), top1_score - top2_score, np.inf)
    else:
        margin = np.full(len(queries), np.inf)

    is_known_full = np.arange(len(queries)) < n_known
    true_index_full = np.concatenate([true_index, np.full(len(queries) - n_known, -1)])
    true_score_full = np.concatenate([true_score, np.full(len(queries) - n_known, np.nan)])
    top1_correct = is_known_full & (top1_index == true_index_full)
    # rank 1 + number of identities scoring strictly higher than the true one
    rank_full = np.zeros(len(queries), dtype=int)
    if n_known:
        rank_full[:n_known] = 1 + (identity_scores[:n_known] > true_score_full[:n_known, None]).sum(axis=1)
    rank_full[~np.isfinite(true_score_full) & is_known_full] = 0  # dropped rows (never used)

    cluster_names = [r.identity for r in queries]
    cluster_codes = {name: i for i, name in enumerate(sorted(set(cluster_names)))}
    cluster = np.array([cluster_codes[name] for name in cluster_names])

    qs = QueryScores(
        is_known=is_known_full[keep_rows],
        top1_score=top1_score[keep_rows].astype(np.float64),
        margin=margin[keep_rows].astype(np.float64),
        top1_correct=top1_correct[keep_rows],
        true_rank=rank_full[keep_rows],
        cluster=cluster[keep_rows],
    )

    # --- which enrolled person (and which of their photos) won each query ---------------
    block_ends = np.append(block_starts[1:], len(gallery))
    top1_identity, top1_gallery_record = [], []
    for row in keep_rows:
        winner = int(top1_index[row])
        top1_identity.append(identities[winner])
        block = masked[row, block_starts[winner] : block_ends[winner]]
        best_photo = int(block_starts[winner] + np.argmax(block)) if len(block) and np.isfinite(block.max()) else None
        top1_gallery_record.append(gallery[best_photo] if best_photo is not None else None)

    # --- closed-set image-level mAP over the kept known queries ----------------------
    known_rows = np.flatnonzero(keep_known)
    mean_ap = None
    if len(known_rows):
        mean_ap = mean_average_precision(
            masked[known_rows],
            np.array([split.known_queries[i].identity for i in known_rows]),
            g_ids,
            ignore[known_rows],
        )

    return ScoredSplit(
        qs=qs,
        query_records=[queries[i] for i in keep_rows],
        mean_ap=mean_ap,
        cmc=cmc(qs.true_rank[qs.is_known], max_rank=min(10, len(identities))),
        dropped_known_queries=dropped,
        top1_identity=top1_identity,
        top1_gallery_record=top1_gallery_record,
        true_score=true_score_full[keep_rows].astype(np.float64),
    )
