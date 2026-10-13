"""
The built-in example demo: an open-set analysis you can run with one click.

In plain words: an "open-set" system has two jobs at once - recognise the people it knows AND refuse everyone else. Showing
that needs photos with known right answers. The project ships a small set of public-domain photos plus a manifest
(``demo/samples/demo_manifest.json``) that says who is "enrolled" and which test photos are known people, strangers, or strangers
dressed exactly like an enrolled person. This module runs them through the SAME decision code the real screens use and reports,
for every photo, what the system decided, what the right answer was, and what a clothes-only matcher would have decided.

Safety by design - the example never touches your data:
  * the example people live in a PRIVATE, TEMPORARY gallery held in memory (a ``DemoSandbox``); the real gallery, the history,
    the audit trail and the stored files are not read or written;
  * nothing about the example photos or the answers is saved;
  * only the files named in the manifest can be served (no path can reach anything else).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from sqlalchemy.orm import Session

from ..core.errors import ModelUnavailable, NotFound
from ..cv.face.registry import FACE_DIM
from ..cv.geometry import pad_to_person_aspect
from ..cv.imaging import load_rgb_file
from ..cv.open_set.decision_engine import Decision
from ..cv.open_set.policy import DecisionPolicy, MultiCuePolicy
from ..cv.quality import assess_crop
from ..cv.retrieval.gallery_index import GalleryIndex, IndexEntry
from ..schemas.demo import (
    DemoCandidate,
    DemoCase,
    DemoCaseResult,
    DemoDecision,
    DemoExpect,
    DemoGroup,
    DemoInfo,
    DemoPerson,
    DemoPhoto,
    DemoPrepared,
    DemoRules,
)
from . import face_service, policy_service
from .matching import decide_person
from .runtime import Runtime

logger = logging.getLogger(__name__)

MANIFEST_NAME = "demo_manifest.json"
EXPECT_KINDS = ("match", "unknown", "review")
DISCLAIMER = (
    "A small demonstration with public-domain photographs, not a benchmark. The numbers describe these 13 photos only; accuracy on "
    "other cameras, lighting or groups of people has not been measured. Nothing from this example is saved."
)


# --------------------------------------------------------------------------------------------------------------- manifest
@dataclass
class Manifest:
    root: Path
    title: str
    intro: str
    groups: list[dict]
    people: list[dict]
    cases: list[dict]
    files: set[str] = field(default_factory=set)  # every relative path the manifest names (the only files that may be served)

    def person_label(self, person_id: str | None) -> str | None:
        return next((p["label"] for p in self.people if p["id"] == person_id), None)


def _safe_file(root: Path, relative: str) -> Path | None:
    """The real path of ``relative`` inside ``root``, or None if it does not exist or tries to leave the folder."""
    if not isinstance(relative, str) or not relative or relative.startswith(("/", "\\")) or ".." in Path(relative).parts:
        return None
    candidate = (root / relative).resolve()
    return candidate if candidate.is_file() and candidate.is_relative_to(root.resolve()) else None


def load_manifest(demo_dir: Path) -> tuple[Manifest | None, str | None]:
    """Read and validate the manifest. Returns (manifest, None) or (None, the plain-language reason it cannot be used)."""
    path = demo_dir / MANIFEST_NAME
    if not path.is_file():
        return None, (f"The example photos are not installed (no {MANIFEST_NAME} in {demo_dir}). "
                      "They ship in the project's demo/samples folder; run demo/prepare_faces.py if they were removed.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        people, cases, groups = list(raw["people"]), list(raw["cases"]), list(raw.get("groups", []))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, f"The example manifest could not be read: {exc}"

    ids = [p.get("id") for p in people]
    if not people or len(set(ids)) != len(ids) or not all(isinstance(i, str) and i for i in ids):
        return None, "The example manifest needs people with unique ids."
    group_ids = {g.get("id") for g in groups}
    files: set[str] = set()
    missing: list[str] = []
    for person in people:
        for photo in person.get("photos", []):
            (files.add(photo) if _safe_file(demo_dir, photo) else missing.append(photo))
    seen_cases: set[str] = set()
    for case in cases:
        expect = case.get("expect", {})
        if case.get("id") in seen_cases or expect.get("kind") not in EXPECT_KINDS or case.get("group") not in group_ids:
            return None, f"The example manifest has a bad case: {case.get('id')!r}."
        if expect["kind"] != "unknown" and expect.get("person") not in ids:
            return None, f"Case {case['id']!r} expects a person who is not in the example gallery."
        seen_cases.add(case["id"])
        (files.add(case["file"]) if _safe_file(demo_dir, case["file"]) else missing.append(case["file"]))
    if missing:
        return None, "Some example photos are missing: " + ", ".join(sorted(set(missing))[:4]) + (" ..." if len(set(missing)) > 4 else "")
    return Manifest(demo_dir, raw.get("title", "Open-set example"), raw.get("intro", ""), groups, people, cases, files), None


def file_url(relative: str) -> str:
    return f"/api/demo/files/{relative}"


def served_file(runtime: Runtime, relative: str) -> Path:
    """The path of one example photo, but only if the manifest names it (the manifest is the whitelist)."""
    manifest, _ = load_manifest(runtime.settings.demo_dir)
    if manifest is None or relative not in manifest.files:
        raise NotFound("No such example file.")
    path = _safe_file(manifest.root, relative)
    if path is None:
        raise NotFound("No such example file.")
    return path


# ---------------------------------------------------------------------------------------------------------------- rules
def _policies(session: Session) -> tuple[DecisionPolicy, DecisionPolicy, DecisionPolicy]:
    """(active policy, face + body policy, clothes-only policy). The active policy itself is never changed.

    If the active policy is body-only, the face + body column uses the recommended default face rules, so the example can
    still show the comparison.
    """
    active = policy_service.to_policy(policy_service.get_active(session))
    face_body = active if active.multicue is not None else replace(active, multicue=MultiCuePolicy())
    return active, face_body, replace(active, multicue=None)


def _rules(runtime: Runtime, session: Session) -> DemoRules:
    active, face_body, _ = _policies(session)
    multicue = face_body.multicue
    assert multicue is not None
    return DemoRules(
        matching_mode="face_body" if active.multicue else "body",
        face_threshold=multicue.face_accept_threshold, face_review_band=multicue.face_review_band,
        body_threshold=face_body.accept_threshold, policy_version=face_body.version, policy_status=face_body.status.value,
        face_models_loaded=runtime.face_engine is not None,
    )


# --------------------------------------------------------------------------------------------------------------- sandbox
@dataclass
class DemoSandbox:
    """The private example gallery. It looks like a ``Runtime`` to ``decide_person`` (index, face_index, face_engine)."""

    index: GalleryIndex
    face_index: GalleryIndex
    face_engine: object
    people: list[DemoPerson]
    built_ms: float


def _people_view(manifest: Manifest, face_status: dict[str, tuple[str, str | None]] | None = None) -> list[DemoPerson]:
    people = []
    for person in manifest.people:
        photos = []
        for name in person.get("photos", []):
            status, note = (face_status or {}).get(name, (None, None))
            photos.append(DemoPhoto(name=Path(name).name, url=file_url(name), face_status=status, face_note=note))
        people.append(DemoPerson(id=person["id"], label=person["label"], note=person.get("note", ""), photos=photos,
                                 n_faces=sum(1 for p in photos if p.face_status == "ready")))
    return people


def build_sandbox(runtime: Runtime, manifest: Manifest) -> DemoSandbox:
    """Embed the example people's reference photos into a temporary gallery (about a second on a laptop CPU)."""
    started = time.perf_counter()
    extractor = runtime.require_extractor()
    if runtime.face_engine is None:
        raise ModelUnavailable("The example compares faces, but the face models are not loaded. " + (runtime.face_error or "Run scripts\\download_weights.py and restart."))

    crops, owners, names = [], [], []
    for person in manifest.people:
        for name in person.get("photos", []):
            path = _safe_file(manifest.root, name)
            assert path is not None
            crops.append(pad_to_person_aspect(load_rgb_file(path)))  # like enrolling with "the image is already a person crop"
            owners.append(person["id"])
            names.append(name)
    body_vectors = extractor.embed(crops)

    body_entries, face_entries, face_status = [], [], {}
    for crop, owner, name, vector in zip(crops, owners, names, body_vectors, strict=True):
        uid = Path(name).stem
        body_entries.append(IndexEntry(owner, uid, vector))
        analysis = face_service.analyse_reference_crop(runtime.face_engine, crop)
        face_status[name] = (analysis.status, analysis.note)
        if analysis.status == "ready" and analysis.reading is not None and analysis.reading.embedding is not None:
            face_entries.append(IndexEntry(owner, uid, analysis.reading.embedding))

    index = GalleryIndex(dim=extractor.dim)
    index.replace(body_entries)
    face_index = GalleryIndex(dim=FACE_DIM)
    face_index.replace(face_entries)
    return DemoSandbox(index, face_index, runtime.face_engine, _people_view(manifest, face_status), round((time.perf_counter() - started) * 1000, 1))


