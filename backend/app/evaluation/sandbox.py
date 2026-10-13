"""
The threshold sandbox: "what would change if I moved the dial?"

In plain words: when an evaluation finishes we keep one small table per split -
for every query image, the best matching enrolled person, how similar they were,
the gap to the runner-up and whether that person was the right one. Nothing
else. This module lets you try ANY threshold (and margin rule) on that fixed
table and see, immediately and with real numbers:

  * how many strangers would be let in / how many enrolled people turned away,
  * which individual queries would change their decision compared with the
    calibrated rule, so you can look at them.

Three guarantees, each covered by a test:

  1. It only does arithmetic on the stored table. It never re-runs a model, so
     the table is exactly the "fixed evaluation set" the original run produced.
  2. It applies the SAME rule as the live decision engine
     (``cv/open_set/decision_engine.py``, rules 3-5) - ``decide_rows`` is checked
     against ``decide`` in ``tests/test_sandbox.py``.
  3. It NEVER writes to the active decision policy. The only way to change the
     production threshold is a calibration run on the calibration split followed
     by an explicit "apply". Looking at test-split numbers while moving a slider
     is exploration, not tuning, and the result says so.
"""

from __future__ import annotations

import numpy as np

from . import metrics as m
from .scoring import ScoredSplit

ACCEPTED, REVIEW, UNKNOWN = "accepted", "review_required", "unknown"
SANDBOX_VERSION = 1


# ----------------------------------------------------------------------------------
# Storing the table
# ----------------------------------------------------------------------------------
def build_split_rows(scored: ScoredSplit, dataset_root) -> dict:
    """One compact column-per-field table for a scored split (JSON-friendly)."""
    qs = scored.qs

    def relative(path) -> str:
        return path.relative_to(dataset_root).as_posix() if path.is_relative_to(dataset_root) else path.name

    finite = np.isfinite(qs.margin)
    return {
        "n": int(len(qs)),
        "ref": [relative(r.path) for r in scored.query_records],
        "identity": [r.identity for r in scored.query_records],
        "is_known": qs.is_known.tolist(),
        "top1_identity": list(scored.top1_identity),
        "top1_score": [round(float(v), 5) for v in qs.top1_score],
        "margin": [round(float(v), 5) if ok else None for v, ok in zip(qs.margin, finite, strict=True)],  # None = no runner-up
        "top1_correct": qs.top1_correct.tolist(),
        "true_rank": qs.true_rank.astype(int).tolist(),
    }


def build_payload(calibration: ScoredSplit, test: ScoredSplit, dataset_root, *, reference: dict, source: str,
                  seed: int, model_fingerprint: str | None) -> dict:
    return {
        "version": SANDBOX_VERSION,
        "seed": seed,
        "embedding_source": source,
        "model_fingerprint": model_fingerprint,
        "reference": reference,  # the calibrated rule the run itself used: {variant, threshold, min_margin, margin_action}
        "splits": {"calibration": build_split_rows(calibration, dataset_root), "test": build_split_rows(test, dataset_root)},
    }


def to_query_scores(rows: dict) -> m.QueryScores:
    margin = np.array([np.inf if v is None else v for v in rows["margin"]], dtype=np.float64)
    codes = {name: i for i, name in enumerate(sorted(set(rows["identity"])))}
    return m.QueryScores(
        is_known=np.array(rows["is_known"], dtype=bool),
        top1_score=np.array(rows["top1_score"], dtype=np.float64),
        margin=margin,
        top1_correct=np.array(rows["top1_correct"], dtype=bool),
        true_rank=np.array(rows["true_rank"], dtype=int),
        cluster=np.array([codes[name] for name in rows["identity"]], dtype=int),
    )


# ----------------------------------------------------------------------------------
# The rule (same order as the live decision engine, rules 3-5)
# ----------------------------------------------------------------------------------
def decide_rows(top1_score: np.ndarray, margin: np.ndarray, threshold: float, min_margin: float | None,
                margin_action: str) -> np.ndarray:
    """Outcome per query: ``accepted`` / ``review_required`` / ``unknown``.

    Rule 3: top-1 below the threshold            -> unknown
    Rule 4: margin below the minimum (if set)    -> review_required (or unknown, if the policy rejects)
    Rule 5: otherwise                            -> accepted
    A missing runner-up (margin = +inf) can never fail the margin rule - exactly like the live engine.
    """
    outcome = np.full(len(top1_score), ACCEPTED, dtype=object)
    below = top1_score < threshold
    ambiguous = np.zeros(len(top1_score), dtype=bool)
    if min_margin is not None:
        ambiguous = ~below & (margin < min_margin)
    outcome[ambiguous] = REVIEW if margin_action == "review" else UNKNOWN
    outcome[below] = UNKNOWN
    return outcome


