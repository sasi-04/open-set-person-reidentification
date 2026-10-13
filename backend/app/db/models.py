"""
Database tables.

In plain words: one class per table. The tables are:

  identities / reference_images   the enrolled gallery (people + their reference crops and embeddings)
  face_templates                  per reference image: the face found in it, its fingerprint and colour cues
  policy_versions                 every version of the decision rules, with who changed them and why
  inference_records / _results    history of re-identification requests (scores, never raw images)
  evaluation_runs                 background experiments: status, progress, final JSON result
  audit_events                    who did what to the gallery / settings, and when

Raw database IDs stay inside the server; the API speaks in ``reference_id``
(a pseudonymous label chosen by the operator) and random ``image_uid`` strings.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Identity(Base):
    __tablename__ = "identities"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String(80))
    consent_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    images: Mapped[list[ReferenceImage]] = relationship(
        back_populates="identity", cascade="all, delete-orphan", order_by="ReferenceImage.id"
    )


class ReferenceImage(Base):
    __tablename__ = "reference_images"
    __table_args__ = (UniqueConstraint("identity_id", "sha256", name="uq_identity_image"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    image_uid: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    identity_id: Mapped[int] = mapped_column(ForeignKey("identities.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(String(200))  # relative to the reference store
    sha256: Mapped[str] = mapped_column(String(64))  # fingerprint of the ORIGINAL upload (duplicate detection)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))  # "crop" (uploaded as a crop) | "detected"
    quality_flags: Mapped[list] = mapped_column(JSON, default=list)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(80))  # extractor fingerprint that produced it
    embedding_dim: Mapped[int | None] = mapped_column(Integer)
    embedding_status: Mapped[str] = mapped_column(String(10), default="ready")  # ready | stale | failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    identity: Mapped[Identity] = relationship(back_populates="images")
    face: Mapped[FaceTemplate | None] = relationship(back_populates="image", cascade="all, delete-orphan", uselist=False)


class FaceTemplate(Base):
    """What the face analysis found in ONE reference image (kept in its own table so older databases upgrade in place).

    status: ready    a usable face; its 128-number fingerprint is in the face index
            weak     a face was found but it is too small / blurry / turned to trust - NOT used for matching
            no_face  no face found (a back view, a very small person ...) - the image is still used for body matching
            stale    made by a different face model than the one now loaded; re-analyse
            failed   the analysis crashed on this image
    """

    __tablename__ = "face_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("reference_images.id", ondelete="CASCADE"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(10), default="no_face")
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(80))
    embedding_dim: Mapped[int | None] = mapped_column(Integer)
    face_box: Mapped[list | None] = mapped_column(JSON)  # [x1, y1, x2, y2] inside the stored reference picture
    detector_score: Mapped[float | None] = mapped_column(Float)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    cues: Mapped[dict] = mapped_column(JSON, default=dict)  # hair / skin / clothing colours measured on this picture
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    image: Mapped[ReferenceImage] = relationship(back_populates="face")


class PolicyVersion(Base):
    __tablename__ = "policy_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    accept_threshold: Mapped[float] = mapped_column(Float)
    min_margin: Mapped[float | None] = mapped_column(Float)
    margin_action: Mapped[str] = mapped_column(String(10), default="review")
    review_on_quality_flags: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(14), default="unvalidated")  # unvalidated | experimental | calibrated
    calibration_run_id: Mapped[str | None] = mapped_column(String(32))
    confidence_model: Mapped[dict | None] = mapped_column(JSON)
    model_fingerprint: Mapped[str | None] = mapped_column(String(100))  # model the thresholds were set for
    multicue: Mapped[dict | None] = mapped_column(JSON)  # face-matching rules (cv/open_set/policy.MultiCuePolicy); None = body only
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(16), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class InferenceRecord(Base):
    __tablename__ = "inference_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    mode: Mapped[str] = mapped_column(String(10))
    n_people: Mapped[int] = mapped_column(Integer)
    policy_version: Mapped[int] = mapped_column(Integer)
    model_name: Mapped[str] = mapped_column(String(80))
    image_width: Mapped[int] = mapped_column(Integer)
    image_height: Mapped[int] = mapped_column(Integer)
    total_ms: Mapped[float] = mapped_column(Float)
    timings: Mapped[dict] = mapped_column(JSON, default=dict)

    results: Mapped[list[InferenceResult]] = relationship(
        back_populates="record", cascade="all, delete-orphan", order_by="InferenceResult.person_index"
    )


class InferenceResult(Base):
    """One row per PERSON in a request (an image with three people produces three rows)."""

    __tablename__ = "inference_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("inference_records.id", ondelete="CASCADE"), index=True)
    person_index: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    outcome: Mapped[str] = mapped_column(String(20), index=True)
    reason_code: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    accepted_reference_id: Mapped[str | None] = mapped_column(String(64))
    top1_reference_id: Mapped[str | None] = mapped_column(String(64))
    top1_score: Mapped[float | None] = mapped_column(Float)
    top2_score: Mapped[float | None] = mapped_column(Float)
    margin: Mapped[float | None] = mapped_column(Float)
    calibrated_confidence: Mapped[float | None] = mapped_column(Float)
    accept_threshold: Mapped[float | None] = mapped_column(Float)
    min_margin: Mapped[float | None] = mapped_column(Float)
    policy_version: Mapped[int] = mapped_column(Integer)
    detector_score: Mapped[float | None] = mapped_column(Float)
    box: Mapped[list | None] = mapped_column(JSON)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    candidates: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[dict | None] = mapped_column(JSON)  # face observation, per-cue colours and the face/body detail of the decision
    crop_path: Mapped[str | None] = mapped_column(String(200))  # query crop kept only for the retention window
    crop_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    record: Mapped[InferenceRecord] = relationship(back_populates="results")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(12))  # evaluation | calibration
    status: Mapped[str] = mapped_column(String(12), index=True)  # queued | running | succeeded | failed | cancelled
    stage: Mapped[str] = mapped_column(String(80), default="Queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    dataset_name: Mapped[str] = mapped_column(String(120))
    dataset_kind: Mapped[str] = mapped_column(String(20), default="benchmark")
    created_by: Mapped[str] = mapped_column(String(16), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor_role: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(40), index=True)
    subject: Mapped[str | None] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
