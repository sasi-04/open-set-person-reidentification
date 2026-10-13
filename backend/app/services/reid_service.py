"""
The re-identification workflow, start to finish.

In plain words: for one uploaded picture this does, in order,

    1. find the person (or people)               - detector, or a box/crop the user supplied
    2. cut out each person and check crop quality
    3. turn each crop into an embedding           - ONE batched pass through the network
    4. rank the enrolled people by similarity     - gallery index
    5. decide: accepted / unknown / review        - decision engine + the ACTIVE policy
    6. write a history row (scores only)          - and keep the crop briefly, if retention allows
    7. return everything, including how long each stage took

Stage timings are measured with ``time.perf_counter`` around the real calls.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.errors import NoPersonDetected, NotFound, ValidationFailed
from ..cv.geometry import Box, crop_person, crop_region, pad_to_person_aspect
from ..cv.imaging import DecodedImage
from ..cv.open_set.decision_engine import Decision
from ..cv.open_set.policy import DecisionPolicy, Outcome
from ..cv.quality import QualityReport, assess_crop
from ..cv.retrieval.validation import InvalidEmbedding
from ..db.models import FaceTemplate, Identity, InferenceRecord, InferenceResult, ReferenceImage
from ..schemas.reid import (
    CandidateModel,
    CueRowModel,
    DecisionModel,
    DetectionModel,
    DetectResponse,
    FaceObservationModel,
    HistoryDetail,
    HistoryItem,
    HistoryPage,
    ImageInfo,
    ModelRef,
    PersonResultModel,
    PredictMode,
    PredictResponse,
    QualityModel,
)
from . import face_service, policy_service
from .face_service import QueryFace, observe_query_face
from .matching import decide_person
from .runtime import Runtime

logger = logging.getLogger(__name__)

MAX_TOP_K = 10


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


@dataclass
class _Person:
    index: int
    box: Box | None
    detector_score: float | None
    crop: np.ndarray  # what the body network sees (padded to a person-like shape)
    quality: QualityReport
    region: np.ndarray | None = None  # the same person WITHOUT padding: where faces and colours are measured
    origin: tuple[int, int] = (0, 0)  # top-left corner of ``region`` in the uploaded image


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


# ---------------------------------------------------------------------------------
# Step 1: finding people
# ---------------------------------------------------------------------------------
def _quality_model(report: QualityReport) -> QualityModel:
    return QualityModel(**report.to_dict())


def detect_people(runtime: Runtime, image: DecodedImage, request_id: str) -> DetectResponse:
    detector = runtime.require_detector()
    started = time.perf_counter()
    detections = detector.detect(image.pixels)
    detect_ms = _ms(started)

    started = time.perf_counter()
    models = []
    for index, detection in enumerate(detections):
        crop = crop_person(image.pixels, detection.box)
        quality = assess_crop(crop, source_box=detection.box, image_size=(image.width, image.height),
                              detector_score=detection.score)
        models.append(DetectionModel(index=index, box=detection.box.as_list(), detector_score=round(detection.score, 4),
                                     quality=_quality_model(quality)))
    return DetectResponse(
        request_id=request_id, image=ImageInfo(width=image.width, height=image.height), detector=detector.name,
        detections=models, timings_ms={"detect_ms": detect_ms, "quality_ms": _ms(started)},
    )


def _parse_box(raw: list[float] | None, image: DecodedImage) -> Box:
    if raw is None or len(raw) != 4 or not all(isinstance(v, int | float) and math.isfinite(v) for v in raw):
        raise ValidationFailed("mode 'box' needs box=[x1, y1, x2, y2] in pixels.")
    box = Box.from_list(raw).clipped(image.width, image.height)
    if not box.is_valid():
        raise ValidationFailed("The selected box is empty or outside the image.")
    return box


def _find_people(runtime: Runtime, image: DecodedImage, mode: PredictMode, raw_box: list[float] | None,
                 timings: dict[str, float]) -> list[_Person]:
    image_size = (image.width, image.height)
    if mode is PredictMode.CROP:
        started = time.perf_counter()
        crop = pad_to_person_aspect(image.pixels)
        timings["preprocess_ms"] = _ms(started)
        return [_Person(0, None, None, crop, assess_crop(crop), region=image.pixels)]

    if mode is PredictMode.BOX:
        box = _parse_box(raw_box, image)
        started = time.perf_counter()
        region, origin = crop_region(image.pixels, box)
        crop = pad_to_person_aspect(region)
        quality = assess_crop(crop, source_box=box, image_size=image_size)
        timings["preprocess_ms"] = _ms(started)
        return [_Person(0, box, None, crop, quality, region=region, origin=origin)]

    detector = runtime.require_detector()
    started = time.perf_counter()
    detections = detector.detect(image.pixels)
    timings["detect_ms"] = _ms(started)
    if not detections:
        raise NoPersonDetected(
            "No person was detected in this image. Try a clearer photo, or - if the image is already a tight "
            "crop of one person - use 'image is a person crop'."
        )
    started = time.perf_counter()
    people = []
    for index, detection in enumerate(detections):
        region, origin = crop_region(image.pixels, detection.box)
        crop = pad_to_person_aspect(region)
        quality = assess_crop(crop, source_box=detection.box, image_size=image_size, detector_score=detection.score)
        people.append(_Person(index, detection.box, detection.score, crop, quality, region=region, origin=origin))
    timings["preprocess_ms"] = _ms(started)
    return people


# ---------------------------------------------------------------------------------
# Step 2: the main workflow
# ---------------------------------------------------------------------------------
def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 5)


def _candidate_models(decision: Decision, labels: dict[str, str | None], face_boxes: dict[str, list] | None = None) -> list[CandidateModel]:
    face_boxes = face_boxes or {}
    return [
        CandidateModel(
            rank=c.rank, reference_id=c.reference_id, label=labels.get(c.reference_id), score=round(c.score, 5),
            n_images=c.n_images,
            image_url=f"/api/gallery/{c.reference_id}/images/{c.best_image_uid}" if c.best_image_uid else None,
            basis=c.basis, face_score=_r(c.face_score), body_score=_r(c.body_score),
            face_box=face_boxes.get(c.best_image_uid) if c.face_score is not None and c.best_image_uid else None,
        )
        for c in decision.candidates
    ]


def _face_boxes(session: Session, decisions: dict[int, Decision | None]) -> dict[str, list]:
    """Where the matched face sits inside each shown reference picture (so the screen can zoom in on it)."""
    uids = {c.best_image_uid for d in decisions.values() if d for c in d.candidates if c.face_score is not None and c.best_image_uid}
    if not uids:
        return {}
    rows = session.execute(
        select(ReferenceImage.image_uid, FaceTemplate.face_box)
        .join(FaceTemplate, FaceTemplate.image_id == ReferenceImage.id)
        .where(ReferenceImage.image_uid.in_(uids), FaceTemplate.face_box.is_not(None))
    ).all()
    return {uid: box for uid, box in rows}


def _decision_model(decision: Decision, matching_mode: str = "body") -> DecisionModel:
    return DecisionModel(
        outcome=decision.outcome.value, reason_code=decision.reason_code, reason=decision.reason,
        accepted_reference_id=decision.accepted_reference_id, top1_reference_id=decision.top1_reference_id,
        top1_score=_r(decision.top1_score), top2_score=_r(decision.top2_score), margin=_r(decision.margin),
        accept_threshold=decision.accept_threshold, min_margin=decision.min_margin,
        calibrated_confidence=_r(decision.calibrated_confidence), policy_version=decision.policy_version,
        policy_status=decision.policy_status, quality_flags=list(decision.quality_flags),
        matching_mode=matching_mode, basis=decision.basis, face_status=decision.face_status,
        top1_face_score=_r(decision.top1_face_score), top1_body_score=_r(decision.top1_body_score),
        face_threshold=decision.face_threshold, body_threshold=decision.body_threshold,
    )


def _evidence_json(decision_model: DecisionModel, face: FaceObservationModel | None, cues: list[CueRowModel]) -> dict:
    """The part of a person's result that has no column of its own, kept as one JSON value for the history."""
    return {
        "decision": decision_model.model_dump(include={"matching_mode", "basis", "face_status", "top1_face_score",
                                                       "top1_body_score", "face_threshold", "body_threshold"}),
        "face": None if face is None else face.model_dump(),
        "cues": [c.model_dump() for c in cues],
    }


