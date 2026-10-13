"""
Request/response shapes for re-identification.

Reading guide - four different numbers, deliberately named differently:
    detector_score         how sure the DETECTOR is that the box holds a person
    decision.top1_score    cosine SIMILARITY of the best enrolled candidate (a retrieval score)
    decision.margin        top-1 minus top-2 similarity (an ambiguity signal)
    decision.calibrated_confidence   fitted estimate that an accepted match is right (optional)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class PredictMode(str, Enum):
    CROP = "crop"  # the whole uploaded image is already a single person crop
    BOX = "box"  # match the person inside the supplied pixel box
    ALL = "all"  # detect every person and match each of them


class ImageInfo(BaseModel):
    width: int
    height: int


class QualityModel(BaseModel):
    usable: bool
    flags: list[str] = Field(default_factory=list)
    blocking_reason: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)


class DetectionModel(BaseModel):
    index: int
    box: list[float] = Field(description="[x1, y1, x2, y2] in pixels of the uploaded image")
    detector_score: float = Field(description="Detector confidence. NOT an identity-match score.")
    quality: QualityModel


class DetectResponse(BaseModel):
    request_id: str
    image: ImageInfo
    detector: str
    detections: list[DetectionModel]
    timings_ms: dict[str, float]


class CandidateModel(BaseModel):
    rank: int
    reference_id: str
    label: str | None = None
    score: float = Field(description="Cosine similarity (-1..1). A retrieval score, not a probability.")
    n_images: int | None = None
    image_url: str | None = Field(default=None, description="Closest reference image for this candidate.")
    basis: str = Field(default="body", description="'face' or 'body': which fingerprint produced `score`.")
    face_score: float | None = Field(default=None, description="Face similarity to this person's best reference face (None = not compared).")
    body_score: float | None = Field(default=None, description="Whole-body similarity to this person's best reference image.")
    face_box: list[float] | None = Field(default=None, description="[x1, y1, x2, y2] of the matched face inside `image_url`'s picture.")


class FaceObservationModel(BaseModel):
    """What the face analysis found in the QUERY picture of one person."""

    status: str = Field(description="not_used | no_face | unusable | usable")
    box: list[float] | None = Field(default=None, description="[x1, y1, x2, y2] of the face in the uploaded image's pixels")
    detector_score: float | None = None
    face_px: float | None = Field(default=None, description="Shorter side of the face box, in pixels")
    flags: list[str] = Field(default_factory=list)
    message: str | None = Field(default=None, description="Plain-language explanation, e.g. why the face cannot be used.")


class CueRowModel(BaseModel):
    """One supporting cue (hair, skin tone, clothing colour) of the query next to the closest reference. Never decides anything."""

    cue: str
    title: str
    query_rgb: list[int]
    query_label: str
    reference_rgb: list[int]
    reference_label: str
    delta_e: float = Field(description="CIE76 colour distance: ~2 barely visible, 10-20 clearly different shade, 40+ different colour")
    verdict: str = Field(description="similar | different (heuristic, uncalibrated)")


class DecisionModel(BaseModel):
    outcome: str = Field(description="accepted | unknown | review_required | processing_error")
    reason_code: str
    reason: str = Field(description="Plain-language explanation built from the real scores and rules.")
    accepted_reference_id: str | None = None
    top1_reference_id: str | None = None
    top1_score: float | None = None
    top2_score: float | None = None
    margin: float | None = None
    accept_threshold: float | None = None
    min_margin: float | None = None
    calibrated_confidence: float | None = Field(
        default=None, description="Only present when a calibration run supplied a confidence model."
    )
    policy_version: int
    policy_status: str
    quality_flags: list[str] = Field(default_factory=list)
    # ---- face + body matching (all None / "body" when the policy is body-only)
    matching_mode: str = Field(default="body", description="body | face_body: what the policy compared")
    basis: str = Field(default="body", description="face | body: the evidence `top1_score` and `accept_threshold` belong to")
    face_status: str | None = None
    top1_face_score: float | None = Field(default=None, description="What the FACE says about the top-1 person (None = not compared)")
    top1_body_score: float | None = Field(default=None, description="What the BODY says about the top-1 person")
    face_threshold: float | None = None
    body_threshold: float | None = None


class PersonResultModel(BaseModel):
    index: int
    box: list[float] | None = None
    detector_score: float | None = None
    quality: QualityModel | None = None
    decision: DecisionModel
    candidates: list[CandidateModel] = Field(default_factory=list)
    face: FaceObservationModel | None = None
    cues: list[CueRowModel] = Field(default_factory=list)
    crop_url: str | None = Field(default=None, description="Stored query crop (only during the retention window).")
    timings_ms: dict[str, float] = Field(default_factory=dict)


class ModelRef(BaseModel):
    name: str
    architecture: str
    embedding_dim: int
    fingerprint: str
    device: str


class PredictResponse(BaseModel):
    request_id: str
    created_at: datetime
    mode: PredictMode
    image: ImageInfo
    model: ModelRef
    face_model: str | None = Field(default=None, description="Fingerprint of the face models used (None = body only).")
    matching_mode: str = "body"
    policy_version: int
    policy_status: str
    people: list[PersonResultModel]
    timings_ms: dict[str, float]
    notes: list[str] = Field(default_factory=list)


class HistoryDetail(BaseModel):
    request_id: str
    created_at: datetime
    mode: str
    image: ImageInfo
    model_name: str
    policy_version: int
    people: list[PersonResultModel]
    timings_ms: dict[str, float]


class HistoryItem(BaseModel):
    request_id: str
    created_at: datetime
    mode: str
    n_people: int
    outcomes: dict[str, int] = Field(description="Count of people per outcome in this request.")
    top_outcome: str
    best_score: float | None = None
    policy_version: int
    model_name: str
    total_ms: float


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    total: int
    limit: int
    offset: int
