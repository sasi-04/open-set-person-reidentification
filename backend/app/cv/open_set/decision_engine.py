"""
The open-set decision engine.

In plain words: retrieval always returns *someone* as the nearest neighbour,
even for a stranger. This module decides whether that nearest neighbour is
actually SUPPORTED by the evidence. It is a pure function - scores in,
decision out - with no database, no web framework and no images, so it can be
tested exhaustively and reasoned about in a code review.

The rules, in order (the first one that applies wins):

  1. Empty gallery                      -> UNKNOWN   (nobody to match against)
  2. Quality flags (if the policy asks) -> REVIEW    (the evidence itself is shaky)
  3. top-1 similarity < threshold       -> UNKNOWN   (not alike enough to anyone)
  4. margin rule (if configured): top-1 minus top-2 < minimum margin
                                        -> REVIEW (default) or UNKNOWN (policy choice)
  5. otherwise                          -> ACCEPTED

Note what is NOT here: "UNKNOWN" does not mean "one specific unknown person",
and nothing is enrolled automatically. A rejected query stays a rejected query.

Four different numbers appear in a Decision and must never be confused:
``top1_score`` (retrieval similarity), ``margin`` (gap to the runner-up),
``calibrated_confidence`` (fitted probability, optional) - and the detector
score, which lives with the detection, not here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..retrieval.types import Candidate
from .confidence import ConfidenceModel
from .policy import DecisionPolicy, MarginAction, Outcome


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    reason_code: str  # stable machine-readable code
    reason: str  # human-readable sentence built from the real numbers
    accepted_reference_id: str | None  # set only when outcome == ACCEPTED
    top1_reference_id: str | None
    top1_score: float | None
    top2_score: float | None
    margin: float | None  # top1_score - top2_score (None if fewer than two candidates)
    accept_threshold: float
    min_margin: float | None
    policy_version: int
    policy_status: str
    candidates: tuple[Candidate, ...]
    calibrated_confidence: float | None = None
    quality_flags: tuple[str, ...] = ()
    # ---- filled only by multicue.decide_multicue (face + body matching); the body-only engine leaves the defaults
    basis: str = "body"  # which evidence produced top1_score / accept_threshold: "face" or "body"
    face_status: str | None = None  # not_used | usable | no_face | unusable | not_enrolled
    top1_face_score: float | None = None  # what the FACE says about the top-1 identity (None = not compared)
    top1_body_score: float | None = None  # what the BODY says about the top-1 identity
    face_threshold: float | None = None
    body_threshold: float | None = None


def decide(
    candidates: Sequence[Candidate],
    policy: DecisionPolicy,
    *,
    quality_flags: Sequence[str] = (),
    confidence_model: ConfidenceModel | None = None,
) -> Decision:
    # Deterministic order: best score first; equal scores keep their original order (stable sort).
    ranked = tuple(sorted(candidates, key=lambda candidate: -candidate.score))
    ranked = tuple(
        Candidate(index + 1, c.reference_id, c.score, c.best_image_uid, c.n_images)
        for index, c in enumerate(ranked)
    )

    top1 = ranked[0] if ranked else None
    top2 = ranked[1] if len(ranked) > 1 else None
    margin = (top1.score - top2.score) if top1 and top2 else None
    confidence = (
        confidence_model.predict(top1.score, margin) if (confidence_model and top1 and margin is not None) else None
    )

    def build(outcome: Outcome, code: str, reason: str) -> Decision:
        return Decision(
            outcome=outcome,
            reason_code=code,
            reason=reason,
            accepted_reference_id=top1.reference_id if outcome is Outcome.ACCEPTED and top1 else None,
            top1_reference_id=top1.reference_id if top1 else None,
            top1_score=top1.score if top1 else None,
            top2_score=top2.score if top2 else None,
            margin=margin,
            accept_threshold=policy.accept_threshold,
            min_margin=policy.min_margin,
            policy_version=policy.version,
            policy_status=policy.status.value,
            candidates=ranked,
            calibrated_confidence=confidence,
            quality_flags=tuple(quality_flags),
        )

    # Rule 1 - nothing enrolled.
    if top1 is None:
        return build(Outcome.UNKNOWN, "empty_gallery", "The gallery is empty, so there is no one to match against.")

    # Rule 2 - poor evidence quality.
    if quality_flags and policy.review_on_quality_flags:
        flags = ", ".join(quality_flags)
        return build(
            Outcome.REVIEW_REQUIRED,
            "quality_review",
            f"Image quality is inadequate for an automatic decision ({flags}). "
            f"Closest candidate '{top1.reference_id}' scored {top1.score:.3f}.",
        )

    # Rule 3 - not similar enough to anyone.
    if top1.score < policy.accept_threshold:
        return build(
            Outcome.UNKNOWN,
            "below_threshold",
            f"No supported match: the closest candidate '{top1.reference_id}' scored {top1.score:.3f}, "
            f"below the acceptance threshold {policy.accept_threshold:.3f}.",
        )

    # Rule 4 - similar enough, but is the winner clearly ahead of the runner-up?
    if policy.min_margin is not None and margin is not None and margin < policy.min_margin:
        detail = (
            f"'{top1.reference_id}' scored {top1.score:.3f} but the runner-up '{top2.reference_id}' "
            f"scored {top2.score:.3f}: the margin {margin:.3f} is below the required {policy.min_margin:.3f}."
        )
        if policy.margin_action is MarginAction.REVIEW:
            return build(Outcome.REVIEW_REQUIRED, "ambiguous_margin", f"Ambiguous match. {detail}")
        return build(Outcome.UNKNOWN, "ambiguous_margin_rejected", f"Rejected as ambiguous. {detail}")

    # Rule 5 - every configured rule passed.
    parts = [f"'{top1.reference_id}' scored {top1.score:.3f}, at or above the threshold {policy.accept_threshold:.3f}"]
    if policy.min_margin is not None:
        if margin is None:
            parts.append("the margin rule was not applicable (only one identity is enrolled)")
        else:
            parts.append(f"leads the runner-up by {margin:.3f} (required {policy.min_margin:.3f})")
    return build(Outcome.ACCEPTED, "accepted", "Accepted: " + "; ".join(parts) + ".")
