"""Configuration routes: thresholds, model status, audit trail, maintenance."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from ...core.errors import Conflict, ValidationFailed
from ...cv.open_set.policy import BodyOnlyAction, MultiCuePolicy
from ...db.models import AuditEvent
from ...schemas.config import ConfigResponse, ModelStatus, PolicyModel, ThresholdUpdate
from ...services import evaluation_service, maintenance_service, policy_service
from ...services.audit import record_audit
from ..deps import AdminRole, RuntimeDep, SessionDep, ViewerRole

router = APIRouter(prefix="/api", tags=["configuration"])


def _live_fingerprint(runtime) -> str | None:
    return runtime.fingerprint


def _face_status(runtime) -> dict:
    snapshot = runtime.face_index.snapshot
    base = {"ready": runtime.face_engine is not None, "enabled": runtime.settings.face_matching,
            "enrolled_faces": snapshot.n_images, "identities_with_a_face": snapshot.n_identities}
    return {**base, **(runtime.face_engine.info() if runtime.face_engine else {"error": runtime.face_error})}


@router.get("/config", response_model=ConfigResponse, summary="Active decision policy and system limits")
def get_config(runtime: RuntimeDep, session: SessionDep, _: ViewerRole) -> ConfigResponse:
    s = runtime.settings
    return ConfigResponse(
        policy=policy_service.to_model(policy_service.get_active(session), _live_fingerprint(runtime), runtime.face_engine is not None),
        limits={"max_upload_mb": s.max_upload_mb, "max_image_side": s.max_image_side, "allowed_extensions": list(s.allowed_extensions),
                "max_enroll_files": s.max_enroll_files, "detector_score_threshold": s.detector_score_threshold},
        retention={"query_retention_hours": s.query_retention_hours, "history_retention_days": s.history_retention_days,
                   "reference_images": "kept until the identity is deleted"},
        auth={"required": s.auth_required, "roles": ["viewer", "operator", "admin"]},
        model={"embedding": runtime.extractor.info() if runtime.extractor else {"error": runtime.extractor_error},
               "face": _face_status(runtime), "flip_tta": s.use_flip_tta},
        evaluation_defaults={"bootstrap_samples": s.evaluation_bootstrap_samples},
    )


@router.get("/model/status", response_model=ModelStatus, summary="Model, device and index status")
def model_status(runtime: RuntimeDep, _: ViewerRole) -> ModelStatus:
    snapshot = runtime.index.snapshot
    return ModelStatus(
        embedding={"ready": runtime.extractor is not None,
                   **(runtime.extractor.info() if runtime.extractor else {"error": runtime.extractor_error})},
        detector={"ready": runtime.detector is not None,
                  **(runtime.detector.info() if runtime.detector else {"error": runtime.detector_error})},
        device=runtime.device_info,
        gallery_index={"version": snapshot.version, "identities": snapshot.n_identities, "images": snapshot.n_images},
        face=_face_status(runtime),
    )


@router.get("/config/history", response_model=list[PolicyModel], summary="Every policy version, newest first")
def policy_history(runtime: RuntimeDep, session: SessionDep, _: ViewerRole,
                   limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[PolicyModel]:
    return [policy_service.to_model(row, _live_fingerprint(runtime), runtime.face_engine is not None)
            for row in policy_service.list_versions(session, limit)]


@router.post("/config/thresholds", response_model=PolicyModel, summary="Create a new active policy version")
def update_thresholds(body: ThresholdUpdate, runtime: RuntimeDep, session: SessionDep, role: AdminRole) -> PolicyModel:
    if not body.confirm:
        raise ValidationFailed("Changing the policy immediately affects live decisions: set confirm=true to apply it.")

    confidence_model, calibration_run_id = None, None
    if body.from_calibration_run_id:
        run = evaluation_service.get_run(session, body.from_calibration_run_id)
        if run.kind != "calibration" or run.status != "succeeded" or not run.result:
            raise Conflict("That run is not a finished calibration run.")
        result = run.result
        if result["model_fingerprint"] != _live_fingerprint(runtime):
            raise Conflict(
                "That calibration was computed for a different model configuration than the one running now "
                f"({result['model_fingerprint']} vs {_live_fingerprint(runtime)}). Re-run calibration."
            )
        if not result["selected"]["target_achieved"]:
            raise Conflict("That calibration did NOT reach its target, so it cannot be applied as 'calibrated'. "
                           "Enter values manually if you want to use them as an experimental setting.")
        proposed = result["proposed_policy"]
        threshold, margin, status = proposed["accept_threshold"], proposed["min_margin"], "calibrated"
        confidence_model, calibration_run_id = result.get("confidence_model"), run.id
    else:
        threshold, margin, status = body.accept_threshold, body.min_margin, "experimental"

    multicue = _next_multicue(body, MultiCuePolicy.from_dict(policy_service.get_active(session).multicue), runtime)
    row = policy_service.create_version(
        session, accept_threshold=threshold, min_margin=margin, margin_action=body.margin_action,
        review_on_quality_flags=body.review_on_quality_flags, status=status, role_name=role.name, note=body.note,
        calibration_run_id=calibration_run_id, confidence_model=confidence_model, model_fingerprint=_live_fingerprint(runtime),
        multicue=multicue.to_dict() if multicue else None,
    )
    record_audit(session, role.name, "policy.update", f"v{row.version}", threshold=threshold, min_margin=margin, status=status,
                 matching_mode="face_body" if multicue else "body")
    session.commit()
    return policy_service.to_model(row, _live_fingerprint(runtime), runtime.face_engine is not None)


def _next_multicue(body: ThresholdUpdate, current: MultiCuePolicy | None, runtime) -> MultiCuePolicy | None:
    """The face rules of the NEW policy version: keep the current ones unless the request changes them."""
    mode = body.matching_mode or ("face_body" if current else "body")
    if mode == "body":
        return None
    if current is None and not runtime.settings.face_matching:
        raise Conflict("Face matching is switched off on this server (REID_FACE_MATCHING=false).")
    base = current or MultiCuePolicy()
    return MultiCuePolicy(
        face_accept_threshold=body.face_accept_threshold if body.face_accept_threshold is not None else base.face_accept_threshold,
        face_review_band=body.face_review_band if body.face_review_band is not None else base.face_review_band,
        body_only_action=BodyOnlyAction(body.body_only_action) if body.body_only_action else base.body_only_action,
    )


@router.get("/audit", summary="Audit trail of sensitive actions (admin only)")
def audit(session: SessionDep, _: AdminRole, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[dict]:
    events = session.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit))
    return [{"at": e.created_at, "role": e.actor_role, "action": e.action, "subject": e.subject, "detail": e.detail} for e in events]


@router.post("/maintenance/cleanup", summary="Apply the retention policy now")
def cleanup(runtime: RuntimeDep, session: SessionDep, role: AdminRole) -> dict:
    return maintenance_service.run_cleanup(session, runtime, role.name)
