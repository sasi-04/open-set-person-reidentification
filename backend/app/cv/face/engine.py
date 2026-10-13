"""
Face detection and face fingerprints.

In plain words: given a picture of a person this finds the face (if there is a usable one), judges whether the
face is good enough to trust, and turns it into 128 numbers (a "face embedding"). Two photos of the same face give
embeddings with a high cosine similarity; different people give low ones. It is the second kind of evidence next
to the whole-body fingerprint of ``cv/embedding``: a body fingerprint mostly captures clothing colour and build,
a face fingerprint captures the face itself.

Quality is checked before a face is allowed to decide anything. A face that is tiny, blurry, in strong profile or
only weakly detected is reported as NOT usable, with the reason - the matcher then falls back to body evidence
(and, by default, asks for human review instead of accepting on clothing alone).

Honest limits: this is ordinary 2-D face matching from photographs. It is not the 3-D depth sensing of a phone's
Face ID, it can be fooled by photos of photos, it degrades with masks, sunglasses, strong angles, low light and
tiny faces, and very similar faces (twins, close relatives) can score high. The measured accuracy is in
docs/FACE_AND_BODY_MATCHING.md.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ...core.errors import ModelUnavailable
from ..embedding.weights import sha256_of_file
from .registry import FACE_DETECTOR_FILE, FACE_DIM, FACE_RECOGNIZER_FILE, FaceModelFile

logger = logging.getLogger(__name__)

# ---- detection ---------------------------------------------------------------------------------
DETECT_SCORE_THRESHOLD = 0.70  # YuNet's own confidence needed before a face is even considered
NMS_THRESHOLD = 0.30
MAX_DETECT_SIDE = 1280  # larger pictures are shrunk for the detector only (faces are found at this scale)

# ---- "is this face good enough to decide anything?" (plain heuristics, listed in the docs) ----------
MIN_FACE_PX = 40  # shorter side of the face box, in the ORIGINAL picture's pixels
MIN_FACE_CONFIDENCE = 0.80
MAX_YAW_RATIO = 0.45  # |nose offset from the eye midline| / eye distance; ~0 = frontal, > 0.45 = strong profile
MIN_FACE_SHARPNESS = 10.0  # variance of the Laplacian of the aligned 112x112 face (blurrier = lower)

FACE_FLAG_TEXT = {
    "face_small": "The face is too small in the picture to compare reliably.",
    "face_blurry": "The face is out of focus.",
    "face_turned": "The face is turned too far away from the camera.",
    "face_low_confidence": "The face detector was not sure this is a face.",
}


@dataclass(frozen=True)
class FaceFound:
    """One face in the picture that was given to ``detect`` (coordinates are that picture's pixels)."""

    box: tuple[float, float, float, float]  # x1, y1, x2, y2
    landmarks: tuple[tuple[float, float], ...]  # right eye, left eye, nose tip, right/left mouth corner (as seen in the image)
    score: float
    row: np.ndarray = field(repr=False, compare=False)  # YuNet's raw 15 numbers, needed for alignment

    @property
    def width(self) -> float:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> float:
        return self.box[3] - self.box[1]

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.box[0] + self.box[2]) / 2, (self.box[1] + self.box[3]) / 2)

    def shifted(self, dx: float, dy: float) -> FaceFound:
        """The same face in the coordinates of a bigger picture this one was cut from."""
        row = self.row.copy()
        row[0] += dx
        row[1] += dy
        row[4:14:2] += dx
        row[5:14:2] += dy
        x1, y1, x2, y2 = self.box
        return FaceFound(
            (x1 + dx, y1 + dy, x2 + dx, y2 + dy), tuple((x + dx, y + dy) for x, y in self.landmarks), self.score, row
        )


@dataclass
class FaceQuality:
    usable: bool
    flags: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def reason(self) -> str | None:
        return " ".join(FACE_FLAG_TEXT[f] for f in self.flags) if self.flags else None


@dataclass
class FaceReading:
    """Everything the matcher needs about ONE face: where it is, how good it is, and its fingerprint."""

    found: FaceFound
    quality: FaceQuality
    embedding: np.ndarray | None  # (128,) float32, length 1; None only if the network could not process the face


def _yaw_ratio(face: FaceFound) -> float:
    (rx, _), (lx, _), (nx, _) = face.landmarks[0], face.landmarks[1], face.landmarks[2]
    eye_distance = abs(lx - rx)
    return 0.0 if eye_distance < 1e-6 else (nx - (rx + lx) / 2) / eye_distance


