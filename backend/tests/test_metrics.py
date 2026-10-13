"""
Metric tests on a toy table whose answers were worked out by hand.

Known queries (5)                         Unknown queries (4)
  K1 score .90 margin .30 correct rank1     U1 score .75 margin .10
  K2 score .80 margin .20 correct rank1     U2 score .50 margin .05
  K3 score .70 margin .05 WRONG   rank2     U3 score .30 margin .01
  K4 score .60 margin .10 correct rank1     U4 score .65 margin .08
  K5 score .40 margin .02 WRONG   rank3
"""

import numpy as np
import pytest

from app.evaluation import metrics as m


def toy() -> m.QueryScores:
    return m.QueryScores(
        is_known=np.array([1, 1, 1, 1, 1, 0, 0, 0, 0], dtype=bool),
        top1_score=np.array([0.90, 0.80, 0.70, 0.60, 0.40, 0.75, 0.50, 0.30, 0.65]),
        margin=np.array([0.30, 0.20, 0.05, 0.10, 0.02, 0.10, 0.05, 0.01, 0.08]),
        top1_correct=np.array([1, 1, 0, 1, 0, 0, 0, 0, 0], dtype=bool),
        true_rank=np.array([1, 1, 2, 1, 3, 0, 0, 0, 0]),
        cluster=np.array([1, 2, 3, 4, 5, 101, 102, 103, 104]),
    )


# ------------------------------------------------------------- one operating point
def test_operating_point_threshold_only():
    point = m.operating_point(toy(), threshold=0.65)
    counts = point["counts"]
    assert counts["known_accepted"] == 3 and counts["known_accepted_correct"] == 2
    assert counts["unknown_accepted"] == 2
    assert point["far"] == pytest.approx(2 / 4)  # denominator = ALL unknown queries
    assert point["tar"] == pytest.approx(3 / 5)  # denominator = ALL known queries
    assert point["frr"] == pytest.approx(2 / 5)
    assert point["dir_at_rank"]["1"] == pytest.approx(2 / 5)  # accepted AND correct
    assert point["dir_at_rank"]["5"] == pytest.approx(3 / 5)  # K3 is accepted with the true id at rank 2
    assert point["precision"] == pytest.approx(2 / 5)  # 2 correct out of 5 accepted
    assert point["recall"] == pytest.approx(2 / 5)
    assert point["f1"] == pytest.approx(2 / 5)


def test_operating_point_with_margin_rule():
    point = m.operating_point(toy(), threshold=0.65, min_margin=0.10)
    assert point["counts"]["known_accepted"] == 2 and point["counts"]["unknown_accepted"] == 1
    assert point["far"] == pytest.approx(1 / 4)
    assert point["precision"] == pytest.approx(2 / 3)


def test_unknown_query_is_falsely_accepted_when_any_identity_is_named():
    # U1 (score .75) is accepted at threshold .7 even though no identity is truly its match.
    point = m.operating_point(toy(), threshold=0.70)
    assert point["counts"]["unknown_accepted"] == 1


def test_nothing_accepted_gives_undefined_precision_not_a_crash():
    point = m.operating_point(toy(), threshold=0.99)
    assert point["far"] == 0 and point["tar"] == 0
    assert point["precision"] is None and point["f1"] is None


def test_empty_denominators_are_none_not_zero():
    only_known = toy().subset(np.arange(5))
    assert m.operating_point(only_known, 0.5)["far"] is None


# --------------------------------------------------------------------- the curve
def test_roc_points_and_area_match_hand_calculation():
    curve = m.roc_curve(toy())
    assert curve.thresholds[0] == np.inf and curve.thresholds[-1] == -np.inf
    assert curve.far[0] == 0 and curve.tar[0] == 0  # accept nothing
    assert curve.far[-1] == 1 and curve.tar[-1] == 1  # accept everything
    assert curve.auc("tar") == pytest.approx(0.70)  # = P(known score > unknown score) = 14/20
    assert curve.auc("dir1") == pytest.approx(0.50)  # AUOSCR


def test_curve_values_are_monotone_in_the_threshold():
    curve = m.roc_curve(toy())
    assert np.all(np.diff(curve.far) >= 0) and np.all(np.diff(curve.tar) >= 0)
    assert np.all(np.diff(curve.dir1) >= 0)


def test_no_rejection_endpoint_has_far_one_and_closed_set_accuracy():
    curve = m.roc_curve(toy())
    assert curve.far[-1] == 1.0
    assert curve.dir1[-1] == pytest.approx(3 / 5)  # = rank-1 accuracy of the closed-set baseline


def test_roc_requires_both_kinds_of_queries():
    with pytest.raises(ValueError):
        m.roc_curve(toy().subset(np.arange(5)))


def test_recall_at_fixed_far():
    curve = m.roc_curve(toy())
    result = m.recall_at_far(curve, target_far=0.25, which="tar")
    assert result["recall"] == pytest.approx(0.6)
    assert result["threshold"] == pytest.approx(0.70)
    assert result["achieved_far"] == pytest.approx(0.25)
    assert m.recall_at_far(curve, 0.25, "dir1")["recall"] == pytest.approx(0.4)