def _sandbox(runtime: Runtime, manifest: Manifest, *, rebuild: bool = False) -> DemoSandbox:
    with runtime.demo_lock:
        if rebuild or not isinstance(runtime.demo_sandbox, DemoSandbox):
            runtime.demo_sandbox = build_sandbox(runtime, manifest)
        return runtime.demo_sandbox  # type: ignore[return-value]


# --------------------------------------------------------------------------------------------------------------- service
def _expect_text(expect: dict, manifest: Manifest) -> DemoExpect:
    label = manifest.person_label(expect.get("person"))
    text = {
        "match": f"Enrolled: {label}. The right answer is MATCH {label}.",
        "unknown": "Not enrolled - a stranger. The right answer is UNKNOWN.",
        "review": f"{label} is enrolled, but there is no usable face. The safe answer is REVIEW (a person should look).",
    }[expect["kind"]]
    return DemoExpect(kind=expect["kind"], person=expect.get("person"), person_label=label, text=text)


def info(runtime: Runtime, session: Session) -> DemoInfo:
    manifest, reason = load_manifest(runtime.settings.demo_dir)
    if manifest is None:
        return DemoInfo(available=False, reason=reason, disclaimer=DISCLAIMER)
    problem = None
    if runtime.extractor is None:
        problem = "The embedding model is not loaded. " + (runtime.extractor_error or "")
    elif runtime.face_engine is None:
        problem = "The face models are not loaded, so the example cannot compare faces. " + (runtime.face_error or "")
    return DemoInfo(
        available=problem is None, reason=problem.strip() if problem else None,
        title=manifest.title, intro=manifest.intro,
        groups=[DemoGroup(**g) for g in manifest.groups],
        people=_people_view(manifest),
        cases=[DemoCase(id=c["id"], group=c["group"], title=c["title"], story=c.get("story", ""), image_url=file_url(c["file"]),
                        expect=_expect_text(c["expect"], manifest)) for c in manifest.cases],
        rules=_rules(runtime, session), disclaimer=DISCLAIMER,
    )


