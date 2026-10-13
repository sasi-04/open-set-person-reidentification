"""
Safe image decoding and encoding.

In plain words: this is the front door for every picture that enters the
system - uploads from the browser, reference images, dataset files. The rules:

  * never trust the file name or the MIME type the client sends - check the
    real bytes with Pillow;
  * refuse oversized files and absurd dimensions *before* decoding everything
    (protects against "decompression bomb" images);
  * apply the camera's EXIF rotation, then convert to plain RGB pixels;
  * when we need to store an image, we re-encode it ourselves as JPEG, so the
    original bytes (and any hidden metadata) are never written to disk.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from ..core.config import Settings
from ..core.errors import PayloadTooLarge, UnsupportedImage, ValidationFailed

# Pillow refuses to open images with more pixels than this (decompression-bomb guard).
Image.MAX_IMAGE_PIXELS = 60_000_000

_ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP"}
_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
# Some clients send a generic type for uploads; the byte-level check below still applies.
_GENERIC_MIME = {"application/octet-stream", "binary/octet-stream", ""}


@dataclass(frozen=True)
class DecodedImage:
    pixels: np.ndarray  # (height, width, 3) uint8, RGB order
    sha256: str  # fingerprint of the ORIGINAL bytes - used to detect duplicate uploads
    source_format: str  # JPEG / PNG / WEBP / BMP

    @property
    def height(self) -> int:
        return int(self.pixels.shape[0])

    @property
    def width(self) -> int:
        return int(self.pixels.shape[1])


def decode_image(
    data: bytes,
    *,
    filename: str | None,
    content_type: str | None,
    settings: Settings,
) -> DecodedImage:
    """Validate and decode an uploaded image. Raises an AppError with a helpful message."""
    if not data:
        raise ValidationFailed("The uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise PayloadTooLarge(
            f"The file is {len(data) / 2**20:.1f} MB; the limit is {settings.max_upload_mb} MB."
        )

    if filename:
        suffix = Path(filename).suffix.lower()
        if suffix not in settings.allowed_extensions:
            raise UnsupportedImage(
                f"Unsupported file extension '{suffix}'. "
                f"Allowed: {', '.join(settings.allowed_extensions)}."
            )

    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in _ALLOWED_MIME and mime not in _GENERIC_MIME:
        raise UnsupportedImage(f"Unsupported content type '{mime}'. Upload a JPEG, PNG, WebP or BMP image.")

    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in _ALLOWED_FORMATS:
                raise UnsupportedImage(
                    f"The file content is '{image.format}', which is not a supported image format."
                )
            width, height = image.size  # read from the header, before decoding pixels
            _check_dimensions(width, height, settings)
            image.load()  # decode fully now so truncated/corrupt files fail here
            image = ImageOps.exif_transpose(image)  # honour camera rotation
            rgb = image.convert("RGB")
            source_format = str(image.format or "")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as exc:
        raise UnsupportedImage("The file is not a readable image (it may be corrupted).") from exc

    return DecodedImage(
        pixels=np.asarray(rgb, dtype=np.uint8),
        sha256=hashlib.sha256(data).hexdigest(),
        source_format=source_format,
    )


def _check_dimensions(width: int, height: int, settings: Settings) -> None:
    if min(width, height) < settings.min_image_side:
        raise ValidationFailed(
            f"The image is too small ({width}x{height}px). "
            f"Both sides must be at least {settings.min_image_side}px."
        )
    if max(width, height) > settings.max_image_side:
        raise ValidationFailed(
            f"The image is too large ({width}x{height}px). "
            f"The longest side may be at most {settings.max_image_side}px."
        )


def encode_jpeg(pixels: np.ndarray, quality: int = 90) -> bytes:
    """Encode RGB pixels as JPEG bytes (used for everything we store or serve)."""
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def load_rgb_file(path: Path) -> np.ndarray:
    """Read an image from disk (datasets, stored references) as RGB pixels."""
    with Image.open(path) as image:
        return np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
