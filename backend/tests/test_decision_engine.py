"""
Decision-engine tests.

These use hand-written candidate lists (synthetic scores) so every expected
outcome can be verified by reading the test. They prove the RULES behave as
documented; they say nothing about real-world accuracy.
"""

import pytest

from app.core.errors import ValidationFailed
from app.cv.open_set.confidence import ConfidenceModel
from app.cv.open_set.decision_engine import decide
from app.cv.open_set.policy import DecisionPolicy, MarginAction, Outcome, PolicyStatus
from app.cv.retrieval.types import Candidate


def cands(*scores: float) -> list[Candidate]:
    return [Candidate(rank=i + 1, reference_id=f"P-{i + 1:03d}", score=s) for i, s in enumerate(scores)]


def policy(threshold=0.7, margin=None, action=MarginAction.REVIEW, quality=True) -> DecisionPolicy:
    return DecisionPolicy(
        version=3,
        accept_threshold=threshold,
        min_margin=margin,
        margin_action=action,
        review_on_quality_flags=quality,
        status=PolicyStatus.EXPERIMENTAL,
    )


def test_top_candidate_is_not_automatically_accepted():
    # P-001 is the nearest neighbour, but 0.55 is far below the 0.70 threshold.
    decision = decide(cands(0.55, 0.50, 0.40), policy())
    assert decision.outcome is Outcome.UNKNOWN
    assert decision.accepted_reference_id is None
    assert decision.top1_reference_id == "P-001"  # still reported as the closest candidate
    assert decision.reason_code == "below_threshold"


def test_score_at_or_above_threshold_is_accepted():
    assert decide(cands(0.80, 0.30), policy()).outcome is Outcome.ACCEPTED
    # exactly equal to the threshold counts as accepted ("at or above")
    assert decide(cands(0.70, 0.30), policy()).outcome is Outcome.ACCEPTED


def test_accepted_decision_names_the_identity():
    decision = decide(cands(0.9, 0.2), policy())
    assert decision.accepted_reference_id == "P-001"


def test_threshold_change_changes_the_decision():
    scores = cands(0.75, 0.30)
    assert decide(scores, policy(threshold=0.70)).outcome is Outcome.ACCEPTED
    assert decide(scores, policy(threshold=0.80)).outcome is Outcome.UNKNOWN


def test_empty_gallery_is_unknown_with_clear_reason():
    decision = decide([], policy())
    assert decision.outcome is Outcome.UNKNOWN
    assert decision.reason_code == "empty_gallery"
    assert decision.top1_score is None and decision.candidates == ()


def test_ambiguous_margin_triggers_review_by_default():
    # 0.80 passes the threshold, but the runner-up (0.78) is practically tied.
    decision = decide(cands(0.80, 0.78), policy(margin=0.05))
    assert decision.outcome is Outcome.REVIEW_REQUIRED
    assert decision.reason_code == "ambiguous_margin"
    assert decision.margin == pytest.approx(0.02)
    assert decision.accepted_reference_id is None


def test_ambiguous_margin_can_be_configured_to_reject():
    decision = decide(cands(0.80, 0.78), policy(margin=0.05, action=MarginAction.REJECT))
    assert decision.outcome is Outcome.UNKNOWN
    assert decision.reason_code == "ambiguous_margin_rejected"


def test_clear_margin_passes_margin_rule():
    decision = decide(cands(0.85, 0.60), policy(margin=0.05))
    assert decision.outcome is Outcome.ACCEPTED
    assert decision.margin == pytest.approx(0.25)


def test_margin_rule_not_applied_with_a_single_candidate():
    decision = decide(cands(0.85), policy(margin=0.30))
    assert decision.outcome is Outcome.ACCEPTED
    assert decision.margin is None
    assert "not applicable" in decision.reason


def test_margin_rule_never_rescues_a_score_below_threshold():
    decision = decide(cands(0.60, 0.10), policy(threshold=0.7, margin=0.05))
    assert decision.outcome is Outcome.UNKNOWN  # a big margin does not override the threshold


def test_quality_flags_trigger_review_even_for_strong_scores():
    decision = decide(cands(0.95, 0.20), policy(), quality_flags=["blurry"])
    assert decision.outcome is Outcome.REVIEW_REQUIRED
    assert decision.reason_code == "quality_review"
    assert decision.quality_flags == ("blurry",)


def test_quality_review_can_be_disabled_by_policy():
    decision = decide(cands(0.95, 0.20), policy(quality=False), quality_flags=["blurry"])
    assert decision.outcome is Outcome.ACCEPTED


def test_ranking_is_deterministic_and_reranks_unsorted_input():
    shuffled = [
        Candidate(1, "B", 0.40),
        Candidate(2, "A", 0.90),
        Candidate(3, "C", 0.40),  # tie with B: original order must be preserved
    ]
    first = decide(shuffled, policy())
    second = decide(list(shuffled), policy())
    assert [c.reference_id for c in first.candidates] == ["A", "B", "C"]
    assert [c.rank for c in first.candidates] == [1, 2, 3]
    assert first == second


def test_explanation_matches_the_underlying_scores():
    decision = decide(cands(0.812, 0.655), policy(threshold=0.7, margin=0.1))
    assert "0.812" in decision.reason and "0.700" in decision.reason and "0.157" in decision.reason
    assert decision.top1_score == 0.812 and decision.top2_score == 0.655


def test_decision_records_the_policy_that_made_it():
    decision = decide(cands(0.9, 0.1), policy())
    assert decision.policy_version == 3
    assert decision.policy_status == "experimental"
    assert decision.accept_threshold == 0.7


def test_retrieval_score_and_calibrated_confidence_are_separate_fields():
    model = ConfidenceModel(2.0, 1.0, 0.0, 0.7, 0.1, 0.2, 0.1, 100, 50, "unit test")
    decision = decide(cands(0.9, 0.3), policy(), confidence_model=model)
    assert decision.top1_score == 0.9
    assert decision.calibrated_confidence is not None
    assert decision.calibrated_confidence != decision.top1_score


def test_confidence_is_absent_without_a_fitted_model():
    assert decide(cands(0.9, 0.3), policy()).calibrated_confidence is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1, 1.5])
def test_invalid_thresholds_are_rejected(bad):
    with pytest.raises(ValidationFailed):
        DecisionPolicy(version=1, accept_threshold=bad)


@pytest.mark.parametrize("bad", [float("nan"), -0.01, 1.2])
def test_invalid_margins_are_rejected(bad):
    with pytest.raises(ValidationFailed):
        DecisionPolicy(version=1, accept_threshold=0.5, min_margin=bad)