class FaceEngine:
    name = "yunet+sface"
    dim = FACE_DIM

    def __init__(self, detector: cv2.FaceDetectorYN, recognizer: cv2.FaceRecognizerSF, *, files: tuple[FaceModelFile, FaceModelFile],
                 load_seconds: float = 0.0) -> None:
        self._detector, self._recognizer = detector, recognizer
        self._lock = threading.Lock()  # OpenCV's networks are not safe to call from two threads at once
        self.files = files
        self.load_seconds = load_seconds
        self.fingerprint = f"face-{files[0].sha256[:8]}-{files[1].sha256[:8]}"

    # ---------------------------------------------------------------- loading
    @classmethod
    def load(cls, weights_dir: Path) -> FaceEngine:
        started = time.perf_counter()
        for spec in (FACE_DETECTOR_FILE, FACE_RECOGNIZER_FILE):
            path = weights_dir / spec.filename
            if not path.is_file():
                raise ModelUnavailable(
                    f"Face model {spec.filename} was not found at {path}. Run:  python scripts/download_weights.py",
                    details={"missing_file": str(path)},
                )
            actual = sha256_of_file(path)
            if actual != spec.sha256:
                raise ModelUnavailable(
                    f"The face model file {spec.filename} is corrupted or not the official file (SHA-256 mismatch). "
                    "Delete it and re-run scripts/download_weights.py.",
                    details={"expected_sha256": spec.sha256, "actual_sha256": actual},
                )
        try:
            detector = cv2.FaceDetectorYN.create(
                str(weights_dir / FACE_DETECTOR_FILE.filename), "", (320, 320), DETECT_SCORE_THRESHOLD, NMS_THRESHOLD, 50
            )
            recognizer = cv2.FaceRecognizerSF.create(str(weights_dir / FACE_RECOGNIZER_FILE.filename), "")
        except Exception as exc:  # OpenCV raises cv2.error for anything it cannot read
            raise ModelUnavailable(f"The face models could not be loaded by OpenCV: {exc}") from exc
        engine = cls(detector, recognizer, files=(FACE_DETECTOR_FILE, FACE_RECOGNIZER_FILE), load_seconds=time.perf_counter() - started)
        engine.detect(np.full((160, 160, 3), 127, dtype=np.uint8))  # warm-up, and proves the networks really run
        logger.info("Face models ready (%.2fs)", engine.load_seconds)
        return engine

    # -------------------------------------------------------------- detection
    def detect(self, rgb: np.ndarray) -> list[FaceFound]:
        """All faces in ``rgb`` (an RGB uint8 picture), best first. Empty list = no face."""
        height, width = rgb.shape[:2]
        if height < 16 or width < 16:
            return []
        scale = min(1.0, MAX_DETECT_SIDE / max(height, width))
        small = rgb if scale == 1.0 else cv2.resize(rgb, (max(16, round(width * scale)), max(16, round(height * scale))), interpolation=cv2.INTER_AREA)
        bgr = cv2.cvtColor(small, cv2.COLOR_RGB2BGR)
        with self._lock:
            self._detector.setInputSize((bgr.shape[1], bgr.shape[0]))
            _, rows = self._detector.detect(bgr)
        if rows is None:
            return []
        found = []
        for row in rows:
            row = np.asarray(row, dtype=np.float32).reshape(-1)
            if scale != 1.0:
                row[:14] /= scale
            x, y, w, h = (float(v) for v in row[:4])
            if w < 4 or h < 4 or not np.isfinite(row).all():
                continue
            landmarks = tuple((float(row[4 + 2 * i]), float(row[5 + 2 * i])) for i in range(5))
            found.append(FaceFound((x, y, x + w, y + h), landmarks, float(row[14]), row))
        found.sort(key=lambda f: f.score * f.width * f.height, reverse=True)
        return found

    def best_face(self, rgb: np.ndarray) -> FaceFound | None:
        """The face of THE person in a picture of one person.

        A picture taller than 1.4:1 is a whole-body crop: the face must be in its upper 70 % (a face on a poster
        or a second person's face lower down is ignored). A squarer picture is a head-and-shoulders photo: any face counts.
        """
        faces = self.detect(rgb)
        height, width = rgb.shape[:2]
        if height / max(width, 1) >= 1.4:
            faces = [f for f in faces if f.centre[1] <= 0.70 * height]
        return faces[0] if faces else None

    # ------------------------------------------------------- quality + fingerprint
    def read(self, rgb: np.ndarray, face: FaceFound) -> FaceReading:
        """Judge the face and compute its fingerprint (the fingerprint is computed even for a weak face)."""
        flags: list[str] = []
        metrics: dict[str, float] = {"face_px": round(min(face.width, face.height), 1), "detector_confidence": round(face.score, 3)}
        yaw = _yaw_ratio(face)
        metrics["turn"] = round(abs(yaw), 3)
        if min(face.width, face.height) < MIN_FACE_PX:
            flags.append("face_small")
        if face.score < MIN_FACE_CONFIDENCE:
            flags.append("face_low_confidence")
        if abs(yaw) > MAX_YAW_RATIO:
            flags.append("face_turned")

        embedding = None
        try:
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            with self._lock:
                aligned = self._recognizer.alignCrop(bgr, face.row)
                feature = np.asarray(self._recognizer.feature(aligned), dtype=np.float32).reshape(-1)
            norm = float(np.linalg.norm(feature))
            if feature.shape == (self.dim,) and np.isfinite(feature).all() and norm > 1e-6:
                embedding = (feature / norm).astype(np.float32)
            sharp = float(cv2.Laplacian(cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
            metrics["sharpness"] = round(sharp, 1)
            if sharp < MIN_FACE_SHARPNESS:
                flags.append("face_blurry")
        except cv2.error as exc:
            logger.warning("Face alignment/embedding failed: %s", exc)
        if embedding is None:
            return FaceReading(face, FaceQuality(False, flags, metrics), None)
        return FaceReading(face, FaceQuality(not flags, flags, metrics), embedding)

    def read_best(self, rgb: np.ndarray) -> FaceReading | None:
        """Find the face of the person in ``rgb`` and read it. None = no face found at all."""
        face = self.best_face(rgb)
        return None if face is None else self.read(rgb, face)

    def info(self) -> dict:
        return {
            "name": self.name, "display_name": "YuNet detector + SFace recogniser", "embedding_dim": self.dim,
            "fingerprint": self.fingerprint, "load_seconds": round(self.load_seconds, 3),
            "files": [{"role": f.role, "filename": f.filename, "sha256": f.sha256, "licence": f.licence, "source": f.source} for f in self.files],
            "weights_verified_against_pinned_hash": True,
            "usable_face_rules": {
                "min_face_px": MIN_FACE_PX, "min_detector_confidence": MIN_FACE_CONFIDENCE,
                "max_turn_ratio": MAX_YAW_RATIO, "min_sharpness": MIN_FACE_SHARPNESS,
            },
        }
