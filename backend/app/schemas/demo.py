"""Response shapes of the built-in example demo ("open-set analysis")."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .reid import FaceObservationModel


class DemoRules(BaseModel):
    """The decision rules the example is judged under (read from the ACTIVE policy; nothing is changed)."""

    matching_mode: str = Field(description="face_body | body")
    face_threshold: float
    face_review_band: float
    body_threshold: float
    policy_version: int
    policy_status: str
    face_models_loaded: bool


class DemoGroup(BaseModel):
    id: str
    title: str
    blurb: str


class DemoPhoto(BaseModel):
    name: str
    url: str
    face_status: str | None = Field(default=None, description="ready | weak | no_face (known after /prepare)")
    face_note: str | None = None


class DemoPerson(BaseModel):
    id: str
    label: str
    note: str
    photos: list[DemoPhoto]
    n_faces: int = 0


class DemoExpect(BaseModel):
    kind: Literal["match", "unknown", "review"]
    person: str | None = None
    person_label: str | None = None
    text: str = Field(description="The right answer in plain words, e.g. 'Enrolled: Example person 1 - should be MATCH'.")


class DemoCase(BaseModel):
    id: str
    group: str
    title: str
    story: str
    image_url: str
    expect: DemoExpect


class DemoInfo(BaseModel):
    available: bool
    reason: str | None = None
    title: str = ""
    intro: str = ""
    groups: list[DemoGroup] = Field(default_factory=list)
    people: list[DemoPerson] = Field(default_factory=list)
    cases: list[DemoCase] = Field(default_factory=list)
    rules: DemoRules | None = None
    disclaimer: str = ""


class DemoPrepared(BaseModel):
    people: list[DemoPerson]
    rules: DemoRules
    built_ms: float


class DemoCandidate(BaseModel):
    person: str
    label: str
    score: float
    basis: str
    face_score: float | None = None
    body_score: float | None = None


class DemoDecision(BaseModel):
    outcome: str = Field(description="accepted | unknown | review_required | processing_error")
    accepted_person: str | None = None
    accepted_label: str | None = None
    top1_person: str | None = None
    top1_label: str | None = None
    top1_score: float | None = None
    face_score: float | None = Field(default=None, description="Face similarity to the closest enrolled face (None = no usable face)")
    body_score: float | None = Field(default=None, description="Clothing-and-build similarity to the closest enrolled person")
    basis: str = "body"
    threshold: float | None = None
    reason: str
    verdict: Literal["correct", "review", "cautious", "false_accept", "wrong_person", "missed", "risky"]
    candidates: list[DemoCandidate] = Field(default_factory=list)


class DemoCaseResult(BaseModel):
    case_id: str
    face: FaceObservationModel | None = None
    face_body: DemoDecision
    clothes_only: DemoDecision
    timings_ms: dict[str, float]