def _confusion(qs: m.QueryScores, outcome: np.ndarray) -> dict:
    accepted = outcome == ACCEPTED
    known, unknown = qs.is_known, ~qs.is_known
    return {
        "true_accepts": int((accepted & known & qs.top1_correct).sum()),
        "wrong_identity_accepts": int((accepted & known & ~qs.top1_correct).sum()),
        "false_accepts": int((accepted & unknown).sum()),
        "false_rejects": int((~accepted & known).sum()),
        "true_rejects": int((~accepted & unknown).sum()),
        "known_sent_to_review": int(((outcome == REVIEW) & known).sum()),
        "unknown_sent_to_review": int(((outcome == REVIEW) & unknown).sum()),
        "definitions": {
            "true_accepts": "enrolled person, accepted, and the right person was named",
            "wrong_identity_accepts": "enrolled person, accepted, but a DIFFERENT enrolled person was named",
            "false_accepts": "stranger (not enrolled), accepted as someone",
            "false_rejects": "enrolled person, not accepted (rejected as unknown OR sent to review)",
            "true_rejects": "stranger, not accepted",
        },
    }


def _summary(rows: dict, qs: m.QueryScores, threshold: float, min_margin: float | None, margin_action: str) -> dict:
    outcome = decide_rows(qs.top1_score, qs.margin, threshold, min_margin, margin_action)
    point = m.operating_point(qs, threshold, min_margin)
    point["far_upper_bound_95"] = m.wilson_upper_bound(point["counts"]["unknown_accepted"], point["counts"]["unknown_queries"])
    return {
        "rule": {"threshold": threshold, "min_margin": min_margin, "margin_action": margin_action},
        "metrics": point,
        "confusion": _confusion(qs, outcome),
        "outcome_counts": {name: int((outcome == name).sum()) for name in (ACCEPTED, REVIEW, UNKNOWN)},
        "_outcome": outcome,
    }


def explore(payload: dict, split: str, *, threshold: float, min_margin: float | None, margin_action: str,
            max_examples: int = 12) -> dict:
    """Apply a trial rule to a stored split and compare it with the run's calibrated rule."""
    if split not in payload["splits"]:
        raise KeyError(split)
    rows = payload["splits"][split]
    qs = to_query_scores(rows)
    reference = payload["reference"]
    ref_margin_action = reference.get("margin_action", "review")

    trial = _summary(rows, qs, threshold, min_margin, margin_action)
    baseline = _summary(rows, qs, reference["threshold"], reference.get("min_margin"), ref_margin_action)

    changed = np.flatnonzero(trial["_outcome"] != baseline["_outcome"])
    # The most instructive changes first: strangers that now get in, then enrolled people now turned away, then the rest.
    def importance(i: int) -> tuple:
        now_in = trial["_outcome"][i] == ACCEPTED
        return (0 if (now_in and not qs.is_known[i]) else 1 if (not now_in and qs.is_known[i]) else 2,
                -abs(qs.top1_score[i] - threshold))

    examples = []
    for i in sorted(changed.tolist(), key=importance)[:max_examples]:
        examples.append({
            "ref": rows["ref"][i], "query_identity": rows["identity"][i], "is_known": bool(qs.is_known[i]),
            "top1_identity": rows["top1_identity"][i], "top1_correct": bool(qs.top1_correct[i]),
            "top1_score": rows["top1_score"][i], "margin": rows["margin"][i],
            "calibrated_rule": baseline["_outcome"][i], "trial_rule": trial["_outcome"][i],
        })

    for summary in (trial, baseline):
        summary.pop("_outcome")
    test_note = (
        "You are looking at the TEST split. Moving the threshold while watching these numbers and then keeping "
        "the best-looking value would be tuning on the test set - the result would no longer be an honest "
        "measurement. Use this view to understand the trade-off; choose real thresholds on the calibration split."
        if split == "test" else None
    )
    return {
        "split": split, "n_queries": int(len(qs)), "trial": trial, "calibrated_rule": baseline,
        "decisions_changed": int(len(changed)), "changed_examples": examples,
        "writes_policy": False,  # the sandbox can never change the active decision policy
        "warning": test_note,
        "embedding_source": payload.get("embedding_source"), "model_fingerprint": payload.get("model_fingerprint"),
    }


def threshold_range(payload: dict) -> dict:
    """Useful slider bounds for the UI: the observed range of top-1 similarities."""
    scores = [s for rows in payload["splits"].values() for s in rows["top1_score"]]
    if not scores:
        return {"min": 0.0, "max": 1.0}
    return {"min": round(min(scores), 3), "max": round(max(scores), 3)}
