"""
Video Explorer: re-identify people in sampled frames of a PRERECORDED video.

In plain words: a video is just many pictures. We take one frame every N seconds
(you choose N), find the people in it, and ask the matcher the same question we ask
for a single photo - "which enrolled person is this, if any?" - using the same
detector, the same embedding model, the same gallery and the same decision rules
(``cv/open_set/decision_engine.py``). Every sampled frame is judged on its own.

What this is NOT: it is not a multi-object tracker. A person is never followed from
one frame to the next, nobody is tracked through occlusion, and no identity is
carried between frames. If the same enrolled person shows up in five frames you get
five independent MATCH decisions; "identities seen" below is just those decisions
grouped by name afterwards. The result says so in its own notes.

Safety: the upload is size-limited and read in chunks, its real container type is
checked from the first bytes (the file name and MIME type are never trusted), it is
stored under a random name, probed with OpenCV for sane dimensions and length, and
deleted as soon as processing ends - whether it succeeded, failed or was cancelled.
"""

from __future__ import annotations

import logging
import math
import re
import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
from fastapi import UploadFile
from sqlalchemy import select

from ..core.config import Settings
from ..core.errors import NotFound, PayloadTooLarge, UnsupportedImage, ValidationFailed
from ..cv.geometry import crop_region, pad_to_person_aspect
from ..cv.imaging import encode_jpeg
from ..cv.quality import assess_crop
from ..cv.retrieval.validation import InvalidEmbedding
from ..db.database import session_scope
from ..db.models import Identity
from ..evaluation.embedding_store import EvaluationCancelled
from ..evaluation.performance import percentiles
from . import policy_service
from .face_service import QueryFace, observe_query_face
from .matching import decide_person
from .runtime import Runtime

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm")
FRAME_THUMBNAIL_SIDE = 720  # longest side of the stored preview of each sampled frame
_SAFE_RUN_ID = re.compile(r"^[0-9a-f]{32}$")
ProgressFn = Callable[[str, float], None]


# =====================================================================================
# Accepting an upload
# =====================================================================================
def sniff_container(head: bytes) -> str | None:
    """Recognise the real container from its first bytes. ``None`` means "not a video we accept"."""
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "mp4"  # MP4 and QuickTime (.mov) share this layout
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "avi"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "mkv"  # Matroska and WebM
    return None


def safe_display_name(filename: str | None) -> str:
    """A harmless label for the screen (never used as a path): last path part, printable characters, 80 long."""
    name = Path((filename or "video").replace("\\", "/")).name
    cleaned = "".join(ch for ch in name if ch.isprintable())[:80].strip()
    return cleaned or "video"