def _error_decision(policy: DecisionPolicy, reason_code: str, reason: str) -> DecisionModel:
    return DecisionModel(
        outcome=Outcome.PROCESSING_ERROR.value, reason_code=reason_code, reason=reason,
        accept_threshold=policy.accept_threshold, min_margin=policy.min_margin,
        policy_version=policy.version, policy_status=policy.status.value,
        matching_mode="face_body" if policy.multicue is not None else "body",
    )


def predict(
    runtime: Runtime, session: Session, image: DecodedImage, *, mode: PredictMode, raw_box: list[float] | None,
    top_k: int, role_name: str, request_id: str,
) -> PredictResponse:
    overall = time.perf_counter()
    extractor = runtime.require_extractor()
    if not 1 <= top_k <= MAX_TOP_K:
        raise ValidationFailed(f"top_k must be between 1 and {MAX_TOP_K}.")

    policy_row = policy_service.get_active(session)
    policy, policy_note = policy_service.effective_policy(runtime, policy_row)
    confidence_model = policy_service.confidence_model_for(policy_row, runtime.fingerprint)
    matching_mode = "face_body" if policy.multicue is not None else "body"

    timings: dict[str, float] = {}
    people = _find_people(runtime, image, mode, raw_box, timings)

    usable = [p for p in people if p.quality.usable]
    embeddings = np.zeros((0, extractor.dim), dtype=np.float32)
    if usable:
        started = time.perf_counter()
        embeddings = extractor.embed([p.crop for p in usable])  # one batch for every person in the picture
        timings["embed_ms"] = _ms(started)
    vector_of = {id(p): vector for p, vector in zip(usable, embeddings, strict=True)}

    # Face evidence: find and judge each person's face (skipped entirely when the policy is body-only).
    faces: dict[int, QueryFace] = {}
    if matching_mode == "face_body":
        started = time.perf_counter()
        for person in usable:
            faces[person.index] = observe_query_face(runtime, person.region if person.region is not None else person.crop, person.origin)
        timings["face_ms"] = _ms(started)

    retrieval_started = time.perf_counter()
    decisions: dict[int, Decision | None] = {}
    errors: dict[int, tuple[str, str]] = {}  # person -> (reason code, sentence): why there is no decision
    for person in people:
        if not person.quality.usable:
            decisions[person.index] = None
            errors[person.index] = ("crop_unusable", person.quality.blocking_reason or "The crop is unusable.")
            continue
        try:
            decisions[person.index] = decide_person(
                runtime, policy, vector_of[id(person)], body_flags=person.quality.flags, face=faces.get(person.index),
                top_k=top_k, confidence_model=confidence_model)
        except InvalidEmbedding as exc:
            # A broken fingerprint is a PROCESSING ERROR for this person - never an ordinary "unknown".
            decisions[person.index] = None
            errors[person.index] = ("invalid_embedding", exc.message)
            logger.warning("predict %s: invalid embedding for person %d: %s", request_id, person.index, exc.message)
    timings["retrieval_and_decision_ms"] = _ms(retrieval_started)

    cues_of: dict[int, list[CueRowModel]] = {}
    for person in people:
        decision, face = decisions[person.index], faces.get(person.index)
        if decision is not None and face is not None and decision.candidates:
            cues_of[person.index] = face_service.cue_rows(session, face.cues, decision.candidates[0].best_image_uid)

    needed = {c.reference_id for d in decisions.values() if d for c in d.candidates}
    labels = dict(session.execute(select(Identity.reference_id, Identity.label).where(Identity.reference_id.in_(needed))).all()) if needed else {}

    face_boxes = _face_boxes(session, decisions)
    created_at = datetime.now(UTC)
    keep_crops = runtime.settings.query_retention_hours > 0
    expires = created_at + timedelta(hours=runtime.settings.query_retention_hours)

    record = InferenceRecord(
        request_id=request_id, created_at=created_at, mode=mode.value, n_people=len(people), policy_version=policy.version,
        model_name=extractor.name, image_width=image.width, image_height=image.height, total_ms=0.0, timings={},
    )
    person_models: list[PersonResultModel] = []
    for person in people:
        decision = decisions[person.index]
        crop_name = runtime.queries.save_jpeg(person.crop, quality=80) if (keep_crops and decision is not None) else None
        if decision is None:
            code, sentence = errors.get(person.index, ("crop_unusable", "The crop is unusable."))
            decision_model = _error_decision(policy, code, sentence)
            candidate_models: list[CandidateModel] = []
        else:
            decision_model, candidate_models = _decision_model(decision, matching_mode), _candidate_models(decision, labels, face_boxes)
        face_observation = faces[person.index].observation() if person.index in faces else None
        person_cues = cues_of.get(person.index, [])

        record.results.append(InferenceResult(
            person_index=person.index, created_at=created_at, outcome=decision_model.outcome,
            reason_code=decision_model.reason_code, reason=decision_model.reason,
            accepted_reference_id=decision_model.accepted_reference_id, top1_reference_id=decision_model.top1_reference_id,
            top1_score=decision_model.top1_score, top2_score=decision_model.top2_score, margin=decision_model.margin,
            calibrated_confidence=decision_model.calibrated_confidence, accept_threshold=decision_model.accept_threshold,
            min_margin=decision_model.min_margin, policy_version=policy.version, detector_score=person.detector_score,
            box=person.box.as_list() if person.box else None, quality=person.quality.to_dict(),
            candidates=[c.model_dump() for c in candidate_models], crop_path=crop_name,
            crop_expires_at=expires if crop_name else None,
            evidence=_evidence_json(decision_model, face_observation, person_cues) if matching_mode == "face_body" else None,
        ))
        person_models.append(PersonResultModel(
            index=person.index, box=person.box.as_list() if person.box else None,
            detector_score=None if person.detector_score is None else round(person.detector_score, 4),
            quality=_quality_model(person.quality), decision=decision_model, candidates=candidate_models,
            crop_url=f"/api/reid/history/{request_id}/crops/{person.index}" if crop_name else None,
            face=face_observation, cues=person_cues,
        ))

    timings["total_ms"] = _ms(overall)
    record.total_ms, record.timings = timings["total_ms"], timings
    session.add(record)
    session.commit()

    info = extractor.info()
    logger.info("predict %s mode=%s people=%d outcomes=%s total=%.0fms", request_id, mode.value, len(people),
                [p.decision.outcome for p in person_models], timings["total_ms"])
    return PredictResponse(
        request_id=request_id, created_at=created_at, mode=mode, image=ImageInfo(width=image.width, height=image.height),
        model=ModelRef(name=extractor.name, architecture=info["architecture"], embedding_dim=extractor.dim,
                       fingerprint=extractor.fingerprint, device=info["device"]),
        face_model=runtime.face_engine.fingerprint if (runtime.face_engine and matching_mode == "face_body") else None,
        matching_mode=matching_mode,
        policy_version=policy.version, policy_status=policy.status.value, people=person_models, timings_ms=timings,
        notes=([policy_note] if policy_note else []) + _notes(policy, runtime),
    )


