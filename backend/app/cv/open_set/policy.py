"""
The decision policy: the rules that turn scores into an outcome.

In plain words: a policy is a small, versioned bundle of settings -

    accept_threshold   "the best candidate must be at least THIS similar"
    min_margin         (optional) "...and must beat the runner-up by at least THIS much"
    margin_action      what to do when the margin rule fails: send to REVIEW or just REJECT
    review_on_quality_flags   send blurry / cut-off / tiny crops to REVIEW

Every change creates a NEW version, so any past decision can be traced to the
exact rules that produced it. ``status`` says honestly how trustworthy the
numbers are:

    unvalidated   a starting value nobody has checked
    experimental  chosen by a human, not derived from data
    calibrated    selected on a held-out calibration split by the calibration workflow
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass

from ...core.errors import ValidationFailed


class Outcome(str, enum.Enum):
    ACCEPTED = "accepted"  # a supported enrolled identity passed every rule
    UNKNOWN = "unknown"  # no enrolled identity is supported by the evidence
    REVIEW_REQUIRED = "review_required"  # ambiguous or low quality: a human should look
    PROCESSING_ERROR = "processing_error"  # the input could not be processed reliably


class PolicyStatus(str, enum.Enum):
    UNVALIDATED = "unvalidated"
    EXPERIMENTAL = "experimental"
    CALIBRATED = "calibrated"


class MarginAction(str, enum.Enum):
    REVIEW = "review"
    REJECT = "reject"


THRESHOLD_RANGE = (0.0, 1.0)
MARGIN_RANGE = (0.0, 1.0)


class BodyOnlyAction(str, enum.Enum):
    """What to do when only clothing/body evidence is available and it passes the body threshold."""

    REVIEW = "review"  # a human decides: clothing alone is not enough for an automatic MATCH (default)
    ACCEPT = "accept"  # the body-only behaviour of the original design


@dataclass(frozen=True)
class MultiCuePolicy:
    """Rules for using the FACE as well as the whole body.

    face_accept_threshold   "the best face must be at least THIS similar" (cosine)
    face_review_band        a face score within this distance BELOW the threshold is sent to REVIEW rather than UNKNOWN
    body_only_action        see ``BodyOnlyAction``

    ``DecisionPolicy.accept_threshold`` keeps meaning "body similarity needed"; this block adds the face rules on top.

    Where the defaults come from (measured, see docs/FACE_AND_BODY_MATCHING.md and docs/results/face_lfw.json): on 4.5 million
    pairs of DIFFERENT people from LFW, a face score of 0.465 or more occurred in 1 pair per 100,000 (0.001 %), while 93 % of
    same-person pairs reach it. The face model's own card suggests 0.363, which about 1 stranger pair in 1,200 still reaches -
    too loose when a query is compared with every enrolled person and the best score wins. So 0.465 is the automatic-MATCH
    line, and the 0.10 band below it (about 0.365 - 0.465, the model card's own region) goes to a person instead of being
    decided by the machine. Both numbers are still UNVALIDATED for any particular camera or population.
    """

    face_accept_threshold: float = 0.465
    face_review_band: float = 0.10
    body_only_action: BodyOnlyAction = BodyOnlyAction.REVIEW

    def __post_init__(self) -> None:
        validate_multicue_values(self.face_accept_threshold, self.face_review_band)

    def to_dict(self) -> dict:
        return {"face_accept_threshold": self.face_accept_threshold, "face_review_band": self.face_review_band,
                "body_only_action": self.body_only_action.value}

    @classmethod
    def from_dict(cls, data: dict | None) -> MultiCuePolicy | None:
        if not data:
            return None
        return cls(float(data["face_accept_threshold"]), float(data["face_review_band"]), BodyOnlyAction(data["body_only_action"]))


@dataclass(frozen=True)
class DecisionPolicy:
    version: int
    accept_threshold: float
    min_margin: float | None = None
    margin_action: MarginAction = MarginAction.REVIEW
    review_on_quality_flags: bool = True
    status: PolicyStatus = PolicyStatus.UNVALIDATED
    multicue: MultiCuePolicy | None = None  # None = the original body-only behaviour

    def __post_init__(self) -> None:
        validate_policy_values(self.accept_threshold, self.min_margin)


def validate_multicue_values(face_accept_threshold: float, face_review_band: float) -> None:
    if not isinstance(face_accept_threshold, int | float) or not math.isfinite(face_accept_threshold) or not 0.0 < face_accept_threshold < 1.0:
        raise ValidationFailed("The face threshold must be a number between 0 and 1 (the model card suggests 0.363).")
    if not isinstance(face_review_band, int | float) or not math.isfinite(face_review_band) or not 0.0 <= face_review_band <= 0.5:
        raise ValidationFailed("The face review band must be a number between 0 and 0.5.")


def validate_policy_values(accept_threshold: float, min_margin: float | None) -> None:
    """Reject nonsense (NaN, out-of-range) before it can reach a decision."""
    low, high = THRESHOLD_RANGE
    if not isinstance(accept_threshold, int | float) or not math.isfinite(accept_threshold):
        raise ValidationFailed("The acceptance threshold must be a finite number.")
    if not low <= accept_threshold <= high:
        raise ValidationFailed(f"The acceptance threshold must be between {low} and {high}.")
    if min_margin is not None:
        low, high = MARGIN_RANGE
        if not isinstance(min_margin, int | float) or not math.isfinite(min_margin):
            raise ValidationFailed("The minimum margin must be a finite number.")
        if not low <= min_margin <= high:
            raise ValidationFailed(f"The minimum margin must be between {low} and {high}.")
