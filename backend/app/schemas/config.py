"""Request/response shapes for decision-policy configuration."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PolicyModel(BaseModel):
    version: int
    accept_threshold: float
    min_margin: float | None
    margin_action: str
    review_on_quality_flags: bool
    matching_mode: Literal["body", "face_body"] = Field(
        default="body", description="body = clothing/build only (the PS-1 baseline); face_body = face first, body as support."
    )
    face_accept_threshold: float | None = None
    face_review_band: float | None = None
    body_only_action: Literal["review", "accept"] | None = None
    face_models_loaded: bool = Field(default=False, description="False: face_body falls back to body evidence until the models are downloaded.")
    status: Literal["unvalidated", "experimental", "calibrated"]
    status_explanation: str
    calibration_run_id: str | None = None
    has_confidence_model: bool = False
    model_fingerprint: str | None = None
    model_matches_current: bool | None = Field(
        default=None, description="False when the thresholds were set for a different embedding model."
    )
    note: str = ""
    created_by: str
    created_at: datetime
    is_active: bool


class ThresholdUpdate(BaseModel):
    """Either give explicit values (saved as EXPERIMENTAL) or reference a calibration run."""

    from_calibration_run_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    accept_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    min_margin: float | None = Field(default=None, ge=0.0, le=1.0)
    margin_action: Literal["review", "reject"] = "review"
    review_on_quality_flags: bool = True
    matching_mode: Literal["body", "face_body"] | None = Field(
        default=None, description="Omit to keep the current mode. 'body' switches faces off; 'face_body' switches them on."
    )
    face_accept_threshold: float | None = Field(default=None, gt=0.0, lt=1.0)
    face_review_band: float | None = Field(default=None, ge=0.0, le=0.5)
    body_only_action: Literal["review", "accept"] | None = None
    note: str = Field(default="", max_length=400)
    confirm: bool = Field(description="Must be true: the change immediately affects live decisions.")

    @model_validator(mode="after")
    def _either_run_or_values(self) -> ThresholdUpdate:
        if self.from_calibration_run_id is None and self.accept_threshold is None:
            raise ValueError("Provide accept_threshold, or from_calibration_run_id to apply a calibration result.")
        return self


class ConfigResponse(BaseModel):
    policy: PolicyModel
    limits: dict
    retention: dict
    auth: dict
    model: dict
    evaluation_defaults: dict


class ModelStatus(BaseModel):
    embedding: dict
    detector: dict
    device: dict
    gallery_index: dict
    face: dict = Field(default_factory=dict)
