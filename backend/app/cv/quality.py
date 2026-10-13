"""
Crop quality checks.

In plain words: a blurry, tiny or half-cut-off picture of a person gives an
unreliable fingerprint. Before we trust a match we look at the crop and record
simple, explainable facts about it. There are two severities:

  * BLOCKING problem  -> the crop is unusable (e.g. a few pixels tall). We do
    not even compute an embedding; the result is a PROCESSING_ERROR.
  * SOFT flag         -> we still compute the embedding and show the candidates,
    but the decision policy sends the result to human REVIEW instead of
    auto-accepting or auto-rejecting it.

The thresholds are plain heuristics (documented below), not learned values.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .geometry import Box, touches_border

# Blocking: below this the crop carries too little information to embed at all.
MIN_BLOCKING_HEIGHT = 32
MIN_BLOCKING_WIDTH = 16

# Soft flags (heuristics - tuned to be silent on 128x64 benchmark crops).
LOW_RESOLUTION_HEIGHT = 80  # crops shorter than this are "low resolution"
ASPECT_RANGE = (1.2, 4.0)  # height/width outside this is an unusual body shape / bad box
BLUR_LAPLACIAN_VARIANCE = 12.0  # variance of the Laplacian below this = blurry
LOW_DETECTOR_SCORE = 0.60


@dataclass
class QualityReport:
    usable: bool
    flags: list[str] = field(default_factory=list)
    blocking_reason: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "usable": self.usable,
            "flags": self.flags,
            "blocking_reason": self.blocking_reason,
            "metrics": {k: round(float(v), 2) for k, v in self.metrics.items()},
        }


def sharpness(crop: np.ndarray) -> float:
    """Variance of the Laplacian on a fixed-size grey copy: higher = sharper."""
    grey = cv2.cvtColor(cv2.resize(crop, (64, 128), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(grey, cv2.CV_64F).var())


def assess_crop(
    crop: np.ndarray,
    *,
    source_box: Box | None = None,
    image_size: tuple[int, int] | None = None,
    detector_score: float | None = None,
) -> QualityReport:
    """``source_box`` / ``image_size`` enable the "cut off by the frame" check (detections only)."""
    height, width = (source_box.height, source_box.width) if source_box else crop.shape[:2]
    metrics = {"height_px": height, "width_px": width, "sharpness": sharpness(crop)}

    if height < MIN_BLOCKING_HEIGHT or width < MIN_BLOCKING_WIDTH:
        return QualityReport(
            usable=False,
            blocking_reason=f"The person is too small to match reliably ({width:.0f}x{height:.0f}px; "
            f"need at least {MIN_BLOCKING_WIDTH}x{MIN_BLOCKING_HEIGHT}px).",
            metrics=metrics,
        )

    flags: list[str] = []
    if height < LOW_RESOLUTION_HEIGHT:
        flags.append("low_resolution")
    aspect = height / width
    metrics["aspect_ratio"] = aspect
    if not ASPECT_RANGE[0] <= aspect <= ASPECT_RANGE[1]:
        flags.append("unusual_aspect_ratio")
    if metrics["sharpness"] < BLUR_LAPLACIAN_VARIANCE:
        flags.append("blurry")
    if source_box is not None and image_size is not None:
        edges = [edge for edge, hit in touches_border(source_box, *image_size).items() if hit]
        if edges:
            flags.append("cut_off_by_frame")
            metrics["touching_edges"] = float(len(edges))
    if detector_score is not None:
        metrics["detector_score"] = detector_score
        if detector_score < LOW_DETECTOR_SCORE:
            flags.append("uncertain_detection")

    return QualityReport(usable=True, flags=flags, metrics=metrics)


FLAG_DESCRIPTIONS = {
    "low_resolution": "The person is small in the image, so fine detail is missing.",
    "unusual_aspect_ratio": "The box has an unusual shape for a standing person.",
    "blurry": "The crop looks blurry.",
    "cut_off_by_frame": "The person touches the edge of the image and may be partly out of frame.",
    "uncertain_detection": "The detector was not very sure this is a whole person.",
}
