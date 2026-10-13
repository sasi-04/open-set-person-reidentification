"""
Appearance cues: hair, skin tone and clothing colours, compared side by side.

In plain words: besides the two neural fingerprints (face and whole body) a human reviewer likes to SEE the simple
things - "same hair colour? same skin tone? same shirt?". This module measures those from the pictures with plain
image statistics (no neural network) and lines up the query and the closest enrolled reference.

These cues are SUPPORTING EVIDENCE FOR A HUMAN. They never change a MATCH / UNKNOWN / REVIEW decision, because they
are not calibrated: lighting, camera white balance, shadows and make-up move colours a lot, and clothes change from
day to day. The decision uses the face and body fingerprints; this is the explanation next to it.

Colours are compared as CIE L*a*b* distance (Delta E 1976): about 2 is the smallest visible difference, 10-20 is
clearly a different shade, 40+ is a different colour.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

CUE_ORDER = ("hair", "skin_tone", "upper_clothing", "lower_clothing")
CUE_TITLE = {"hair": "Hair colour", "skin_tone": "Skin tone", "upper_clothing": "Upper clothing", "lower_clothing": "Lower clothing"}
SAME_DELTA_E = {"hair": 25.0, "skin_tone": 16.0, "upper_clothing": 25.0, "lower_clothing": 25.0}  # heuristic cut-offs, uncalibrated

_CLOTHES = {
    "black": (20, 20, 20), "dark grey": (80, 80, 80), "grey": (140, 140, 140), "light grey": (200, 200, 200), "white": (240, 240, 240),
    "red": (200, 30, 30), "dark red": (120, 20, 30), "orange": (235, 130, 30), "yellow": (235, 215, 50), "khaki": (150, 140, 70),
    "green": (40, 150, 60), "dark green": (25, 80, 40), "teal": (30, 140, 140), "light blue": (130, 180, 230), "blue": (40, 80, 200),
    "navy": (25, 35, 90), "purple": (110, 50, 150), "pink": (235, 140, 175), "brown": (110, 70, 40), "beige": (215, 195, 160), "tan": (190, 150, 100),
}
_HAIR = {
    "black": (25, 22, 22), "dark brown": (60, 40, 30), "brown": (100, 70, 45), "light brown": (140, 105, 70), "blond": (205, 175, 110),
    "red / auburn": (140, 60, 35), "grey": (140, 140, 140), "white": (225, 225, 225),
}


def _lab(rgb: np.ndarray) -> np.ndarray:
    """(N,3) uint8 RGB -> (N,3) float L*a*b* (L 0..100)."""
    pixels = rgb.reshape(-1, 1, 3).astype(np.float32) / 255.0
    return cv2.cvtColor(pixels, cv2.COLOR_RGB2LAB).reshape(-1, 3)


def _name(rgb: tuple[int, int, int], palette: dict[str, tuple[int, int, int]]) -> str:
    target = _lab(np.array([rgb], dtype=np.uint8))[0]
    return min(palette, key=lambda n: float(np.linalg.norm(_lab(np.array([palette[n]], dtype=np.uint8))[0] - target)))


def _skin_name(lab: np.ndarray) -> str:
    """Individual Typology Angle (a standard dermatology scale) -> a plain word. Only a rough guide under unknown lighting."""
    ita = math.degrees(math.atan2(lab[0] - 50.0, max(lab[2], 1e-3)))
    for limit, word in ((55, "very light"), (41, "light"), (28, "intermediate"), (10, "tan"), (-30, "brown")):
        if ita > limit:
            return word
    return "dark"


def _skin_mask(rgb: np.ndarray) -> np.ndarray:
    """Pixels whose colour lies in the classic skin range of YCrCb space."""
    ycrcb = cv2.cvtColor(rgb.reshape(-1, 1, 3), cv2.COLOR_RGB2YCrCb).reshape(-1, 3)
    return (ycrcb[:, 1] >= 133) & (ycrcb[:, 1] <= 173) & (ycrcb[:, 2] >= 77) & (ycrcb[:, 2] <= 127)


@dataclass(frozen=True)
class Cue:
    name: str
    rgb: tuple[int, int, int]
    label: str


def _region(rgb: np.ndarray, x1: float, y1: float, x2: float, y2: float) -> np.ndarray | None:
    h, w = rgb.shape[:2]
    ix1, iy1, ix2, iy2 = max(0, int(x1)), max(0, int(y1)), min(w, int(x2)), min(h, int(y2))
    if ix2 - ix1 < 3 or iy2 - iy1 < 3:
        return None
    return rgb[iy1:iy2, ix1:ix2]


def _dominant(pixels: np.ndarray) -> tuple[int, int, int] | None:
    """The colour of the larger of two colour clusters (stripes and patterns have no single colour)."""
    if len(pixels) < 12:
        return None
    lab = _lab(pixels)
    if len(lab) > 4000:
        lab = lab[:: len(lab) // 4000]
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 12, 1.0)
    _, labels, centres = cv2.kmeans(lab.astype(np.float32), 2, None, criteria, 2, cv2.KMEANS_PP_CENTERS)
    best = centres[int(np.argmax(np.bincount(labels.reshape(-1), minlength=2)))]
    rgb = cv2.cvtColor(best.reshape(1, 1, 3).astype(np.float32), cv2.COLOR_LAB2RGB).reshape(3)
    return tuple(int(v) for v in np.clip(rgb * 255.0, 0, 255))  # type: ignore[return-value]


def extract_cues(rgb: np.ndarray, face_box: tuple[float, float, float, float] | None) -> dict[str, Cue]:
    """Measure the cues that can be seen. ``rgb`` is one person's picture; ``face_box`` is the face in THAT picture's pixels."""
    cues: dict[str, Cue] = {}
    height, width = rgb.shape[:2]

    if face_box is not None:
        fx1, fy1, fx2, fy2 = face_box
        fw, fh = fx2 - fx1, fy2 - fy1
        patch = _region(rgb, fx1 + 0.28 * fw, fy1 + 0.45 * fh, fx1 + 0.72 * fw, fy1 + 0.80 * fh)
        if patch is not None:
            pixels = patch.reshape(-1, 3)
            skin = _skin_mask(pixels)
            if skin.mean() >= 0.30:
                colour = tuple(int(v) for v in np.median(pixels[skin], axis=0))
                lab = _lab(np.array([colour], dtype=np.uint8))[0]
                cues["skin_tone"] = Cue("skin_tone", colour, _skin_name(lab))  # type: ignore[arg-type]
        top = _region(rgb, fx1 + 0.15 * fw, fy1 - 0.30 * fh, fx1 + 0.85 * fw, fy1 + 0.08 * fh)
        if top is not None:
            pixels = top.reshape(-1, 3)
            keep = ~_skin_mask(pixels) & (pixels.astype(int).sum(axis=1) < 3 * 235)  # not skin, not blown-out sky/wall
            if keep.mean() >= 0.25 and keep.sum() >= 12:
                colour = tuple(int(v) for v in np.median(pixels[keep], axis=0))
                cues["hair"] = Cue("hair", colour, _name(colour, _HAIR))  # type: ignore[arg-type]

    if height / max(width, 1) >= 1.4:  # a whole-body crop: torso and legs are where we expect them
        for cue_name, (y1, y2) in (("upper_clothing", (0.26, 0.46)), ("lower_clothing", (0.56, 0.84))):
            patch = _region(rgb, 0.22 * width, y1 * height, 0.78 * width, y2 * height)
            colour = None if patch is None else _dominant(patch.reshape(-1, 3))
            if colour is not None:
                cues[cue_name] = Cue(cue_name, colour, _name(colour, _CLOTHES))
    return cues


def compare_cues(query: dict[str, Cue], reference: dict[str, Cue]) -> list[dict]:
    """One row per cue that BOTH pictures show: the two colours, their distance and a plain verdict."""
    rows = []
    for name in CUE_ORDER:
        if name not in query or name not in reference:
            continue
        a, b = query[name], reference[name]
        delta = float(np.linalg.norm(_lab(np.array([a.rgb], dtype=np.uint8))[0] - _lab(np.array([b.rgb], dtype=np.uint8))[0]))
        rows.append({
            "cue": name, "title": CUE_TITLE[name], "query_rgb": list(a.rgb), "query_label": a.label,
            "reference_rgb": list(b.rgb), "reference_label": b.label, "delta_e": round(delta, 1),
            # Two colours that get the same plain name ("black" and "black") are called similar even when the exact shades
            # differ a little - otherwise the table would say "Black vs Black: different".
            "verdict": "similar" if (delta < SAME_DELTA_E[name] or a.label == b.label) else "different",
        })
    return rows