def prepare(runtime: Runtime, session: Session) -> DemoPrepared:
    manifest, reason = load_manifest(runtime.settings.demo_dir)
    if manifest is None:
        raise NotFound(reason or "The example is not available.")
    sandbox = _sandbox(runtime, manifest, rebuild=True)
    return DemoPrepared(people=sandbox.people, rules=_rules(runtime, session), built_ms=sandbox.built_ms)


def verdict(kind: str, expected_person: str | None, outcome: str, accepted_person: str | None) -> str:
    """Was this decision right? (the one place that defines "right" for the example)"""
    accepted = outcome == "accepted"
    if kind == "match":
        if accepted:
            return "correct" if accepted_person == expected_person else "wrong_person"
        return "review" if outcome == "review_required" else "missed"
    if kind == "unknown":
        if accepted:
            return "false_accept"
        return "correct" if outcome == "unknown" else "review"
    # kind == "review": a known person with no usable face - accepting on clothing alone would be risky
    if accepted:
        return "risky"
    return "correct" if outcome == "review_required" else "cautious"


def _decision(decision: Decision | None, error: str | None, manifest: Manifest, expect: dict) -> DemoDecision:
    if decision is None:
        return DemoDecision(outcome="processing_error", reason=error or "This picture could not be processed.", verdict="missed" if expect["kind"] == "match" else "cautious")
    label = manifest.person_label
    candidates = [DemoCandidate(person=c.reference_id, label=label(c.reference_id) or c.reference_id, score=round(c.score, 4), basis=c.basis,
                                face_score=None if c.face_score is None else round(c.face_score, 4),
                                body_score=None if c.body_score is None else round(c.body_score, 4)) for c in decision.candidates]

    def r(value: float | None) -> float | None:
        return None if value is None else round(value, 4)

    reason = decision.reason
    for person in manifest.people:  # the engine names people by id ('person1'); the page shows their label ('Example person 1')
        reason = reason.replace(f"'{person['id']}'", f"'{person['label']}'")

    face_score = decision.top1_face_score if decision.basis == "face" else None
    body_score = decision.top1_body_score if decision.basis == "face" else decision.top1_score
    accepted = decision.accepted_reference_id
    return DemoDecision(
        outcome=decision.outcome.value, accepted_person=accepted, accepted_label=label(accepted) if accepted else None,
        top1_person=decision.top1_reference_id, top1_label=label(decision.top1_reference_id) if decision.top1_reference_id else None,
        top1_score=r(decision.top1_score), face_score=r(face_score), body_score=r(body_score), basis=decision.basis,
        threshold=decision.accept_threshold, reason=reason, candidates=candidates,
        verdict=verdict(expect["kind"], expect.get("person"), decision.outcome.value, accepted),  # type: ignore[arg-type]
    )


