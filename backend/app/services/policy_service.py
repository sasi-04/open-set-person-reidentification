"""
Versioned decision policy.

In plain words: the acceptance threshold and margin rule are stored in the
database as a list of numbered versions. Exactly one version is "active". A
change never edits a row - it adds a new version and switches the active flag -
so history is never lost and every decision can say "made under policy v7".
Every request reads the active version from the database, so a change takes
effect on the very next request (it is not cached in the browser or the server).
"""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..core.config import Settings
from ..core.errors import NotFound
from ..cv.open_set.confidence import ConfidenceModel
from ..cv.open_set.policy import DecisionPolicy, MarginAction, MultiCuePolicy, PolicyStatus, validate_policy_values
from ..db.models import PolicyVersion
from ..schemas.config import PolicyModel

STATUS_EXPLANATION = {
    "unvalidated": "A starting value nobody has checked. Run calibration before relying on it.",
    "experimental": "Set by a person, not derived from data on a held-out calibration split.",
    "calibrated": "Selected on a held-out calibration split by the calibration workflow (see the linked run).",
}


def ensure_default_policy(session: Session, settings: Settings) -> PolicyVersion:
    """First start: create version 1 from the configured default. It is labelled UNVALIDATED."""
    existing = session.scalar(select(PolicyVersion).where(PolicyVersion.is_active.is_(True)))
    if existing:
        return existing
    return create_version(
        session,
        accept_threshold=settings.default_accept_threshold,
        min_margin=None,
        margin_action="review",
        review_on_quality_flags=True,
        status=PolicyStatus.UNVALIDATED.value,
        role_name="system",
        note="Initial default from configuration. Not validated on any data.",
        multicue=MultiCuePolicy().to_dict() if settings.face_matching else None,
    )


def get_active(session: Session) -> PolicyVersion:
    row = session.scalar(select(PolicyVersion).where(PolicyVersion.is_active.is_(True)))
    if row is None:
        raise NotFound("No active decision policy exists.")
    return row


def to_policy(row: PolicyVersion) -> DecisionPolicy:
    return DecisionPolicy(
        version=row.version,
        accept_threshold=row.accept_threshold,
        min_margin=row.min_margin,
        margin_action=MarginAction(row.margin_action),
        review_on_quality_flags=row.review_on_quality_flags,
        status=PolicyStatus(row.status),
        multicue=MultiCuePolicy.from_dict(row.multicue),
    )


def effective_policy(runtime, row: PolicyVersion) -> tuple[DecisionPolicy, str | None]:
    """The policy to apply right now, plus a note when it had to be reduced.

    A policy may ask for face matching while the face models are not loaded (not downloaded, or switched off). The system
    then does what it did before faces existed - match on the body - and SAYS so, instead of failing or silently pretending.
    """
    policy = to_policy(row)
    if policy.multicue is not None and runtime.face_engine is None:
        from dataclasses import replace

        return replace(policy, multicue=None), (
            "Face matching is enabled in the policy but the face models are not loaded, so only the body is compared. "
            + (runtime.face_error or "")
        ).strip()
    return policy, None


def confidence_model_for(row: PolicyVersion, current_fingerprint: str | None) -> ConfidenceModel | None:
    """A confidence model is only valid for the embedding model it was fitted on."""
    if not row.confidence_model or row.model_fingerprint != current_fingerprint:
        return None
    return ConfidenceModel.from_dict(row.confidence_model)


def create_version(
    session: Session,
    *,
    accept_threshold: float,
    min_margin: float | None,
    margin_action: str,
    review_on_quality_flags: bool,
    status: str,
    role_name: str,
    note: str = "",
    calibration_run_id: str | None = None,
    confidence_model: dict | None = None,
    model_fingerprint: str | None = None,
    multicue: dict | None = None,
) -> PolicyVersion:
    validate_policy_values(accept_threshold, min_margin)  # raises ValidationFailed for nonsense
    MultiCuePolicy.from_dict(multicue)  # same for the face rules (None = body only)
    next_version = (session.scalar(select(func.max(PolicyVersion.version))) or 0) + 1
    session.execute(update(PolicyVersion).values(is_active=False))
    row = PolicyVersion(
        version=next_version,
        accept_threshold=accept_threshold,
        min_margin=min_margin,
        margin_action=margin_action,
        review_on_quality_flags=review_on_quality_flags,
        status=status,
        calibration_run_id=calibration_run_id,
        confidence_model=confidence_model,
        model_fingerprint=model_fingerprint,
        multicue=multicue,
        note=note,
        created_by=role_name.lower(),
        is_active=True,
    )
    session.add(row)
    session.flush()
    return row


def list_versions(session: Session, limit: int = 50) -> list[PolicyVersion]:
    return list(session.scalars(select(PolicyVersion).order_by(PolicyVersion.version.desc()).limit(limit)))


def to_model(row: PolicyVersion, current_fingerprint: str | None, face_available: bool = False) -> PolicyModel:
    multicue = MultiCuePolicy.from_dict(row.multicue)
    return PolicyModel(
        matching_mode="face_body" if multicue else "body",
        face_accept_threshold=multicue.face_accept_threshold if multicue else None,
        face_review_band=multicue.face_review_band if multicue else None,
        body_only_action=multicue.body_only_action.value if multicue else None,
        face_models_loaded=face_available,
        version=row.version,
        accept_threshold=row.accept_threshold,
        min_margin=row.min_margin,
        margin_action=row.margin_action,
        review_on_quality_flags=row.review_on_quality_flags,
        status=row.status,  # type: ignore[arg-type]
        status_explanation=STATUS_EXPLANATION[row.status],
        calibration_run_id=row.calibration_run_id,
        has_confidence_model=row.confidence_model is not None,
        model_fingerprint=row.model_fingerprint,
        model_matches_current=None if row.model_fingerprint is None else row.model_fingerprint == current_fingerprint,
        note=row.note,
        created_by=row.created_by,
        created_at=row.created_at,
        is_active=row.is_active,
    )