def save_upload(settings: Settings, upload: UploadFile) -> tuple[Path, str, int]:
    """Stream the upload to disk under a random name. Returns (path, container, size in bytes)."""
    extension = Path(upload.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedImage(f"Unsupported video extension '{extension}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}.")

    settings.video_upload_dir.mkdir(parents=True, exist_ok=True)
    limit = settings.max_video_bytes
    first = upload.file.read(1 << 20)
    if not first:
        raise ValidationFailed("The uploaded video is empty.")
    container = sniff_container(first)
    if container is None:
        raise UnsupportedImage("The file content is not an MP4/MOV, AVI, MKV or WebM video (the file name was not trusted).")

    path = settings.video_upload_dir / f"{uuid.uuid4().hex}.{container}"
    size = 0
    try:
        with path.open("wb") as out:
            chunk = first
            while chunk:
                size += len(chunk)
                if size > limit:
                    raise PayloadTooLarge(f"The video is larger than the {settings.max_video_mb} MB limit.")
                out.write(chunk)
                chunk = upload.file.read(1 << 20)
    except BaseException:
        path.unlink(missing_ok=True)  # never leave a half-written upload behind
        raise
    return path, container, size


# =====================================================================================
# Looking at the video before accepting the job
# =====================================================================================
@dataclass(frozen=True)
class VideoProbe:
    width: int
    height: int
    fps: float
    frame_count: int | None  # None when the container does not say
    duration_seconds: float | None
    container: str

    def to_dict(self) -> dict:
        return {"width": self.width, "height": self.height, "fps": round(self.fps, 3), "frame_count": self.frame_count,
                "duration_seconds": None if self.duration_seconds is None else round(self.duration_seconds, 2),
                "container": self.container}


def probe_video(path: Path, settings: Settings, container: str) -> VideoProbe:
    """Open the file with OpenCV and refuse unreadable, oversized or too-long videos."""
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise UnsupportedImage("The video could not be opened. It may be corrupted or use an unsupported codec.")
        width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        decoded, _ = capture.read()
        if not decoded:
            raise UnsupportedImage("The first frame of the video could not be decoded. The file may be corrupted.")
    finally:
        capture.release()

    if min(width, height) < settings.min_image_side:
        raise ValidationFailed(f"The video frames are too small ({width}x{height}px).")
    if max(width, height) > settings.max_video_side:
        raise ValidationFailed(f"The video frames are too large ({width}x{height}px); the longest side may be {settings.max_video_side}px.")
    if not math.isfinite(fps) or fps <= 0 or fps > 1000:
        fps = 0.0  # unknown: sampling falls back to reading in real time order with a conservative guess
    frame_count = count if count > 0 else None
    duration = (frame_count / fps) if (frame_count and fps) else None
    if duration is not None and duration > settings.max_video_seconds:
        raise ValidationFailed(f"The video is {duration:.0f} s long; the limit is {settings.max_video_seconds} s.")
    return VideoProbe(width, height, fps, frame_count, duration, container)


def validate_sampling(settings: Settings, every_seconds: float, max_frames: int) -> None:
    if not math.isfinite(every_seconds) or not 0.1 <= every_seconds <= 60:
        raise ValidationFailed("Sample interval must be between 0.1 and 60 seconds.")
    if not 1 <= max_frames <= settings.max_video_frames:
        raise ValidationFailed(f"Maximum frames must be between 1 and {settings.max_video_frames}.")


# =====================================================================================
# Frame thumbnails (kept briefly, like query crops)
# =====================================================================================
def frame_folder(settings: Settings, run_id: str) -> Path:
    if not _SAFE_RUN_ID.fullmatch(run_id or ""):
        raise NotFound("No such video job.")
    return settings.video_frame_dir / run_id


def frame_path(settings: Settings, run_id: str, index: int) -> Path:
    path = frame_folder(settings, run_id) / f"f{int(index):04d}.jpg"
    if not path.is_file():
        raise NotFound("This frame preview is not available (it may have expired - previews are deleted after the retention window).")
    return path


def delete_artifacts(settings: Settings, run_id: str) -> None:
    folder = frame_folder(settings, run_id)
    shutil.rmtree(folder, ignore_errors=True)


def remove_expired(settings: Settings) -> int:
    """Delete frame folders older than the query-crop retention, and stray uploads older than an hour."""
    removed = 0
    now = datetime.now(UTC)
    keep_for = timedelta(hours=max(settings.query_retention_hours, 1))
    for folder in settings.video_frame_dir.glob("*"):
        if folder.is_dir() and _SAFE_RUN_ID.fullmatch(folder.name):
            if now - datetime.fromtimestamp(folder.stat().st_mtime, UTC) > keep_for:
                shutil.rmtree(folder, ignore_errors=True)
                removed += 1
    for upload in settings.video_upload_dir.glob("*"):
        if upload.is_file() and now - datetime.fromtimestamp(upload.stat().st_mtime, UTC) > timedelta(hours=1):
            upload.unlink(missing_ok=True)
            removed += 1
    return removed


# =====================================================================================
# Processing
# =====================================================================================
def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def _thumbnail(rgb: np.ndarray) -> np.ndarray:
    height, width = rgb.shape[:2]
    scale = FRAME_THUMBNAIL_SIDE / max(height, width)
    if scale >= 1:
        return rgb
    return cv2.resize(rgb, (max(1, round(width * scale)), max(1, round(height * scale))), interpolation=cv2.INTER_AREA)


def _person_entry(index: int, detection, usable: bool, quality, decision, face: QueryFace | None = None) -> dict:
    entry = {
        "index": index, "box": [round(v, 1) for v in detection.box.as_list()], "detector_score": round(detection.score, 4),
        "usable": usable, "quality_flags": list(quality.flags), "blocking_reason": quality.blocking_reason,
    }
    if face is not None:  # face matching is on: say what the face analysis saw, whatever the decision
        entry.update(face_status=face.status, face_box=face.box, face_flags=list(face.flags))
    if decision is None:
        entry.update(outcome="processing_error", reason_code="crop_unusable",
                     reason=quality.blocking_reason or "The person crop is unusable.")
    else:
        def r(value):
            return None if value is None else round(value, 5)

        entry.update(
            outcome=decision.outcome.value, reason_code=decision.reason_code, reason=decision.reason,
            accepted_reference_id=decision.accepted_reference_id, top1_reference_id=decision.top1_reference_id,
            top1_score=r(decision.top1_score), top2_score=r(decision.top2_score), margin=r(decision.margin),
            calibrated_confidence=r(decision.calibrated_confidence),
        )
        if face is not None:
            entry.update(basis=decision.basis, top1_face_score=r(decision.top1_face_score), top1_body_score=r(decision.top1_body_score),
                         accept_threshold=decision.accept_threshold)
    return entry


def process_video(runtime: Runtime, run_id: str, config: dict, path: Path, progress: ProgressFn,
                  cancelled: Callable[[], bool]) -> dict:
    """Sample frames, re-identify the people in each, and return the full JSON result."""
    settings = runtime.settings
    extractor, detector = runtime.require_extractor(), runtime.require_detector()
    with session_scope(runtime.session_factory) as session:
        policy_row = policy_service.get_active(session)
        policy, policy_note = policy_service.effective_policy(runtime, policy_row)
        confidence_model = policy_service.confidence_model_for(policy_row, runtime.fingerprint)

    every_seconds, max_frames = float(config["every_seconds"]), int(config["max_frames"])
    probe = VideoProbe(**{k: v for k, v in config["probe"].items()})
    fps = probe.fps or 25.0  # unknown frame rate: assume 25 so "every N seconds" still means something sensible
    step = max(1, round(every_seconds * fps))
    expected = max_frames if probe.frame_count is None else min(max_frames, math.ceil(probe.frame_count / step))
    keep_frames = settings.query_retention_hours > 0
    folder = frame_folder(settings, run_id)
    if keep_frames:
        folder.mkdir(parents=True, exist_ok=True)

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValidationFailed("The video could not be opened for processing.")
    frames: list[dict] = []
    frame_no = -1
    started = time.perf_counter()
    try:
        while len(frames) < max_frames:
            if cancelled():
                raise EvaluationCancelled()
            frame_no += 1
            decode_started = time.perf_counter()
            if not capture.grab():  # end of the video
                break
            if frame_no % step:
                continue  # skipped frames are only advanced past, never decoded to pixels
            ok, bgr = capture.retrieve()
            if not ok:
                break
            time_seconds = frame_no / fps
            if time_seconds > settings.max_video_seconds:
                break
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            decode_ms = _ms(decode_started)

            frames.append(_process_frame(runtime, extractor, detector, policy, confidence_model, rgb,
                                         index=len(frames), frame_no=frame_no, time_seconds=time_seconds, decode_ms=decode_ms,
                                         save_to=folder if keep_frames else None))
            progress(f"Frame {len(frames)} of about {expected}", min(0.97, len(frames) / max(expected, 1)))
    finally:
        capture.release()
    if not frames:
        raise ValidationFailed("No frame could be read from the video.")

    return _build_result(runtime, config, probe, policy, frames, elapsed_seconds=time.perf_counter() - started,
                         thumbnails_kept=keep_frames, step=step, fps=fps, policy_note=policy_note)


def _process_frame(runtime, extractor, detector, policy, confidence_model, rgb: np.ndarray, *, index: int, frame_no: int,
                   time_seconds: float, decode_ms: float, save_to: Path | None) -> dict:
    height, width = rgb.shape[:2]
    started = time.perf_counter()
    detections = detector.detect(rgb)
    detect_ms = _ms(started)

    started = time.perf_counter()
    crops, regions, qualities = [], [], []
    for detection in detections:
        region, origin = crop_region(rgb, detection.box)
        crop = pad_to_person_aspect(region)
        crops.append(crop)
        regions.append((region, origin))
        qualities.append(assess_crop(crop, source_box=detection.box, image_size=(width, height), detector_score=detection.score))
    usable_rows = [i for i, q in enumerate(qualities) if q.usable]
    embeddings = extractor.embed([crops[i] for i in usable_rows]) if usable_rows else np.zeros((0, extractor.dim), dtype=np.float32)
    embed_ms = _ms(started)
    vector_of = dict(zip(usable_rows, embeddings, strict=True))

    started = time.perf_counter()
    faces: dict[int, QueryFace] = {}
    if policy.multicue is not None:  # face matching: find and judge each person's face (frame pixels, not the padded crop)
        for i in usable_rows:
            faces[i] = observe_query_face(runtime, regions[i][0], regions[i][1])
    face_ms = _ms(started)

    started = time.perf_counter()
    people = []
    for i, detection in enumerate(detections):
        decision, problem = None, None
        if i in vector_of:
            try:
                decision = decide_person(runtime, policy, vector_of[i], body_flags=qualities[i].flags, face=faces.get(i), top_k=5,
                                         confidence_model=confidence_model)
            except InvalidEmbedding as exc:  # a broken fingerprint is an error for this person, not an "unknown"
                problem = ("invalid_embedding", exc.message)
        entry = _person_entry(i, detection, i in vector_of, qualities[i], decision, faces.get(i))
        if problem:
            entry.update(outcome="processing_error", reason_code=problem[0], reason=problem[1])
        people.append(entry)
    match_ms = _ms(started)

    thumbnail = None
    if save_to is not None:
        thumbnail = f"f{index:04d}.jpg"
        (save_to / thumbnail).write_bytes(encode_jpeg(_thumbnail(rgb), quality=75))
    return {
        "index": index, "frame_number": frame_no, "time_seconds": round(time_seconds, 3), "width": width, "height": height,
        "thumbnail": thumbnail, "people": people,
        "timings_ms": {"decode_ms": decode_ms, "detect_ms": detect_ms, "embed_ms": embed_ms, "face_ms": face_ms, "match_ms": match_ms,
                       "processing_ms": round(detect_ms + embed_ms + face_ms + match_ms, 2)},
    }


def _build_result(runtime: Runtime, config: dict, probe: VideoProbe, policy, frames: list[dict], *, elapsed_seconds: float,
                  thumbnails_kept: bool, step: int, fps: float, policy_note: str | None = None) -> dict:
    outcomes: dict[str, int] = {}
    seen: dict[str, dict] = {}
    for frame in frames:
        for person in frame["people"]:
            outcomes[person["outcome"]] = outcomes.get(person["outcome"], 0) + 1
            reference = person.get("accepted_reference_id")
            if reference:
                entry = seen.setdefault(reference, {"reference_id": reference, "frames": 0, "first_seen_seconds": frame["time_seconds"],
                                                    "last_seen_seconds": frame["time_seconds"], "best_score": 0.0})
                entry["frames"] += 1
                entry["last_seen_seconds"] = frame["time_seconds"]
                entry["best_score"] = max(entry["best_score"], person["top1_score"] or 0.0)
    if seen:
        with runtime.session_factory() as session:
            labels = dict(session.execute(select(Identity.reference_id, Identity.label).where(Identity.reference_id.in_(list(seen)))).all())
        for reference, entry in seen.items():
            entry["label"] = labels.get(reference)

    notes = [
        "Each sampled frame is judged on its own. A person is NOT followed from frame to frame, nothing is tracked through "
        "occlusion, and no identity is carried between frames - this is frame-by-frame re-identification, not multi-object tracking.",
        "'Identities seen' only groups the independent MATCH decisions by name after the fact; gaps between frames say nothing about where a person was.",
    ]
    if policy_note:
        notes.append(policy_note)
    if policy.multicue is not None:
        notes.append("Face + body matching: in every frame the face decides when a usable face is visible (people seen from behind, "
                     "far away or blurred have no usable face and fall back to the body, which by policy asks for review instead of a MATCH).")
    if policy.status.value != "calibrated":
        notes.append(f"The active decision policy is '{policy.status.value}': its threshold has not been calibrated on held-out data.")
    if runtime.index.snapshot.n_identities == 0:
        notes.append("The gallery is empty, so every detected person is reported as unknown.")
    if not thumbnails_kept:
        notes.append("Frame previews were not stored because query-image retention is set to 0 hours.")

    processing = [f["timings_ms"]["processing_ms"] for f in frames]
    people_total = sum(outcomes.values())
    extractor = runtime.require_extractor()
    return {
        "schema_version": 1, "kind": "video",
        "metadata": {
            "original_name": config["original_name"], "video": probe.to_dict(),
            "sampling": {"every_seconds": config["every_seconds"], "max_frames": config["max_frames"], "every_n_frames": step,
                         "assumed_fps": None if probe.fps else round(fps, 2), "frames_processed": len(frames)},
            "policy": {"version": policy.version, "status": policy.status.value, "accept_threshold": policy.accept_threshold,
                       "min_margin": policy.min_margin, "matching_mode": "face_body" if policy.multicue else "body",
                       "face_accept_threshold": policy.multicue.face_accept_threshold if policy.multicue else None},
            "face_model": runtime.face_engine.fingerprint if (runtime.face_engine and policy.multicue) else None,
            "model": {"name": extractor.name, "fingerprint": extractor.fingerprint, "device": extractor.info()["device"]},
            "detector": runtime.detector.name if runtime.detector else None,
            "thumbnails_kept": thumbnails_kept, "retention_hours": runtime.settings.query_retention_hours,
            "generated_at": datetime.now(UTC).isoformat(),
        },
        "frames": frames,
        "summary": {
            "frames_processed": len(frames), "people_detected": people_total, "outcomes": outcomes,
            "identities_seen": sorted(seen.values(), key=lambda e: -e["frames"]),
            "latency_ms": {
                "processing_per_frame": percentiles(processing),
                "note": "detection + embedding + matching for one frame, measured; video decoding is reported separately per frame.",
            },
            "wall_seconds": round(elapsed_seconds, 2),
            "frames_per_second_processed": round(len(frames) / elapsed_seconds, 2) if elapsed_seconds > 0 else None,
        },
        "notes": notes,
    }


def frames_csv(result: dict) -> str:
    """One row per detected person per sampled frame."""
    import csv
    import io

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["frame", "time_seconds", "person", "outcome", "accepted_reference_id", "top1_reference_id", "top1_score",
                     "margin", "detector_score", "quality_flags", "reason", "processing_ms",
                     "decided_by", "face_status", "top1_face_score", "top1_body_score"])
    for frame in result["frames"]:
        for person in frame["people"]:
            def cell(key):
                return person.get(key) if person.get(key) is not None else ""

            writer.writerow([frame["index"], frame["time_seconds"], person["index"], person["outcome"],
                             person.get("accepted_reference_id") or "", person.get("top1_reference_id") or "",
                             cell("top1_score"), cell("margin"), person["detector_score"],
                             ";".join(person["quality_flags"]), person["reason"], frame["timings_ms"]["processing_ms"],
                             cell("basis"), cell("face_status"), cell("top1_face_score"), cell("top1_body_score")])
    return out.getvalue()