def analyse_case(runtime: Runtime, session: Session, case_id: str) -> DemoCaseResult:
    manifest, reason = load_manifest(runtime.settings.demo_dir)
    if manifest is None:
        raise NotFound(reason or "The example is not available.")
    case = next((c for c in manifest.cases if c["id"] == case_id), None)
    if case is None:
        raise NotFound(f"No such example case '{case_id}'.")
    extractor = runtime.require_extractor()
    sandbox = _sandbox(runtime, manifest)
    _, policy_fb, policy_body = _policies(session)

    started = time.perf_counter()
    path = _safe_file(manifest.root, case["file"])
    assert path is not None
    pixels = load_rgb_file(path)
    crop = pad_to_person_aspect(pixels)
    quality = assess_crop(crop)
    timings: dict[str, float] = {}
    if not quality.usable:
        error = quality.blocking_reason or "The picture is unusable."
        both = _decision(None, error, manifest, case["expect"])
        return DemoCaseResult(case_id=case_id, face=None, face_body=both, clothes_only=both, timings_ms={"total_ms": round((time.perf_counter() - started) * 1000, 1)})

    t = time.perf_counter()
    vector = extractor.embed([crop])[0]
    timings["embed_ms"] = round((time.perf_counter() - t) * 1000, 1)
    t = time.perf_counter()
    face = face_service.observe_query_face(runtime, pixels)
    timings["face_ms"] = round((time.perf_counter() - t) * 1000, 1)

    t = time.perf_counter()
    top_k = max(3, len(manifest.people))
    face_body = decide_person(sandbox, policy_fb, vector, body_flags=quality.flags, face=face, top_k=top_k)  # type: ignore[arg-type]
    clothes_only = decide_person(sandbox, policy_body, vector, body_flags=quality.flags, face=None, top_k=top_k)  # type: ignore[arg-type]
    timings["decide_ms"] = round((time.perf_counter() - t) * 1000, 1)
    timings["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return DemoCaseResult(
        case_id=case_id, face=face.observation(), timings_ms=timings,
        face_body=_decision(face_body, None, manifest, case["expect"]),
        clothes_only=_decision(clothes_only, None, manifest, case["expect"]),
    )


def forget(runtime: Runtime) -> None:
    """Drop the private example gallery from memory (it holds nothing worth keeping)."""
    with runtime.demo_lock:
        runtime.demo_sandbox = None


__all__ = ["analyse_case", "forget", "info", "load_manifest", "prepare", "served_file", "verdict"]
