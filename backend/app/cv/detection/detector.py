"""
Person detection.

In plain words: before we can compare people we have to find them. This module
wraps a small pretrained object detector (torchvision, trained on the public
COCO dataset - BSD licence) and keeps only the "person" boxes it finds.

Important distinction used everywhere in this project:

    detector score      = how sure the DETECTOR is that a box contains a person
    similarity score    = how alike two people's embeddings are
    calibrated confidence (optional) = estimated chance an accepted match is right

These three numbers answer different questions and are never mixed.

Like the embedding model, the detector loads its weights from a local file that
``scripts/download_weights.py`` placed there - nothing is downloaded at runtime.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torchvision.models import detection as tv_detection

from ...core.errors import ModelUnavailable
from ..geometry import Box

logger = logging.getLogger(__name__)

COCO_PERSON_LABEL = 1  # in torchvision's COCO category indexing


@dataclass(frozen=True)
class Detection:
    box: Box
    score: float  # detector confidence - NOT an identity-match score


@dataclass(frozen=True)
class DetectorSpec:
    name: str
    display_name: str
    builder_name: str  # function name inside torchvision.models.detection
    weights_enum_name: str  # enum holding the official COCO weights (for URL + licence)

    @property
    def weights_url(self) -> str:
        return getattr(tv_detection, self.weights_enum_name).COCO_V1.url

    @property
    def filename(self) -> str:
        return self.weights_url.rsplit("/", 1)[-1]

    @property
    def hash_prefix(self) -> str:
        """torchvision file names end with the first 8 hex chars of the file's SHA-256."""
        match = re.search(r"-([0-9a-f]{8})\.pth$", self.filename)
        return match.group(1) if match else ""


DETECTORS: dict[str, DetectorSpec] = {
    spec.name: spec
    for spec in (
        DetectorSpec(
            "fasterrcnn_mobilenet_v3_large_fpn",
            "Faster R-CNN MobileNetV3-Large FPN",
            "fasterrcnn_mobilenet_v3_large_fpn",
            "FasterRCNN_MobileNet_V3_Large_FPN_Weights",
        ),
        DetectorSpec(
            "fasterrcnn_mobilenet_v3_large_320_fpn",
            "Faster R-CNN MobileNetV3-Large 320 FPN (fastest R-CNN)",
            "fasterrcnn_mobilenet_v3_large_320_fpn",
            "FasterRCNN_MobileNet_V3_Large_320_FPN_Weights",
        ),
        DetectorSpec(
            "ssdlite320_mobilenet_v3_large",
            "SSDlite MobileNetV3-Large 320 (smallest download)",
            "ssdlite320_mobilenet_v3_large",
            "SSDLite320_MobileNet_V3_Large_Weights",
        ),
    )
}


class PersonDetector:
    def __init__(
        self,
        spec: DetectorSpec,
        model: torch.nn.Module,
        device: torch.device,
        *,
        score_threshold: float,
        max_people: int,
        load_seconds: float,
    ) -> None:
        self.spec = spec
        self.name = spec.name
        self.device = device
        self.score_threshold = score_threshold
        self.max_people = max_people
        self.load_seconds = load_seconds
        self._model = model
        self._lock = threading.Lock()

    @classmethod
    def load(
        cls,
        name: str,
        weights_dir: Path,
        device: torch.device,
        *,
        min_size: int,
        score_threshold: float,
        max_people: int,
    ) -> PersonDetector:
        spec = DETECTORS.get(name)
        if spec is None:
            raise ModelUnavailable(f"Unknown detector '{name}'. Available: {', '.join(sorted(DETECTORS))}.")

        path = weights_dir / spec.filename
        if not path.is_file():
            raise ModelUnavailable(
                f"Detector weights not found at {path}. Run:  python scripts/download_weights.py",
                details={"missing_file": str(path)},
            )

        started = time.perf_counter()
        builder = getattr(tv_detection, spec.builder_name)
        # weights=None: build the empty network; we load the verified local file ourselves.
        kwargs = {"weights": None, "weights_backbone": None, "box_score_thresh": score_threshold}
        if spec.builder_name.startswith("fasterrcnn"):
            kwargs["min_size"] = min_size
            kwargs["box_detections_per_img"] = 100
        model = builder(**kwargs)
        try:
            state = torch.load(path, map_location="cpu", weights_only=True)
            model.load_state_dict(state, strict=True)
        except Exception as exc:
            raise ModelUnavailable(
                f"Detector weights {path.name} could not be loaded ({exc}). "
                "Delete the file and re-run scripts/download_weights.py."
            ) from exc
        model.to(device).eval()
        logger.info("Detector %s ready on %s (%.2fs)", spec.name, device, time.perf_counter() - started)
        return cls(
            spec,
            model,
            device,
            score_threshold=score_threshold,
            max_people=max_people,
            load_seconds=time.perf_counter() - started,
        )

    def detect(self, pixels: np.ndarray) -> list[Detection]:
        """Return person boxes, most confident first. Empty list = nobody found."""
        tensor = torch.from_numpy(pixels).to(self.device).permute(2, 0, 1).float().div_(255.0)
        with self._lock, torch.inference_mode():
            output = self._model([tensor])[0]

        boxes = output["boxes"].cpu().numpy()
        scores = output["scores"].cpu().numpy()
        labels = output["labels"].cpu().numpy()

        found = []
        for box, score, label in zip(boxes, scores, labels, strict=True):
            if label != COCO_PERSON_LABEL or score < self.score_threshold:
                continue
            candidate = Box.from_list(box.tolist())
            if candidate.width < 8 or candidate.height < 16:  # not even a plausible person
                continue
            found.append(Detection(candidate, float(score)))

        found.sort(key=lambda d: d.score, reverse=True)
        return found[: self.max_people]

    def info(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.spec.display_name,
            "device": str(self.device),
            "score_threshold": self.score_threshold,
            "weights_source": "torchvision COCO_V1 (BSD-3-Clause; trained on COCO)",
            "load_seconds": round(self.load_seconds, 3),
        }