def test_zero_far_target_returns_the_honest_best_recall():
    result = m.recall_at_far(m.roc_curve(toy()), target_far=0.0, which="tar")
    assert result["achieved_far"] == 0.0
    assert result["recall"] == pytest.approx(0.4)  # K1 and K2 score above every unknown query


def test_far_at_fixed_recall_and_unreachable_targets_are_reported_honestly():
    curve = m.roc_curve(toy())
    reached = m.far_at_recall(curve, 0.8, "tar")
    assert reached["achievable"] and reached["far"] == pytest.approx(0.5)
    assert reached["threshold"] == pytest.approx(0.60)
    unreachable = m.far_at_recall(curve, 0.7, "dir1")  # best possible DIR@1 is only 0.6
    assert unreachable["achievable"] is False and unreachable["far"] is None


def test_margin_rule_changes_the_curve():
    with_margin = m.roc_curve(toy(), min_margin=0.10)
    # K3 and K5 can never be accepted now, so TAR just below the no-rejection point is at most 3/5.
    assert with_margin.tar[-2] == pytest.approx(3 / 5)


# ------------------------------------------------------------- closed-set metrics
def test_cmc_rank_accuracy():
    ranks = toy().true_rank
    assert m.cmc(ranks, max_rank=3) == pytest.approx([0.6, 0.8, 1.0])


def test_average_precision_known_cases():
    assert m.average_precision(np.array([True, False, True])) == pytest.approx((1 + 2 / 3) / 2)
    assert m.average_precision(np.array([False, False, True])) == pytest.approx(1 / 3)
    assert m.average_precision(np.array([False, False])) is None


def test_mean_average_precision_respects_ignored_images():
    similarity = np.array([[0.9, 0.8, 0.7, 0.1]])
    gallery_ids = np.array([5, 9, 5, 9])
    query_ids = np.array([5])
    assert m.mean_average_precision(similarity, query_ids, gallery_ids) == pytest.approx((1 + 2 / 3) / 2)
    # Ignoring the first (same-camera) image leaves ranking [9,5,9] -> AP = 1/2.
    ignore = np.array([[True, False, False, False]])
    assert m.mean_average_precision(similarity, query_ids, gallery_ids, ignore) == pytest.approx(0.5)


# ------------------------------------------------------- uncertainty and honesty
def test_wilson_upper_bound_with_zero_events_matches_closed_form():
    z = 1.645
    assert m.wilson_upper_bound(0, 100) == pytest.approx(z * z / (100 + z * z), rel=1e-6)
    assert m.wilson_upper_bound(0, 0) is None
    assert m.wilson_upper_bound(10, 100) > 0.10  # upper bound is above the observed rate


def test_rule_of_three_sample_size():
    assert m.minimum_unknown_queries_for_far(0.01) == 300
    assert m.minimum_unknown_queries_for_far(0.001) == 3000


def test_bootstrap_is_reproducible_and_brackets_the_estimate():
    rng = np.random.default_rng(3)
    n_known, n_unknown = 300, 300
    qs = m.QueryScores(
        is_known=np.r_[np.ones(n_known, bool), np.zeros(n_unknown, bool)],
        top1_score=np.r_[rng.normal(0.8, 0.1, n_known), rng.normal(0.55, 0.1, n_unknown)],
        margin=np.full(n_known + n_unknown, 0.2),
        top1_correct=np.r_[np.ones(n_known, bool), np.zeros(n_unknown, bool)],
        true_rank=np.r_[np.ones(n_known, int), np.zeros(n_unknown, int)],
        cluster=np.arange(n_known + n_unknown) // 3,
    )
    stats = {
        "far": lambda s: m.operating_point(s, 0.7)["far"],
        "tar": lambda s: m.operating_point(s, 0.7)["tar"],
    }
    first = m.cluster_bootstrap_ci(qs, stats, n_boot=200, seed=7)
    second = m.cluster_bootstrap_ci(qs, stats, n_boot=200, seed=7)
    assert first == second  # same seed -> identical intervals
    point = m.operating_point(qs, 0.7)
    assert first["far"]["low"] <= point["far"] <= first["far"]["high"]
    assert first["tar"]["low"] <= point["tar"] <= first["tar"]["high"]
    assert m.cluster_bootstrap_ci(qs, stats, n_boot=0, seed=7) == {"far": None, "tar": None}


def test_calibration_report_on_perfectly_calibrated_forecast():
    probability = np.full(10, 0.1)
    outcome = np.array([1] + [0] * 9)
    report = m.calibration_report(probability, outcome)
    assert report["ece"] == pytest.approx(0.0, abs=1e-9)
    assert report["brier"] == pytest.approx((9 * 0.01 + 0.81) / 10)


def test_calibration_report_detects_overconfidence():
    report = m.calibration_report(np.full(100, 0.9), np.r_[np.ones(50), np.zeros(50)])
    assert report["ece"] == pytest.approx(0.4)


def test_score_histogram_counts_every_query_once():
    hist = m.score_histogram(toy(), bins=10)
    assert sum(hist["known_correct"]) == 3 and sum(hist["known_wrong"]) == 2 and sum(hist["unknown"]) == 4


def test_mismatched_columns_are_rejected():
    with pytest.raises(ValueError):
        m.QueryScores(np.ones(3, bool), np.ones(2), np.ones(3), np.ones(3, bool), np.ones(3, int), np.ones(3, int))
