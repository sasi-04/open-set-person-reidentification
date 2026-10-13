"""
Face analysis for the gallery and for queries.

In plain words: this is the glue between the face engine (``cv/face``) and the rest of the application.

  * For a REFERENCE photo it finds the face, judges it, stores its fingerprint and the hair / skin / clothing colours
    in the ``face_templates`` table, so a query never has to re-read old pictures.
  * For a QUERY it does the same on the fly and returns what the matcher needs.
  * ``analyse_missing_faces`` upgrades galleries enrolled before faces existed (it reads the stored reference pictures;
    nothing is re-uploaded and nothing leaves the machine).

A face is only allowed to decide something when it is a USABLE face (large enough, sharp enough, not in strong profile).
A reference photo whose face is not usable is still used for body matching; it just contributes no face fingerprint.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cv.face.appearance import Cue, compare_cues, extract_cues
from ..cv.face.engine import FACE_FLAG_TEXT, FaceEngine, FaceReading
from ..cv.geometry import PAD_COLOUR as _PAD_COLOUR
from ..cv.imaging import load_rgb_file
from ..db.models import FaceTemplate, ReferenceImage, utcnow
from ..schemas.reid import CueRowModel, FaceObservationModel
from .audit import record_audit
from .runtime import Runtime

logger = logging.getLogger(__name__)

STARTUP_ANALYSIS_LIMIT = 300  # at startup, analyse at most this many not-yet-analysed reference pictures (about a minute at worst)


# ----------------------------------------------------------------------------------------- helpers
def trim_padding(crop: np.ndarray) -> tuple[np.ndarray, int, int]:
    """Remove the grey bars ``pad_to_person_aspect`` added around a crop. Returns (content, top offset, left offset).

    Face and colour analysis must look at real picture content only: the bars would confuse the face detector and the
    clothing-colour regions. A bar is a border row/column that is entirely the pad colour (JPEG noise tolerated).
    """
    if crop.size == 0:
        return crop, 0, 0
    is_pad = np.abs(crop.astype(np.int16) - np.array(_PAD_COLOUR, dtype=np.int16)).max(axis=2) <= 16
    rows, cols = np.where(~is_pad.all(axis=1))[0], np.where(~is_pad.all(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return crop, 0, 0
    top, bottom, left, right = int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1
    return crop[top:bottom, left:right], top, left


def cues_to_json(cues: dict[str, Cue]) -> dict:
    return {name: {"rgb": list(cue.rgb), "label": cue.label} for name, cue in cues.items()}


def cues_from_json(data: dict | None) -> dict[str, Cue]:
    return {name: Cue(name, tuple(v["rgb"]), v["label"]) for name, v in (data or {}).items()}  # type: ignore[arg-type]


def explain(status: str, flags: list[str]) -> str | None:
    if status == "ready":
        return None
    if status == "weak":
        return "A face was found but is not good enough to use: " + " ".join(FACE_FLAG_TEXT.get(f, f) for f in flags)
    if status == "no_face":
        return "No face was found in this picture (a back view, or the person is too small). It is still used for body matching."
    if status == "stale":
        return "The face fingerprint was made by a different face model. Use 'Analyse faces' to refresh it."
    if status == "failed":
        return "The face analysis failed on this picture."
    return "Not analysed yet. Use 'Analyse faces'."


# --------------------------------------------------------------------------------- reference pictures
@dataclass
class ReferenceAnalysis:
    status: str  # ready | weak | no_face | failed
    reading: FaceReading | None
    face_box: list[float] | None  # in the coordinates of the STORED (possibly padded) reference picture
    cues: dict[str, Cue] = field(default_factory=dict)

    @property
    def flags(self) -> list[str]:
        return self.reading.quality.flags if self.reading else []

    @property
    def note(self) -> str | None:
        return explain(self.status, self.flags)


def analyse_reference_crop(engine: FaceEngine, crop: np.ndarray) -> ReferenceAnalysis:
    """Analyse one stored reference crop (RGB). Never raises: a failure becomes status 'failed'."""
    try:
        content, top, left = trim_padding(crop)
        reading = engine.read_best(content)
        box = None if reading is None else [round(v, 1) for v in (reading.found.box[0] + left, reading.found.box[1] + top,
                                                                    reading.found.box[2] + left, reading.found.box[3] + top)]
        cues = extract_cues(content, None if reading is None else reading.found.box)
    except Exception:  # a broken image must not sink an enrolment
        logger.exception("Face analysis of a reference crop failed")
        return ReferenceAnalysis("failed", None, None)
    if reading is None:
        return ReferenceAnalysis("no_face", None, None, cues)
    if reading.embedding is None:
        return ReferenceAnalysis("failed", reading, box, cues)
    return ReferenceAnalysis("ready" if reading.quality.usable else "weak", reading, box, cues)


def store_template(session: Session, runtime: Runtime, image: ReferenceImage, analysis: ReferenceAnalysis) -> FaceTemplate:
    """Create or replace the face record of one reference image (the caller commits)."""
    engine = runtime.face_engine
    template = image.face or FaceTemplate()
    template.status = analysis.status
    keep = analysis.reading is not None and analysis.reading.embedding is not None and analysis.status in ("ready", "weak")
    template.embedding = analysis.reading.embedding.astype(np.float32).tobytes() if keep else None
    template.embedding_model = engine.fingerprint if engine else None
    template.embedding_dim = engine.dim if (engine and keep) else None
    template.face_box = analysis.face_box
    template.detector_score = round(analysis.reading.found.score, 4) if analysis.reading else None
    template.flags = list(analysis.flags)
    template.metrics = dict(analysis.reading.quality.metrics) if analysis.reading else {}
    template.cues = cues_to_json(analysis.cues)
    template.created_at = utcnow()
    if image.face is None:
        image.face = template
    return template


def analyse_missing_faces(session: Session, runtime: Runtime, role_name: str, *, limit: int | None = None, everything: bool = False) -> dict:
    """Analyse reference pictures that have no current face record (or ALL of them when ``everything``).

    Safe to run any time: it reads the stored reference crops, writes only ``face_templates`` rows, then refreshes the index.
    """
    engine = runtime.face_engine
    if engine is None:
        return {"analysed": 0, "usable": 0, "without_usable_face": 0, "failed": 0, "skipped_unreadable": 0, "remaining": 0,
                "message": runtime.face_error or "The face models are not loaded."}
    images = list(session.scalars(select(ReferenceImage).order_by(ReferenceImage.id)))
    todo = [i for i in images if everything or i.face is None or i.face.status in ("stale", "failed") or i.face.embedding_model != engine.fingerprint]
    batch = todo if limit is None else todo[:limit]
    counts = {"ready": 0, "weak": 0, "no_face": 0, "failed": 0}
    unreadable = 0
    started = time.perf_counter()
    for image in batch:
        try:
            crop = load_rgb_file(runtime.references.path_for(image.file_path))
        except Exception:
            logger.warning("Reference image %s could not be read for face analysis", image.image_uid)
            unreadable += 1
            continue
        analysis = analyse_reference_crop(engine, crop)
        store_template(session, runtime, image, analysis)
        counts[analysis.status] += 1
    session.flush()
    if batch:
        record_audit(session, role_name, "gallery.analyse_faces", None, **counts, unreadable=unreadable)
    runtime.sync_gallery(session)
    session.commit()
    logger.info("Face analysis: %s, %d unreadable, %.1fs", counts, unreadable, time.perf_counter() - started)
    return {"analysed": len(batch) - unreadable, "usable": counts["ready"], "without_usable_face": counts["weak"] + counts["no_face"],
            "failed": counts["failed"], "skipped_unreadable": unreadable, "remaining": len(todo) - len(batch),
            "message": f"Analysed {len(batch) - unreadable} reference picture(s): {counts['ready']} with a usable face."}


# ----------------------------------------------------------------------------------------------- queries
@dataclass
class QueryFace:
    """What the matcher knows about the face in a query picture."""

    status: str  # not_used | no_face | unusable | usable
    reading: FaceReading | None = None
    box: list[float] | None = None  # in the uploaded image's pixels
    cues: dict[str, Cue] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    @property
    def vector(self) -> np.ndarray | None:
        return self.reading.embedding if (self.reading and self.status == "usable") else None

    def observation(self) -> FaceObservationModel:
        r = self.reading
        message = {
            "not_used": "Face matching is not active for this decision.",
            "no_face": "No face was found in this picture, so only the body could be compared.",
            "usable": "A usable face was found and compared.",
        }.get(self.status) or ("A face was found but it is not usable: " + " ".join(FACE_FLAG_TEXT.get(f, f) for f in self.flags))
        return FaceObservationModel(
            status=self.status, box=self.box, detector_score=None if r is None else round(r.found.score, 3),
            face_px=None if r is None else r.quality.metrics.get("face_px"), flags=self.flags, message=message,
        )


def observe_query_face(runtime: Runtime, region: np.ndarray, origin: tuple[int, int] = (0, 0)) -> QueryFace:
    """Find and judge the face of the person shown in ``region`` (RGB). ``origin`` = where ``region`` sits in the uploaded image."""
    engine = runtime.face_engine
    if engine is None:
        return QueryFace("not_used")
    try:
        reading = engine.read_best(region)
    except Exception:
        logger.exception("Face analysis of a query failed")
        return QueryFace("no_face")
    if reading is None:
        return QueryFace("no_face", cues=extract_cues(region, None))
    dx, dy = origin
    x1, y1, x2, y2 = reading.found.box
    box = [round(x1 + dx, 1), round(y1 + dy, 1), round(x2 + dx, 1), round(y2 + dy, 1)]
    cues = extract_cues(region, reading.found.box)
    if reading.quality.usable and reading.embedding is not None:
        return QueryFace("usable", reading, box, cues, [])
    return QueryFace("unusable", reading, box, cues, list(reading.quality.flags) or ["face_low_confidence"])


def cue_rows(session: Session, query_cues: dict[str, Cue], image_uid: str | None) -> list[CueRowModel]:
    """Line up the query's colours with the stored colours of one reference picture (the closest one)."""
    if not query_cues or not image_uid:
        return []
    template = session.scalar(select(FaceTemplate).join(ReferenceImage, ReferenceImage.id == FaceTemplate.image_id).where(ReferenceImage.image_uid == image_uid))
    if template is None or not template.cues:
        return []
    return [CueRowModel(**row) for row in compare_cues(query_cues, cues_from_json(template.cues))]
