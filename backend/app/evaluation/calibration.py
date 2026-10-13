"""
Choosing the operating point (threshold + margin) on CALIBRATION data.

In plain words: the acceptance threshold is the dial that trades "let
strangers in" against "turn enrolled people away". We never pick it by
feel and never by looking at the final test results. This module picks it
from the calibration split, in one of two modes:

  fixed_recall (the PS-1 objective)  "Keep at least R% of enrolled people being
                                      correctly accepted, and make the False Accept
                                      Rate as small as possible."
  fixed_far                          "Never let more than F% of strangers in, and
                                      keep as many enrolled people as possible."

It can also search a small grid of margin values (top-1 minus top-2) and keep
the combination that works best on the calibration data. It tells the truth
when it fails: if no threshold reaches the target, ``target_achieved`` is False
and the report says what WAS reachable. It also reports the sample size and a
95% upper confidence bound on the FAR, because a threshold selected on a small
calibration set can not "guarantee" any particular FAR on new people.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from .metrics import (
    QueryScores,
    far_at_recall,
    minimum_unknown_queries_for_far,
    operating_point,
    recall_at_far,
    roc_curve,
    wilson_upper_bound,
)

# Candidate minimum margins searched when the margin rule is enabled. A short fixed list keeps
# the search small, so there is little room to over-fit the calibration data.
MARGIN_GRID: tuple[float, ...] = (0.01, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15)


@dataclass(frozen=True)
class OperatingTarget:
    mode: str = "fixed_recall"  # "fixed_recall" | "fixed_far"
    target_recall: float = 0.90
    target_far: float = 0.01
    recall_metric: str = "dir1"  # "dir1" = accepted AND correct (honest) | "tar" = accepted (any identity)

    def validate(self) -> None:
        if self.mode not in ("fixed_recall", "fixed_far"):
            raise ValueError("mode must be 'fixed_recall' or 'fixed_far'")
        if self.recall_metric not in ("dir1", "tar"):
            raise ValueError("recall_metric must be 'dir1' or 'tar'")
        if not 0 < self.target_recall <= 1:
            raise ValueError("target_recall must be in (0, 1]")
        if not 0 <= self.target_far < 1:
            raise ValueError("target_far must be in [0, 1)")

    def describe(self) -> str:
        metric = "DIR@1 (accepted and correct)" if self.recall_metric == "dir1" else "TAR (accepted)"
        if self.mode == "fixed_recall":
            return f"{metric} >= {self.target_recall:.1%}, minimise FAR"
        return f"FAR <= {self.target_far:.2%}, maximise {metric}"


@dataclass
class SelectedPoint:
    target: dict
    target_achieved: bool
    threshold: float | None  # accept iff top-1 similarity >= threshold
    min_margin: float | None
    calibration: dict  # operating-point metrics measured on the calibration data
    far_upper_bound_95: float | None
    n_unknown: int
    n_known: int
    sample_size_adequate: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _best_for_margin(curve, target: OperatingTarget) -> dict:
    if target.mode == "fixed_recall":
        result = far_at_recall(curve, target.target_recall, target.recall_metric)
        achieved = bool(result["achievable"]) and result["threshold"] is not None
        return {"achieved": achieved, "threshold": result["threshold"], "far": result["far"],
                "recall": result["recall"]}
    result = recall_at_far(curve, target.target_far, target.recall_metric)
    achieved = result["threshold"] is not None and result["recall"] > 0
    return {"achieved": achieved, "threshold": result["threshold"], "far": result["achieved_far"],
            "recall": result["recall"]}


def _score_for_ranking(candidate: dict, target: OperatingTarget) -> tuple:
    """Sort key: lower is better. Ties prefer the simpler rule (no margin / smaller margin)."""
    if target.mode == "fixed_recall":
        return (candidate["far"], -candidate["recall"], candidate["min_margin"] or 0.0)
    return (-candidate["recall"], candidate["far"], candidate["min_margin"] or 0.0)


def select_operating_point(
    calibration: QueryScores,
    target: OperatingTarget,
    *,
    use_margin: bool = False,
    margin_grid: tuple[float, ...] = MARGIN_GRID,
) -> SelectedPoint:
    target.validate()
    calibration.require_both_kinds()

    rules: list[float | None] = [None] + (list(margin_grid) if use_margin else [])
    candidates = []
    for margin in rules:
        curve = roc_curve(calibration, min_margin=margin)
        best = _best_for_margin(curve, target)
        candidates.append({**best, "min_margin": margin})

    achieving = [c for c in candidates if c["achieved"]]
    notes: list[str] = []
    if achieving:
        chosen = min(achieving, key=lambda c: _score_for_ranking(c, target))
        threshold, margin, achieved = chosen["threshold"], chosen["min_margin"], True
    else:
        # Nothing reaches the target. Report the best-effort rule so the user can see what IS possible.
        achieved = False
        curve = roc_curve(calibration)
        threshold = float(np.min(curve.thresholds[np.isfinite(curve.thresholds)]))
        margin = None
        notes.append(
            "The requested operating point could NOT be met on the calibration data "
            f"({target.describe()}). The threshold shown is only a best-effort fallback (accept every query "
            "that scores at least as high as the lowest observed score) and must not be treated as calibrated."
        )

    point = operating_point(calibration, threshold, margin)
    far_events = point["counts"]["unknown_accepted"]
    upper = wilson_upper_bound(far_events, calibration.n_unknown)

    adequate = True
    if target.mode == "fixed_far":
        needed = minimum_unknown_queries_for_far(target.target_far)
        adequate = calibration.n_unknown >= needed
        if not adequate:
            notes.append(
                f"Only {calibration.n_unknown} unknown calibration queries; roughly {needed} are needed to "
                f"resolve a FAR of {target.target_far:.2%}. Treat the threshold as indicative."
            )
    if upper is not None and achieved:
        notes.append(
            f"On the calibration data {far_events} of {calibration.n_unknown} unknown queries were accepted "
            f"(FAR {point['far']:.2%}); the 95% upper confidence bound is {upper:.2%}. "
            "This is a measurement on one sample of people, not a guarantee for new people."
        )

    return SelectedPoint(
        target=asdict(target),
        target_achieved=achieved,
        threshold=float(threshold) if threshold is not None else None,
        min_margin=margin,
        calibration=point,
        far_upper_bound_95=upper,
        n_unknown=calibration.n_unknown,
        n_known=calibration.n_known,
        sample_size_adequate=adequate,
        notes=notes,
    )
