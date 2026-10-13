"""
The ablation variants and how one variant is evaluated.

In plain words: an ablation answers "which ingredient actually helps?". Every
variant below differs from its ``parent`` by exactly ONE ingredient, and every
variant is measured with the same metrics on the same test people:

  nn_baseline          Nearest neighbour, never rejects. The closed-set way of working:
                       shows why a nearest neighbour alone is unsafe (FAR = 100%).
  thr                  + threshold chosen on the calibration split.
  thr_margin           + top-1 / top-2 margin rule (a near-tie is not a confident match).
  thr_confidence       + (instead of the margin rule) a calibrated confidence fitted from
                       similarity and margin; the threshold is applied to that confidence.
  thr_margin_flip      + horizontal-flip test-time augmentation of the embeddings.
  thr_margin_finetuned + a backbone fine-tuned with batch-hard triplet loss (only if a
                       checkpoint was supplied; otherwise reported as "not available").

NOTHING here looks at test results to choose anything: thresholds, margins and
confidence models are all fitted on the calibration split, then frozen and applied to the
test split. Whether a variant "wins" is decided afterwards by the CALIBRATION numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..cv.open_set.confidence import ConfidenceModel
from . import metrics as m
from .calibration import OperatingTarget, select_operating_point
from .scoring import ScoredSplit


@dataclass(frozen=True)
class VariantSpec:
    key: str
    label: str
    description: str
    parent: str | None
    rejection: str  # "none" | "threshold" | "threshold_margin" | "confidence"
    flip: bool = False
    finetuned: bool = False


VARIANTS: tuple[VariantSpec, ...] = (
    VariantSpec("nn_baseline", "Nearest neighbour (no rejection)",
                "Always names the closest enrolled person. Closed-set behaviour; cannot say 'unknown'.",
                None, "none"),
    VariantSpec("thr", "+ Calibrated threshold",
                "Accept only if the top-1 similarity reaches a threshold chosen on the calibration split.",
                "nn_baseline", "threshold"),
    VariantSpec("thr_margin", "+ Top-1/top-2 margin rule",
                "Also require the winner to beat the runner-up by a margin chosen on the calibration split.",
                "thr", "threshold_margin"),
    VariantSpec("thr_confidence", "+ Calibrated confidence (instead of margin)",
                "Fit P(top-1 correct | similarity, margin) on the calibration split and threshold that.",
                "thr", "confidence"),
    VariantSpec("thr_margin_flip", "+ Flip test-time augmentation",
                "Average each embedding with the embedding of the mirrored crop.",
                "thr_margin", "threshold_margin", flip=True),
    VariantSpec("thr_margin_finetuned", "+ Triplet fine-tuned backbone",
                "Backbone fine-tuned with batch-hard triplet loss on the development identities.",
                "thr_margin", "threshold_margin", finetuned=True),
)
VARIANT_BY_KEY = {v.key: v for v in VARIANTS}
DEFAULT_VARIANT_KEYS = tuple(v.key for v in VARIANTS if not v.finetuned)

_CURVE_POINTS = 160


def _downsample_curve(curve: m.RocCurve) -> dict:
    """Keep the plot payload small: at most ~160 evenly spaced points, always including both ends."""
    n = len(curve.far)
    index = np.unique(np.linspace(0, n - 1, min(n, _CURVE_POINTS)).astype(int))
    finite = lambda v: None if not np.isfinite(v) else round(float(v), 5)  # noqa: E731
    return {
        "far": [round(float(curve.far[i]), 5) for i in index],
        "tar": [round(float(curve.tar[i]), 5) for i in index],
        "dir1": [round(float(curve.dir1[i]), 5) for i in index],
        "threshold": [finite(curve.thresholds[i]) for i in index],
    }


def _headline_statistics(threshold: float, margin: float | None) -> dict:
    """Statistics whose bootstrap intervals we report, all at the SAME frozen decision rule."""
    return {
        "far": lambda s: m.operating_point(s, threshold, margin)["far"],
        "tar": lambda s: m.operating_point(s, threshold, margin)["tar"],
        "dir1": lambda s: m.operating_point(s, threshold, margin)["dir_at_rank"]["1"],
        "f1": lambda s: m.operating_point(s, threshold, margin)["f1"],
    }


def _as_confidence_scores(qs: m.QueryScores, model: ConfidenceModel) -> m.QueryScores:
    """Replace the similarity by the calibrated confidence (and drop the margin rule)."""
    margin = np.where(np.isfinite(qs.margin), qs.margin, 0.0)
    confidence = model.predict_many(qs.top1_score, margin)
    return m.QueryScores(qs.is_known, confidence, np.full(len(qs), np.inf), qs.top1_correct, qs.true_rank, qs.cluster)


def evaluate_variant(
    spec: VariantSpec,
    calibration: ScoredSplit,
    test: ScoredSplit,
    target: OperatingTarget,
    *,
    calibration_hard: np.ndarray,
    test_hard: np.ndarray,
    far_grid: tuple[float, ...],
    bootstrap_samples: int,
    seed: int,
    fitted_on: str,
) -> dict:
    cal_qs, test_qs = calibration.qs, test.qs
    result: dict = {"variant": spec.key, "seed": seed, "status": "ok"}
    result["closed_set"] = {
        "rank1": test.cmc[0] if test.cmc else None,
        "rank5": test.cmc[4] if len(test.cmc) >= 5 else None,
        "cmc": test.cmc,
        "mAP": test.mean_ap,
        "queries_used": test.qs.n_known,
        "dropped_same_camera_only": test.dropped_known_queries,
    }

    # ---- no rejection: the nearest-neighbour baseline ------------------------------
    if spec.rejection == "none":
        everything = float("-inf")
        result["selected"] = None
        result["test"] = m.operating_point(test_qs, everything)
        result["hard_subset"] = {"test": m.operating_point(test_qs.subset(np.flatnonzero(test_hard)), everything)}
        result["score_histogram"] = m.score_histogram(test_qs)
        return result

    # ---- choose the rule on the CALIBRATION split ------------------------------------
    confidence_model = None
    working_cal, working_test = cal_qs, test_qs
    if spec.rejection == "confidence":
        usable = np.isfinite(cal_qs.top1_score)
        confidence_model = ConfidenceModel.fit(
            cal_qs.top1_score[usable],
            np.where(np.isfinite(cal_qs.margin), cal_qs.margin, 0.0)[usable],
            (cal_qs.is_known & cal_qs.top1_correct)[usable],
            fitted_on=fitted_on,
        )
        working_cal = _as_confidence_scores(cal_qs, confidence_model)
        working_test = _as_confidence_scores(test_qs, confidence_model)

    selected = select_operating_point(working_cal, target, use_margin=spec.rejection == "threshold_margin")
    threshold, margin = selected.threshold, selected.min_margin
    result["selected"] = selected.to_dict()
    result["score_scale"] = "calibrated confidence" if confidence_model else "cosine similarity"

    # ---- frozen rule applied to the held-out test split ------------------------------
    point = m.operating_point(working_test, threshold, margin)
    point["confidence_intervals"] = m.cluster_bootstrap_ci(
        working_test, _headline_statistics(threshold, margin), n_boot=bootstrap_samples, seed=seed
    )
    result["test"] = point

    curve = m.roc_curve(working_test, min_margin=margin)
    result["curve"] = _downsample_curve(curve)
    result["auroc"] = curve.auc("tar")  # known-vs-unknown detection (threshold-free)
    result["auoscr"] = curve.auc("dir1")  # open-set classification rate (threshold-free)
    # Curve-based numbers sweep the threshold on the TEST data itself: they describe the best the
    # scores allow, but are not a pre-registered operating point. They are labelled as such in the UI.
    result["curve_operating_points"] = [
        {**m.recall_at_far(curve, far, "tar"), "dir1": m.recall_at_far(curve, far, "dir1")["recall"]}
        for far in far_grid
    ]

    # ---- low inter-class variance: the same frozen rule on the same-clothing subset ------
    hard_test = working_test.subset(np.flatnonzero(test_hard))
    hard = {"test": m.operating_point(hard_test, threshold, margin)}
    if hard_test.n_known and hard_test.n_unknown:
        hard["test"]["confidence_intervals"] = m.cluster_bootstrap_ci(
            hard_test, {"far": lambda s: m.operating_point(s, threshold, margin)["far"]},
            n_boot=bootstrap_samples, seed=seed + 1,
        )
    hard_cal = working_cal.subset(np.flatnonzero(calibration_hard))
    if hard_cal.n_known >= 10 and hard_cal.n_unknown >= 10:
        # What WOULD we have had to do to meet the same target on look-alikes only?
        aware = select_operating_point(hard_cal, target, use_margin=spec.rejection == "threshold_margin")
        hard["hard_aware_calibration"] = {
            "selected": aware.to_dict(),
            "test": m.operating_point(hard_test, aware.threshold, aware.min_margin)
            if aware.threshold is not None and hard_test.n_known and hard_test.n_unknown
            else None,
            "note": "Threshold re-selected on the calibration look-alike subset. Compare its recall with the "
                    "general rule to see the price of holding the same target on look-alikes.",
        }
    result["hard_subset"] = hard

    result["score_histogram"] = m.score_histogram(working_test)
    if confidence_model is not None:
        correct = (test_qs.is_known & test_qs.top1_correct).astype(float)
        probability = confidence_model.predict_many(test_qs.top1_score, np.where(np.isfinite(test_qs.margin), test_qs.margin, 0.0))
        result["confidence_model"] = {
            **confidence_model.to_dict(),
            "quality_on_test": m.calibration_report(probability, correct),
            "meaning": "P(the top-1 candidate is the correct enrolled identity | similarity, margin), "
                       "under the known:unknown mix of the calibration split.",
        }
    return result


# --------------------------------------------------------------------------
# Combining several seeds
# --------------------------------------------------------------------------

_HEADLINES = {
    "far": ("test", "far"),
    "tar": ("test", "tar"),
    "dir1": ("test", "dir_at_rank", "1"),
    "precision": ("test", "precision"),
    "f1": ("test", "f1"),
    "auroc": ("auroc",),
    "auoscr": ("auoscr",),
    "rank1": ("closed_set", "rank1"),
    "rank5": ("closed_set", "rank5"),
    "mAP": ("closed_set", "mAP"),
    "hard_far": ("hard_subset", "test", "far"),
    "hard_dir1": ("hard_subset", "test", "dir_at_rank", "1"),
    "calibration_far": ("selected", "calibration", "far"),
    "calibration_dir1": ("selected", "calibration", "dir_at_rank", "1"),
    "threshold": ("selected", "threshold"),
    "min_margin": ("selected", "min_margin"),
}


def _dig(data: dict | None, path: tuple[str, ...]):
    for key in path:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def summarise_seeds(per_seed: list[dict]) -> dict:
    """Mean and standard deviation of the headline metrics across seeds (None where undefined)."""
    summary = {}
    for name, path in _HEADLINES.items():
        values = [v for v in (_dig(r, path) for r in per_seed) if isinstance(v, int | float) and np.isfinite(v)]
        summary[name] = {
            "mean": float(np.mean(values)) if values else None,
            "std": float(np.std(values, ddof=1)) if len(values) > 1 else None,
            "n_seeds": len(values),
        }
    summary["targets_achieved"] = sum(1 for r in per_seed if (_dig(r, ("selected", "target_achieved")) is True))
    summary["n_seeds_total"] = len(per_seed)
    return summary