def _notes(policy: DecisionPolicy, runtime: Runtime) -> list[str]:
    notes = []
    if policy.multicue is not None:
        notes.append("Face + body matching: the face decides when a usable face is visible; clothing alone cannot produce a MATCH.")
    if policy.status.value != "calibrated":
        notes.append(f"The active threshold is {policy.status.value}: it has not been calibrated on held-out data.")
    if runtime.index.snapshot.n_identities == 0:
        notes.append("The gallery is empty, so every query is reported as unknown.")
    return notes


# ---------------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------------
_PRIORITY = ["accepted", "review_required", "unknown", "processing_error"]


def _history_item(record: InferenceRecord) -> HistoryItem:
    counts: dict[str, int] = {}
    for result in record.results:
        counts[result.outcome] = counts.get(result.outcome, 0) + 1
    scores = [r.top1_score for r in record.results if r.top1_score is not None]
    return HistoryItem(
        request_id=record.request_id, created_at=record.created_at, mode=record.mode, n_people=record.n_people,
        outcomes=counts, top_outcome=next((o for o in _PRIORITY if o in counts), "unknown"),
        best_score=max(scores) if scores else None, policy_version=record.policy_version,
        model_name=record.model_name, total_ms=record.total_ms,
    )


def list_history(session: Session, *, limit: int, offset: int, outcome: str | None) -> HistoryPage:
    query = select(InferenceRecord)
    count_query = select(func.count()).select_from(InferenceRecord)
    if outcome:
        match = select(InferenceResult.record_id).where(InferenceResult.outcome == outcome)
        query, count_query = query.where(InferenceRecord.id.in_(match)), count_query.where(InferenceRecord.id.in_(match))
    records = session.scalars(query.order_by(InferenceRecord.created_at.desc(), InferenceRecord.id.desc()).limit(limit).offset(offset))
    return HistoryPage(items=[_history_item(r) for r in records], total=session.scalar(count_query) or 0, limit=limit, offset=offset)


