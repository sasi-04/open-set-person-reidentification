"""Request/response shapes for evaluation and calibration jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..evaluation.ablation import VARIANT_BY_KEY


class ProtocolOptions(BaseModel):
    gallery_shots: int = Field(default=3, ge=1, le=10, description="Reference images per enrolled person.")
    dev_fraction: float = Field(default=0.4, ge=0.0, le=0.8)
    calibration_fraction: float = Field(default=0.2, ge=0.05, le=0.8)
    max_identities_per_split: int | None = Field(
        default=None, ge=10, le=2000, description="Cap people per split to keep CPU runs short."
    )
    max_images_per_identity: int | None = Field(default=12, ge=4, le=200)
    cross_camera: bool = True


class TargetOptions(BaseModel):
    mode: Literal["fixed_recall", "fixed_far"] = "fixed_recall"
    target_recall: float = Field(default=0.90, gt=0.0, le=1.0)
    target_far: float = Field(default=0.01, ge=0.0, lt=1.0)
    recall_metric: Literal["dir1", "tar"] = "dir1"


class EvaluationRunRequest(BaseModel):
    dataset: str = Field(min_length=1, max_length=120)
    seeds: list[int] = Field(default_factory=lambda: [0], min_length=1, max_length=5)
    target: TargetOptions = Field(default_factory=TargetOptions)
    protocol: ProtocolOptions = Field(default_factory=ProtocolOptions)
    variants: list[str] | None = Field(default=None, description="Default: every variant that needs no checkpoint.")
    bootstrap_samples: int = Field(default=200, ge=0, le=2000)
    finetuned_checkpoint: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9._-]{1,120}\.pt$",
        description="File name inside backend/weights/finetuned/ (never a path).",
    )

    @field_validator("variants")
    @classmethod
    def _known_variants(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            unknown = [v for v in value if v not in VARIANT_BY_KEY]
            if unknown:
                raise ValueError(f"Unknown variants: {unknown}. Available: {sorted(VARIANT_BY_KEY)}")
        return value

    @field_validator("seeds")
    @classmethod
    def _non_negative_seeds(cls, value: list[int]) -> list[int]:
        if any(s < 0 or s > 10_000 for s in value):
            raise ValueError("Seeds must be between 0 and 10000.")
        return value


class CalibrationRunRequest(BaseModel):
    dataset: str = Field(min_length=1, max_length=120)
    seed: int = Field(default=0, ge=0, le=10_000)
    target: TargetOptions = Field(default_factory=TargetOptions)
    protocol: ProtocolOptions = Field(default_factory=ProtocolOptions)
    use_margin: bool = True


class LookalikeRunRequest(BaseModel):
    """Settings of one Lookalike Failure Lab experiment (see ``evaluation/lookalike.py``)."""

    dataset: str = Field(min_length=1, max_length=120)
    seed: int = Field(default=0, ge=0, le=10_000)
    target: TargetOptions = Field(default_factory=TargetOptions)
    protocol: ProtocolOptions = Field(default_factory=ProtocolOptions)
    mining_split: Literal["dev", "calibration", "test"] = Field(
        default="test", description="Which group of people to search for look-alikes. The threshold is always chosen on 'calibration'.")
    top_pairs: int = Field(default=40, ge=5, le=200, description="How many most-alike pairs of people to list and test.")
    images_per_pair: int = Field(default=3, ge=1, le=10)
    max_genuine_pairs: int = Field(default=4000, ge=100, le=50_000)
    max_failures: int = Field(default=40, ge=5, le=200, description="Failures listed per category.")
    use_margin: bool = True
    finetuned_checkpoint: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9._-]{1,120}\.pt$",
        description="File name inside backend/weights/finetuned/ (never a path). Leave empty to run the baseline only.",
    )


class SandboxRequest(BaseModel):
    """A trial decision rule to try on the stored scores of a finished run. It never changes the active policy."""

    split: Literal["calibration", "test"] = "calibration"
    threshold: float = Field(ge=0.0, le=1.0)
    min_margin: float | None = Field(default=None, ge=0.0, le=1.0)
    margin_action: Literal["review", "reject"] = "review"


class RunSummary(BaseModel):
    run_id: str
    kind: str
    status: str
    stage: str
    progress: float
    dataset: str
    dataset_kind: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    headline: dict | None = Field(default=None, description="Key numbers for list views (succeeded runs only).")
    error: str | None = None


class RunDetail(RunSummary):
    config: dict
    result: dict | None = None
    cancel_requested: bool = False


class RunsPage(BaseModel):
    items: list[RunSummary]
    total: int


class CheckpointModel(BaseModel):
    """A fine-tuned backbone found in backend/weights/finetuned/ (created by scripts/finetune_triplet.py)."""

    name: str
    dataset: str | None = None
    seed: int | None = Field(default=None, description="The protocol seed it was trained for: evaluate it with this seed only.")
    trained_people: int | None = None
    training_images: int | None = None
    validated: bool = Field(default=False, description="Always false until an evaluation on held-out people has been run.")
    size_mb: float
    modified: datetime


class DatasetModel(BaseModel):
    name: str
    layout: str
    kind: str
    description: str
    license_note: str
    identities: int
    images: int
    cameras: int
    available: bool
    problems: list[str]
