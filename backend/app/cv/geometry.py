"""
Bounding boxes and cropping.

In plain words: a ``Box`` is a rectangle in pixel coordinates, (x1, y1) = top-left
corner and (x2, y2) = bottom-right corner. ``crop_person`` cuts that rectangle
out of an image, adds a small safety margin around it, and makes sure the crop
has a person-like proportion (about twice as tall as wide) so the network sees
the body without squashing it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Pad colour used when a crop has to be made taller/wider: a neutral mid-grey.
_PAD_COLOUR = (124, 116, 104)
PAD_COLOUR = _PAD_COLOUR  # public name: the face analysis uses it to trim these bars off again

# A standing person is roughly 2:1 (height:width). Crops within this band are
# resized directly; wildly different shapes are padded to avoid heavy distortion.
TARGET_ASPECT = 2.0
ASPECT_TOLERANCE = (1.4, 3.0)


@dataclass(frozen=True)
class Box:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    def is_valid(self) -> bool:
        return self.width > 1 and self.height > 1

    def clipped(self, image_width: int, image_height: int) -> Box:
        return Box(
            max(0.0, min(self.x1, image_width)),
            max(0.0, min(self.y1, image_height)),
            max(0.0, min(self.x2, image_width)),
            max(0.0, min(self.y2, image_height)),
        )

    def as_list(self) -> list[float]:
        return [round(self.x1, 1), round(self.y1, 1), round(self.x2, 1), round(self.y2, 1)]

    @classmethod
    def from_list(cls, values: list[float] | tuple[float, ...]) -> Box:
        x1, y1, x2, y2 = (float(v) for v in values)
        return cls(x1, y1, x2, y2)


def touches_border(box: Box, image_width: int, image_height: int, tolerance: float = 2.0) -> dict[str, bool]:
    """Which image edges does the box touch? (A person cut off by the frame is harder to match.)"""
    return {
        "left": box.x1 <= tolerance,
        "top": box.y1 <= tolerance,
        "right": box.x2 >= image_width - tolerance,
        "bottom": box.y2 >= image_height - tolerance,
    }


def crop_person(pixels: np.ndarray, box: Box, margin: float = 0.05) -> np.ndarray:
    """Cut a person out of an image, keeping a sensible aspect ratio.

    ``margin`` grows the box by that fraction on every side so we do not clip
    hands or feet when the detector box is tight.
    """
    region, _ = crop_region(pixels, box, margin)
    return pad_to_person_aspect(region)


def crop_region(pixels: np.ndarray, box: Box, margin: float = 0.05) -> tuple[np.ndarray, tuple[int, int]]:
    """The same cut as ``crop_person`` but WITHOUT the grey padding, plus where its top-left corner sits in the image.

    Face detection and colour measurements need real picture content only, and need to map what they find back to the
    uploaded image, so they use this instead of the padded crop the body network sees.
    """
    image_height, image_width = pixels.shape[:2]
    box = box.clipped(image_width, image_height)
    pad_x, pad_y = box.width * margin, box.height * margin
    grown = Box(box.x1 - pad_x, box.y1 - pad_y, box.x2 + pad_x, box.y2 + pad_y).clipped(
        image_width, image_height
    )

    x1, y1 = int(np.floor(grown.x1)), int(np.floor(grown.y1))
    x2, y2 = int(np.ceil(grown.x2)), int(np.ceil(grown.y2))
    return pixels[y1:y2, x1:x2], (x1, y1)


def pad_to_person_aspect(crop: np.ndarray) -> np.ndarray:
    """Pad (never stretch) crops whose proportions are far from a standing person."""
    height, width = crop.shape[:2]
    if height == 0 or width == 0:
        return crop
    aspect = height / width
    low, high = ASPECT_TOLERANCE
    if low <= aspect <= high:
        return crop

    if aspect < low:  # too wide  -> add rows
        new_height, new_width = int(round(width * TARGET_ASPECT)), width
    else:  # too tall -> add columns
        new_height, new_width = height, int(round(height / TARGET_ASPECT))

    canvas = np.empty((new_height, new_width, 3), dtype=np.uint8)
    canvas[:, :] = _PAD_COLOUR
    top = (new_height - height) // 2
    left = (new_width - width) // 2
    canvas[top : top + height, left : left + width] = crop
    return canvas