def _record_by_request_id(session: Session, request_id: str) -> InferenceRecord:
    record = session.scalar(select(InferenceRecord).where(InferenceRecord.request_id == request_id))
    if record is None:
        raise NotFound("No such request in the history (it may have been removed by the retention policy).")
    return record


def history_detail(session: Session, request_id: str) -> HistoryDetail:
    record = _record_by_request_id(session, request_id)
    now = datetime.now(UTC)
    people = []
    for result in record.results:
        crop_alive = bool(result.crop_path) and result.crop_expires_at is not None and _aware(result.crop_expires_at) > now
        evidence = result.evidence or {}  # None for requests made before face matching existed, or under a body-only policy
        people.append(PersonResultModel(
            index=result.person_index, box=result.box, detector_score=result.detector_score,
            quality=QualityModel(**result.quality) if result.quality else None,
            decision=DecisionModel(
                outcome=result.outcome, reason_code=result.reason_code, reason=result.reason,
                accepted_reference_id=result.accepted_reference_id, top1_reference_id=result.top1_reference_id,
                top1_score=result.top1_score, top2_score=result.top2_score, margin=result.margin,
                accept_threshold=result.accept_threshold, min_margin=result.min_margin,
                calibrated_confidence=result.calibrated_confidence, policy_version=result.policy_version,
                policy_status="recorded", quality_flags=(result.quality or {}).get("flags", []),
                **evidence.get("decision", {}),
            ),
            candidates=[CandidateModel(**c) for c in result.candidates],
            crop_url=f"/api/reid/history/{request_id}/crops/{result.person_index}" if crop_alive else None,
            face=FaceObservationModel(**evidence["face"]) if evidence.get("face") else None,
            cues=[CueRowModel(**c) for c in evidence.get("cues", [])],
        ))
    return HistoryDetail(
        request_id=record.request_id, created_at=record.created_at, mode=record.mode,
        image=ImageInfo(width=record.image_width, height=record.image_height), model_name=record.model_name,
        policy_version=record.policy_version, people=people, timings_ms=record.timings,
    )


