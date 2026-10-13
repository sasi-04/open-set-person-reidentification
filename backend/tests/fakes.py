"""
Stand-ins for the neural networks, used ONLY in tests.

In plain words: the real OSNet takes ~0.2 s per image on a CPU and the real
detector about a second, which would make a few hundred API tests crawl. These
fakes keep the same interface but compute a deterministic embedding from the
image's mean colour, so a "person" is just a colour. Tests built on them prove
that the PLUMBING is right (routes, rules, storage, security); they say
nothing about how accurate the real model is - that is what the evaluation
pipeline on a real dataset is for.
"""

from __future__ import annotations

import io
import time

import numpy as np
from PIL import Image

from app.cv.detection.detector import Detection
from app.cv.face.engine import FaceFound, FaceQuality, FaceReading
from app.cv.geometry import Box

# Distinct, well-separated "people" (RGB).
RED, GREEN, BLUE, YELLOW, PURPLE = (220, 30, 30), (30, 200, 40), (30, 50, 220), (230, 220, 30), (160, 40, 190)


class FakeExtractor:
    name = "fake-osnet"
    dim = 16
    batch_size = 8
    use_flip_tta = False
    weights_sha256 = "f" * 64

    def __init__(self, noise: float = 0.0, delay: float = 0.0, seed: int = 0, fingerprint: str = "fake-osnet-ffffffffffff-flip0"):
        self.projection = np.random.default_rng(seed).normal(size=(3, self.dim))
        self.noise, self.delay, self.calls = noise, delay, 0
        self.fingerprint = fingerprint
        self._rng = np.random.default_rng(seed + 1)

    def _embed(self, crops, shift: float = 0.0):
        if self.delay:
            time.sleep(self.delay)
        self.calls += len(crops)
        colours = np.stack([c.reshape(-1, 3).mean(axis=0) / 255.0 - 0.5 for c in crops])  # centred colour
        vectors = colours @ self.projection + self._rng.normal(0, self.noise, (len(crops), self.dim)) + shift
        return (vectors / np.linalg.norm(vectors, axis=1, keepdims=True)).astype(np.float32)

    def embed(self, crops):
        return self._embed(crops)

    def embed_mirrored(self, crops):
        return self._embed(crops, shift=0.001)

    def info(self):
        return {
            "architecture": "Fake OSNet", "name": self.name, "embedding_dim": self.dim, "device": "cpu",
            "weights": "fake weights", "weights_sha256": self.weights_sha256, "load_seconds": 0.0, "warmup_seconds": 0.0,
            "fingerprint": self.fingerprint, "flip_tta": False, "input_size": [256, 128], "parameters": 1,
            "weights_verified_against_pinned_hash": True, "weights_license": "test", "weights_source": "test",
            "training_data": "none",
        }


class FakeDetector:
    name = "fake-detector"

    def __init__(self):
        self.boxes: list[Detection] = []

    def detect(self, pixels):
        return list(self.boxes)

    def info(self):
        return {"name": self.name, "display_name": "Fake detector", "device": "cpu", "score_threshold": 0.5,
                "weights_source": "test", "load_seconds": 0.0}


class FakeFaceEngine:
    """Stands in for YuNet + SFace. A 'face' is a block of pixels with a dark frame that ``person_png`` draws; its identity is the
    block's fill colour. Like the other fakes it proves the PLUMBING and the decision rules, not recognition accuracy."""

    name = "fake-face"
    dim = 128
    fingerprint = "face-fake0000-fake0000"
    load_seconds = 0.0
    files = ()

    def __init__(self, seed: int = 5):
        self.projection = np.random.default_rng(seed).normal(size=(3, self.dim))
        self.calls = 0

    def _frame_box(self, rgb):
        dark = (rgb < 60).all(axis=2)
        ys, xs = np.where(dark)
        if len(xs) < 100:
            return None
        return float(xs.min()), float(ys.min()), float(xs.max()) + 1, float(ys.max()) + 1

    def detect(self, rgb):
        box = self._frame_box(rgb)
        if box is None:
            return []
        x1, y1, x2, y2 = box
        mid = ((x1 + x2) / 2, (y1 + y2) / 2)
        return [FaceFound(box, ((x1, y1), (x2, y1), mid, (x1, y2), (x2, y2)), 0.95, np.zeros(15, dtype=np.float32))]

    def best_face(self, rgb):
        faces = self.detect(rgb)
        return faces[0] if faces else None

    def read(self, rgb, face):
        self.calls += 1
        x1, y1, x2, y2 = (int(v) for v in face.box)
        inner = rgb[y1 + 5 : y2 - 5, x1 + 5 : x2 - 5].reshape(-1, 3).mean(axis=0) / 255.0 - 0.5
        vector = inner @ self.projection
        vector = (vector / np.linalg.norm(vector)).astype(np.float32)
        flags = ["face_small"] if min(face.width, face.height) < 40 else []
        return FaceReading(face, FaceQuality(not flags, flags, {"face_px": min(face.width, face.height)}), vector)

    def read_best(self, rgb):
        face = self.best_face(rgb)
        return None if face is None else self.read(rgb, face)

    def info(self):
        return {"name": self.name, "display_name": "Fake face engine", "embedding_dim": self.dim, "fingerprint": self.fingerprint,
                "load_seconds": 0.0, "files": [], "weights_verified_against_pinned_hash": True, "usable_face_rules": {}}


def person_png(body, face=None, *, size=(120, 300), face_px=60, seed=0, noise=12.0) -> bytes:
    """A standing 'person': coloured body with texture, and - if ``face`` is a colour - a framed face block near the top."""
    rng = np.random.default_rng(seed)
    pixels = np.clip(np.array(body, dtype=float) + rng.normal(0, noise, (size[1], size[0], 3)), 0, 255).astype(np.uint8)
    if face is not None:
        x1, y1 = (size[0] - face_px) // 2, 12
        pixels[y1 : y1 + face_px, x1 : x1 + face_px] = (5, 5, 5)  # the dark frame the fake detector looks for
        pixels[y1 + 4 : y1 + face_px - 4, x1 + 4 : x1 + face_px - 4] = np.clip(
            np.array(face, dtype=float) + rng.normal(0, 4, (face_px - 8, face_px - 8, 3)), 0, 255).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    return buffer.getvalue()


def detection(x1, y1, x2, y2, score=0.95) -> Detection:
    return Detection(Box(x1, y1, x2, y2), score)


def crop_png(colour, *, size=(64, 128), seed=0, noise=12.0, fmt="PNG") -> bytes:
    """A 'person crop': a colour plus texture noise (so the sharpness check does not flag it as blurry)."""
    rng = np.random.default_rng(seed)
    pixels = np.clip(np.array(colour, dtype=float) + rng.normal(0, noise, (size[1], size[0], 3)), 0, 255).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format=fmt)
    return buffer.getvalue()


def scene_png(colour, *, size=(300, 400), box=(80, 40, 220, 360), seed=0) -> bytes:
    """A grey scene with one person-shaped coloured rectangle."""
    rng = np.random.default_rng(seed)
    pixels = np.clip(rng.normal(128, 10, (size[1], size[0], 3)), 0, 255).astype(np.uint8)
    x1, y1, x2, y2 = box
    pixels[y1:y2, x1:x2] = np.clip(np.array(colour) + rng.normal(0, 12, (y2 - y1, x2 - x1, 3)), 0, 255).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    return buffer.getvalue()
