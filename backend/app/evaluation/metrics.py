"""
Evaluation metrics for open-set person re-identification.

In plain words: this file turns a table of query results into the numbers a
reviewer cares about. Every metric states its denominator. There is no model
code here - only arithmetic on arrays - so each formula can be checked by hand
against the toy examples in ``tests/test_metrics.py``.

THE TABLE (``QueryScores``) has one row per QUERY. A query is either

    known    the person IS enrolled in the gallery (their other photos are enrolled), or
    unknown  the person is NOT enrolled at all.

For each query the retrieval step has already produced the best identity score
(``top1_score``), the gap to the runner-up (``margin``), whether the best
identity was the right one (``top1_correct``) and where the true identity
ranked (``true_rank``, 1 = best).

DEFINITIONS (acceptance rule: accept iff top1_score >= threshold AND margin >= min_margin)
-------------------------------------------------------------------------------
FAR   False Accept Rate     = unknown queries accepted / ALL unknown queries.
                              An unknown query is falsely accepted whenever the system
                              names ANY enrolled identity for it (query-level, not pairwise).
TAR   True Accept Rate      = known queries accepted (any identity) / ALL known queries.
DIR@k Detection & Identification Rate at rank k
                            = known queries that are accepted AND whose true identity is
                              among the top-k candidates / ALL known queries.
                              DIR@1 = "accepted and correct" - the honest recall of the system.
FRR   False Reject Rate     = 1 - TAR   (known queries the system refused to accept).
Precision / Recall / F1     decision task "name the right person":
                              TP = known, accepted, correct identity
                              FP = accepted but wrong (an unknown person, or a known person
                                   given the wrong identity)
                              FN = known queries that were not correctly accepted
                              precision = TP/(TP+FP), recall = TP/(TP+FN) = DIR@1.
OSCR  Open-Set Classification Rate curve (Dhamija et al., 2018)
                            = DIR@1 plotted against FAR as the threshold sweeps. AUOSCR is the
                              area under it (1.0 = perfect). It judges rejection and correct
                              identification in one number.
Rank-k / CMC                closed-set: share of known queries whose true identity is in the
                            top-k (ignores thresholds; asks "can the system retrieve at all?").
mAP                         mean over known queries of average precision over the ranked gallery
                            IMAGES (Market-1501 style), counting same-identity images as relevant.

NOTE on the margin: it is a heuristic ambiguity signal, not a probability.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

# --------------------------------------------------------------------------
# The per-query results table
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class QueryScores:
    is_known: np.ndarray  # bool   (Q,)
    top1_score: np.ndarray  # float  (Q,)
    margin: np.ndarray  # float  (Q,)  top1 - top2; +inf when only one identity is enrolled
    top1_correct: np.ndarray  # bool   (Q,)  top-1 identity == true identity (always False for unknown)
    true_rank: np.ndarray  # int    (Q,)  1-based rank of the true identity; 0 for unknown queries
    cluster: np.ndarray  # int    (Q,)  true identity id - the unit for bootstrap resampling

    def __post_init__(self) -> None:
        sizes = {len(getattr(self, name)) for name in self.__dataclass_fields__}
        if len(sizes) != 1:
            raise ValueError("All QueryScores columns must have the same length.")

    def __len__(self) -> int:
        return len(self.top1_score)

    @property
    def n_known(self) -> int:
        return int(self.is_known.sum())

    @property
    def n_unknown(self) -> int:
        return int((~self.is_known).sum())

    def subset(self, index: np.ndarray) -> QueryScores:
        return QueryScores(*(getattr(self, name)[index] for name in self.__dataclass_fields__))

    def require_both_kinds(self) -> None:
        if self.n_known == 0 or self.n_unknown == 0:
            raise ValueError(
                f"Open-set metrics need both known and unknown queries (got {self.n_known} known, "
                f"{self.n_unknown} unknown)."
            )


def _rate(numerator: float, denominator: float) -> float | None:
    """Division that reports 'undefined' (None) instead of crashing or inventing a number."""
    return None if denominator == 0 else float(numerator) / float(denominator)


def accepted_mask(qs: QueryScores, threshold: float, min_margin: float | None = None) -> np.ndarray:
    accepted = qs.top1_score >= threshold
    if min_margin is not None:
        accepted &= qs.margin >= min_margin
    return accepted


# --------------------------------------------------------------------------
# Metrics at ONE operating point
# --------------------------------------------------------------------------


def operating_point(
    qs: QueryScores,
    threshold: float,
    min_margin: float | None = None,
    ranks: tuple[int, ...] = (1, 5),
) -> dict:
    """All rates at a fixed (threshold, margin) rule, with raw counts so denominators are visible."""
    accepted = accepted_mask(qs, threshold, min_margin)
    known, unknown = qs.is_known, ~qs.is_known

    n_known, n_unknown = int(known.sum()), int(unknown.sum())
    known_accepted = int((accepted & known).sum())
    unknown_accepted = int((accepted & unknown).sum())
    true_positive = int((accepted & known & qs.top1_correct).sum())
    false_positive = int(accepted.sum()) - true_positive

    precision = _rate(true_positive, true_positive + false_positive)
    recall = _rate(true_positive, n_known)
    if precision is None or recall is None:
        f1 = None  # undefined: nothing was accepted, or there are no known queries
    elif precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)

    return {
        "threshold": float(threshold),
        "min_margin": None if min_margin is None else float(min_margin),
        "counts": {
            "known_queries": n_known,
            "unknown_queries": n_unknown,
            "known_accepted": known_accepted,
            "known_accepted_correct": true_positive,
            "known_accepted_wrong_identity": known_accepted - true_positive,
            "unknown_accepted": unknown_accepted,
        },
        "far": _rate(unknown_accepted, n_unknown),
        "tar": _rate(known_accepted, n_known),
        "frr": _rate(n_known - known_accepted, n_known),
        "dir_at_rank": {
            str(k): _rate(int((accepted & known & (qs.true_rank >= 1) & (qs.true_rank <= k)).sum()), n_known)
            for k in ranks
        },
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


# --------------------------------------------------------------------------
# Threshold-sweeping curves
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RocCurve:
    """Points ordered from strictest (accept nothing) to loosest (accept everything)."""

    thresholds: np.ndarray  # +inf ... -inf, strictly decreasing
    far: np.ndarray
    tar: np.ndarray  # accepted known / known
    dir1: np.ndarray  # accepted AND correct / known  (the OSCR curve)

    def auc(self, which: str = "dir1") -> float:
        y = {"tar": self.tar, "dir1": self.dir1}[which]
        return float(np.trapezoid(y, self.far))


def roc_curve(qs: QueryScores, min_margin: float | None = None) -> RocCurve:
    """Sweep the threshold over every observed score. Needs known AND unknown queries."""
    qs.require_both_kinds()
    # Queries failing the margin rule can never be accepted: give them -inf effective score.
    effective = qs.top1_score.astype(np.float64).copy()
    if min_margin is not None:
        effective[qs.margin < min_margin] = -np.inf

    known, unknown = qs.is_known, ~qs.is_known
    unknown_scores = np.sort(effective[unknown])
    known_scores = np.sort(effective[known])
    correct_scores = np.sort(effective[known & qs.top1_correct])

    finite = np.unique(effective[np.isfinite(effective)])[::-1]  # distinct scores, high -> low
    thresholds = np.concatenate([[np.inf], finite, [-np.inf]])

    def accepted_at_or_above(sorted_scores: np.ndarray) -> np.ndarray:
        # number of entries >= t, for every t, via binary search on the sorted array
        return len(sorted_scores) - np.searchsorted(sorted_scores, thresholds, side="left")

    far = accepted_at_or_above(unknown_scores) / qs.n_unknown
    tar = accepted_at_or_above(known_scores) / qs.n_known
    dir1 = accepted_at_or_above(correct_scores) / qs.n_known
    # At threshold -inf EVERYTHING is accepted, including margin-failures: that is the
    # "no rejection" closed-set baseline (FAR = 1).
    far[-1], tar[-1] = 1.0, 1.0
    dir1[-1] = float((qs.is_known & qs.top1_correct).sum()) / qs.n_known
    return RocCurve(thresholds, far, tar, dir1)


def recall_at_far(curve: RocCurve, target_far: float, which: str = "dir1") -> dict:
    """Best recall achievable while FAR <= target (step function - no interpolation)."""
    y = {"tar": curve.tar, "dir1": curve.dir1}[which]
    eligible = np.flatnonzero(curve.far <= target_far)  # always includes the accept-nothing point
    # Highest recall wins; among equal recalls keep the strictest threshold (lowest FAR).
    best = eligible[np.flatnonzero(y[eligible] == y[eligible].max())[0]]
    return {
        "target_far": float(target_far),
        "recall": float(y[best]),
        "achieved_far": float(curve.far[best]),
        "threshold": None if not np.isfinite(curve.thresholds[best]) else float(curve.thresholds[best]),
        "metric": which,
    }


def far_at_recall(curve: RocCurve, target_recall: float, which: str = "dir1") -> dict:
    """Lowest FAR achievable while recall >= target. ``achievable`` is False if recall never gets there."""
    y = {"tar": curve.tar, "dir1": curve.dir1}[which]
    eligible = np.flatnonzero(y >= target_recall)
    if len(eligible) == 0:
        return {"target_recall": float(target_recall), "achievable": False, "far": None, "recall": None,
                "threshold": None, "metric": which}
    lowest_far = curve.far[eligible].min()
    # Several thresholds can share the lowest FAR; take the loosest one (it has the highest recall).
    best = eligible[curve.far[eligible] == lowest_far][-1]
    return {
        "target_recall": float(target_recall),
        "achievable": True,
        "far": float(curve.far[best]),
        "recall": float(y[best]),
        "threshold": None if not np.isfinite(curve.thresholds[best]) else float(curve.thresholds[best]),
        "metric": which,
    }


# --------------------------------------------------------------------------
# Closed-set retrieval metrics
# --------------------------------------------------------------------------


def cmc(true_rank: np.ndarray, max_rank: int = 10) -> list[float]:
    """Rank-k accuracy for k = 1..max_rank over KNOWN queries (true_rank >= 1)."""
    ranks = true_rank[true_rank >= 1]
    if len(ranks) == 0:
        return []
    return [float((ranks <= k).mean()) for k in range(1, max_rank + 1)]


def average_precision(relevant_sorted: np.ndarray) -> float | None:
    """AP for one query given a boolean 'is relevant' list already sorted by similarity."""
    total = int(relevant_sorted.sum())
    if total == 0:
        return None
    hits = np.cumsum(relevant_sorted)
    precision_at_hit = hits[relevant_sorted] / (np.flatnonzero(relevant_sorted) + 1)
    return float(precision_at_hit.sum() / total)


def mean_average_precision(
    similarity: np.ndarray,
    query_ids: np.ndarray,
    gallery_ids: np.ndarray,
    ignore: np.ndarray | None = None,
) -> float | None:
    """mAP over rows of an image-level similarity matrix (Q, G).

    ``ignore`` (Q, G) marks gallery images to skip for a query (e.g. same camera as the query).
    Queries with no relevant image left are skipped. Returns None if no query is evaluable.
    """
    values = []
    for row in range(similarity.shape[0]):
        keep = np.arange(similarity.shape[1]) if ignore is None else np.flatnonzero(~ignore[row])
        order = keep[np.argsort(-similarity[row, keep], kind="stable")]
        ap = average_precision(gallery_ids[order] == query_ids[row])
        if ap is not None:
            values.append(ap)
    return float(np.mean(values)) if values else None


# --------------------------------------------------------------------------
# Uncertainty and sample-size honesty
# --------------------------------------------------------------------------


def wilson_upper_bound(events: int, trials: int, z: float = 1.645) -> float | None:
    """One-sided 95% upper confidence bound for a rate (Wilson score interval)."""
    if trials == 0:
        return None
    p = events / trials
    denominator = 1 + z * z / trials
    centre = p + z * z / (2 * trials)
    margin = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials))
    return min(1.0, (centre + margin) / denominator)


def minimum_unknown_queries_for_far(target_far: float) -> int:
    """'Rule of three': to show a FAR below ``target`` you need roughly 3/target unknown queries."""
    return int(math.ceil(3.0 / target_far)) if target_far > 0 else 0


def cluster_bootstrap_ci(
    qs: QueryScores,
    statistics: dict[str, Callable[[QueryScores], float | None]],
    *,
    n_boot: int,
    seed: int,
    level: float = 0.95,
) -> dict[str, dict | None]:
    """Percentile confidence intervals that resample whole IDENTITIES, not single queries.

    Queries of the same person are not independent (they look alike), so resampling single
    queries would make the intervals too narrow. Every resample draws people with replacement
    and re-computes ALL statistics on the same resample, so the intervals are consistent.
    """
    if n_boot <= 0:
        return {name: None for name in statistics}
    rng = np.random.default_rng(seed)
    clusters = np.unique(qs.cluster)
    members = {int(c): np.flatnonzero(qs.cluster == c) for c in clusters}

    draws: dict[str, list[float]] = {name: [] for name in statistics}
    for _ in range(n_boot):
        picked = rng.choice(clusters, size=len(clusters), replace=True)
        resample = qs.subset(np.concatenate([members[int(c)] for c in picked]))
        if resample.n_known == 0 or resample.n_unknown == 0:
            continue
        for name, statistic in statistics.items():
            value = statistic(resample)
            if value is not None and math.isfinite(value):
                draws[name].append(value)

    intervals: dict[str, dict | None] = {}
    for name, values in draws.items():
        if len(values) < max(10, n_boot // 2):
            intervals[name] = None
            continue
        low, high = np.quantile(values, [(1 - level) / 2, 1 - (1 - level) / 2])
        intervals[name] = {"low": float(low), "high": float(high), "level": level, "n_resamples": len(values)}
    return intervals


# --------------------------------------------------------------------------
# Confidence calibration quality
# --------------------------------------------------------------------------


def calibration_report(probability: np.ndarray, outcome: np.ndarray, bins: int = 10) -> dict:
    """Reliability table, Expected Calibration Error and Brier score for a probability forecast."""
    probability = np.asarray(probability, dtype=np.float64)
    outcome = np.asarray(outcome, dtype=np.float64)
    edges = np.linspace(0.0, 1.0, bins + 1)
    which_bin = np.clip(np.digitize(probability, edges[1:-1]), 0, bins - 1)

    table, ece = [], 0.0
    for b in range(bins):
        selected = which_bin == b
        n = int(selected.sum())
        if n == 0:
            continue
        mean_p, observed = float(probability[selected].mean()), float(outcome[selected].mean())
        ece += n / len(probability) * abs(mean_p - observed)
        table.append({"bin_low": float(edges[b]), "bin_high": float(edges[b + 1]), "n": n,
                      "mean_predicted": mean_p, "observed_rate": observed})
    return {
        "ece": float(ece),
        "brier": float(np.mean((probability - outcome) ** 2)),
        "n": int(len(probability)),
        "bins": table,
    }


def score_histogram(qs: QueryScores, bins: int = 40, value_range: tuple[float, float] = (0.0, 1.0)) -> dict:
    """Distribution of top-1 scores for correct-known / wrong-known / unknown queries.

    The overlap between the 'unknown' and 'correct known' histograms IS the low
    inter-class-variance problem: the more they overlap, the harder it is to
    reject strangers without also rejecting enrolled people.
    """
    edges = np.linspace(value_range[0], value_range[1], bins + 1)

    def counts(mask: np.ndarray) -> list[int]:
        return np.histogram(np.clip(qs.top1_score[mask], *value_range), bins=edges)[0].astype(int).tolist()

    return {
        "bin_edges": [round(float(e), 4) for e in edges],
        "known_correct": counts(qs.is_known & qs.top1_correct),
        "known_wrong": counts(qs.is_known & ~qs.top1_correct),
        "unknown": counts(~qs.is_known),
    }