EXPORT_NOTICE = (
    "A similarity score is not a probability, and a match is not proof of anyone's identity. This record shows what the "
    "system measured under the decision policy named in it; it can be wrong and is meant for authorised evaluation only."
)


def export_record(session: Session, request_id: str, fmt: str) -> tuple[str, str]:
    """The saved decision(s) of one request as a downloadable file. Returns (body, media type)."""
    import csv
    import io
    import json

    detail = history_detail(session, request_id)
    if fmt == "json":
        body = {"notice": EXPORT_NOTICE, "record": detail.model_dump(mode="json")}
        return json.dumps(body, indent=2), "application/json"
    if fmt != "csv":
        raise ValidationFailed("format must be json or csv.")

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["request_id", "created_at", "mode", "model", "policy_version", "person", "outcome", "reason_code", "reason",
                     "accepted_reference_id", "top1_reference_id", "top1_score", "top2_score", "margin", "accept_threshold",
                     "min_margin", "calibrated_confidence", "quality_flags", "candidates (rank:reference:score)", "notice",
                     "matching_mode", "decided_by", "face_status", "top1_face_score", "top1_body_score", "face_threshold", "body_threshold"])
    for person in detail.people:
        d = person.decision
        writer.writerow([detail.request_id, detail.created_at.isoformat(), detail.mode, detail.model_name, detail.policy_version,
                         person.index, d.outcome, d.reason_code, d.reason, d.accepted_reference_id or "", d.top1_reference_id or "",
                         "" if d.top1_score is None else d.top1_score, "" if d.top2_score is None else d.top2_score,
                         "" if d.margin is None else d.margin, d.accept_threshold, "" if d.min_margin is None else d.min_margin,
                         "" if d.calibrated_confidence is None else d.calibrated_confidence, ";".join(d.quality_flags),
                         " | ".join(f"{c.rank}:{c.reference_id}:{c.score}" for c in person.candidates), EXPORT_NOTICE,
                         d.matching_mode, d.basis, d.face_status or "", "" if d.top1_face_score is None else d.top1_face_score,
                         "" if d.top1_body_score is None else d.top1_body_score, "" if d.face_threshold is None else d.face_threshold,
                         "" if d.body_threshold is None else d.body_threshold])
    return out.getvalue(), "text/csv; charset=utf-8"


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)  # SQLite drops the time zone


def crop_bytes(runtime: Runtime, session: Session, request_id: str, index: int) -> bytes:
    record = _record_by_request_id(session, request_id)
    for result in record.results:
        if result.person_index == index and result.crop_path and result.crop_expires_at:
            if _aware(result.crop_expires_at) > datetime.now(UTC):
                return runtime.queries.read_bytes(result.crop_path)
    raise NotFound("The stored crop is no longer available (query images are deleted after the retention window).")
