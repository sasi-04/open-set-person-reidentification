"""
The threshold sandbox: same rule as the live engine, honest about what it is, never writes policy.

The most important test is the first one: for many random score/margin/threshold combinations the
sandbox's vectorised rule must give EXACTLY the outcome the real decision engine gives.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.cv.open_set.decision_engine import decide
from app.cv.open_set.policy import DecisionPolicy, MarginAction, Outcome
from app.cv.retrieval.types import Candidate
from app.evaluation import metrics as m
from app.evaluation import sandbox
from app.evaluation.calibration import OperatingTarget
from app.evaluation.datasets import inspect_dataset
from app.evaluation.protocol import ProtocolConfig
from app.evaluation.runner import EvaluationRequest, run_evaluation
from tests.test_evaluation_pipeline import FakeExtractor, factory_for, make_dataset

OUTCOME_NAME = {Outcome.ACCEPTED: "accepted", Outcome.REVIEW_REQUIRED: "review_required", Outcome.UNKNOWN: "unknown"}


def _live_engine_outcome(top1: float, top2: float | None, threshold: float, min_margin: float | None, action: str) -> str:
    candidates = [Candidate(1, "A", top1, None, 1)]
    if top2 is not None:
        candidates.append(Candidate(2, "B", top2, None, 1))
    policy = DecisionPolicy(version=1, accept_threshold=threshold, min_margin=min_margin, margin_action=MarginAction(action))
    return OUTCOME_NAME[decide(candidates, policy).outcome]


@pytest.mark.parametrize("action", ["review", "reject"])
@pytest.mark.parametrize("min_margin", [None, 0.0, 0.05, 0.2])
def test_sandbox_rule_matches_the_live_decision_engine_on_random_cases(action, min_margin):
    rng = np.random.default_rng(11)
    top1 = rng.uniform(0.2, 1.0, 400)
    top2 = np.minimum(top1, rng.uniform(0.1, 1.0, 400))  # the runner-up never beats the winner
    has_runner_up = rng.random(400) > 0.1  # some queries have only one enrolled person to compare with
    margin = np.where(has_runner_up, top1 - top2, np.inf)
    threshold = 0.62

    got = sandbox.decide_rows(top1, margin, threshold, min_margin, action)
    for i in range(len(top1)):
        expected = _live_engine_outcome(top1[i], top2[i] if has_runner_up[i] else None, threshold, min_margin, action)
        assert got[i] == expected, (top1[i], top2[i], has_runner_up[i])


def test_the_threshold_boundary_is_inclusive_like_the_live_engine():
    assert sandbox.decide_rows(np.array([0.7]), np.array([np.inf]), 0.7, None, "review")[0] == "accepted"
    assert sandbox.decide_rows(np.array([0.6999]), np.array([np.inf]), 0.7, None, "review")[0] == "unknown"


# ------------------------------------------------------------------------------ a small hand-made table
def _rows():
    #            who they are          best score   margin   right person?
    people = [("k1", True, "k1", 0.90, 0.30, True), ("k2", True, "k2", 0.75, 0.01, True), ("k3", True, "other", 0.74, 0.20, False),
              ("k4", True, "k4", 0.50, 0.40, True), ("s1", False, "k1", 0.80, 0.25, False), ("s2", False, "k2", 0.60, 0.30, False),
              ("s3", False, "k3", 0.30, 0.10, False), ("s4", False, "k1", 0.72, 0.02, False)]
    return {
        "n": len(people), "ref": [f"{p[0]}.jpg" for p in people], "identity": [p[0] for p in people],
        "is_known": [p[1] for p in people], "top1_identity": [p[2] for p in people], "top1_score": [p[3] for p in people],
        "margin": [p[4] for p in people], "top1_correct": [p[5] for p in people],
        "true_rank": [1 if p[1] and p[5] else (2 if p[1] else 0) for p in people],
    }


def _payload():
    rows = _rows()
    return {"version": 1, "seed": 0, "embedding_source": "plain", "model_fingerprint": "fake-0",
            "reference": {"variant": "thr", "threshold": 0.70, "min_margin": None, "margin_action": "review"},
            "splits": {"calibration": rows, "test": rows}}


def test_confusion_counts_follow_their_definitions():
    result = sandbox.explore(_payload(), "calibration", threshold=0.70, min_margin=None, margin_action="review")
    c = result["trial"]["confusion"]
    # accepted at 0.70: k1 (0.90 correct), k2 (0.75 correct), k3 (0.74 WRONG person), s1 (0.80 stranger), s4 (0.72 stranger)
    assert (c["true_accepts"], c["wrong_identity_accepts"], c["false_accepts"]) == (2, 1, 2)
    assert (c["false_rejects"], c["true_rejects"]) == (1, 2)  # k4 turned away; s2, s3 correctly rejected
    metrics = result["trial"]["metrics"]
    assert metrics["far"] == 2 / 4 and metrics["counts"]["known_queries"] == 4
    assert result["trial"]["outcome_counts"] == {"accepted": 5, "review_required": 0, "unknown": 3}


def test_the_margin_rule_moves_ambiguous_queries_to_review_and_counts_them_as_not_accepted():
    result = sandbox.explore(_payload(), "calibration", threshold=0.70, min_margin=0.05, margin_action="review")
    # k2 (margin 0.01) and s4 (margin 0.02) now need review: one enrolled person and one stranger
    c = result["trial"]["confusion"]
    assert (c["known_sent_to_review"], c["unknown_sent_to_review"]) == (1, 1)
    assert result["trial"]["metrics"]["far"] == 1 / 4  # only s1 is still falsely accepted
    assert result["trial"]["outcome_counts"]["review_required"] == 2


def test_changed_decisions_are_listed_strangers_who_get_in_first():
    result = sandbox.explore(_payload(), "calibration", threshold=0.55, min_margin=None, margin_action="review")
    assert result["decisions_changed"] == 1 and result["changed_examples"][0]["ref"] == "s2.jpg"  # 0.60 stranger now accepted
    first = result["changed_examples"][0]
    assert (first["calibrated_rule"], first["trial_rule"]) == ("unknown", "accepted")


def test_a_stricter_threshold_never_raises_the_false_accept_rate_nor_the_recall():
    payload = _payload()
    far, recall = [], []
    for threshold in np.linspace(0.2, 0.95, 16):
        point = sandbox.explore(payload, "test", threshold=float(threshold), min_margin=None, margin_action="review")["trial"]["metrics"]
        far.append(point["far"])
        recall.append(point["dir_at_rank"]["1"])
    assert far == sorted(far, reverse=True) and recall == sorted(recall, reverse=True)


def test_the_sandbox_never_writes_policy_and_warns_on_the_test_split():
    payload = _payload()
    on_test = sandbox.explore(payload, "test", threshold=0.8, min_margin=None, margin_action="review")
    on_calibration = sandbox.explore(payload, "calibration", threshold=0.8, min_margin=None, margin_action="review")
    assert on_test["writes_policy"] is False and "tuning on the test set" in on_test["warning"]
    assert on_calibration["warning"] is None


def test_unknown_split_is_a_key_error():
    with pytest.raises(KeyError):
        sandbox.explore(_payload(), "dev", threshold=0.5, min_margin=None, margin_action="review")


def test_rows_roundtrip_into_the_same_metrics_the_evaluation_uses():
    qs = sandbox.to_query_scores(_rows())
    assert qs.n_known == 4 and qs.n_unknown == 4
    point = m.operating_point(qs, 0.70, None)
    assert point["counts"]["known_accepted"] == 3 and point["counts"]["unknown_accepted"] == 2


# ---------------------------------------------------------------------------- inside a real evaluation run
def test_an_evaluation_run_stores_the_sandbox_table_and_the_reference_is_its_calibrated_rule(tmp_path):
    info = inspect_dataset(make_dataset(tmp_path / "toy"))
    request = EvaluationRequest(
        dataset=info.name, seeds=(0,), target=OperatingTarget("fixed_recall", target_recall=0.5),
        variants=("nn_baseline", "thr", "thr_margin"),
        protocol=ProtocolConfig(dev_fraction=0.2, calibration_fraction=0.3, gallery_shots=2, max_images_per_identity=6),
        bootstrap_samples=10)
    result = run_evaluation(info, request, cache_dir=tmp_path / "cache", make_extractor=factory_for(FakeExtractor(noise=0.02)))
    payload = result["sandbox"]
    assert payload["embedding_source"] == "plain" and set(payload["splits"]) == {"calibration", "test"}
    selected = result["variants"]["thr_margin"]["per_seed"][0]["selected"]
    assert payload["reference"]["threshold"] == selected["threshold"] and payload["reference"]["variant"] == "thr_margin"

    # Re-applying the run's own rule through the sandbox reproduces the run's own test numbers exactly.
    replay = sandbox.explore(payload, "test", threshold=selected["threshold"], min_margin=selected["min_margin"], margin_action="review")
    reported = result["variants"]["thr_margin"]["per_seed"][0]["test"]
    assert replay["trial"]["metrics"]["far"] == reported["far"]
    assert replay["trial"]["metrics"]["dir_at_rank"]["1"] == reported["dir_at_rank"]["1"]
    assert replay["decisions_changed"] == 0
