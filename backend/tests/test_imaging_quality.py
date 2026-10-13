"""Upload validation, cropping geometry and crop-quality checks (all on generated images)."""

import io

import numpy as np
import pytest
from PIL import Image

from app.core.config import Settings
from app.core.errors import PayloadTooLarge, UnsupportedImage, ValidationFailed
from app.cv.geometry import Box, crop_person, pad_to_person_aspect
from app.cv.imaging import decode_image, encode_jpeg
from app.cv.quality import assess_crop

SETTINGS = Settings(max_upload_mb=1, max_image_side=2000, min_image_side=32)


def png_bytes(width=100, height=200, mode="RGB", fmt="PNG") -> bytes:
    buffer = io.BytesIO()
    colour = (120, 40, 40) if mode == "RGB" else 120  # greyscale images take a single value
    Image.new(mode, (width, height), colour).save(buffer, format=fmt)
    return buffer.getvalue()


def decode(data, name="x.png", mime="image/png"):
    return decode_image(data, filename=name, content_type=mime, settings=SETTINGS)


# ------------------------------------------------------------------ upload safety
def test_valid_image_decodes_to_rgb_pixels():
    image = decode(png_bytes(100, 200))
    assert image.pixels.shape == (200, 100, 3) and image.pixels.dtype == np.uint8
    assert image.width == 100 and image.height == 200
    assert len(image.sha256) == 64


def test_grayscale_and_palette_images_are_converted_to_rgb():
    assert decode(png_bytes(mode="L")).pixels.shape[2] == 3


def test_empty_file_is_rejected():
    with pytest.raises(ValidationFailed):
        decode(b"")


def test_non_image_bytes_are_rejected_even_with_image_extension():
    with pytest.raises(UnsupportedImage):
        decode(b"this is definitely not an image" * 10)


def test_wrong_extension_is_rejected():
    with pytest.raises(UnsupportedImage):
        decode(png_bytes(), name="payload.exe")


def test_script_disguised_as_image_is_rejected_by_content_sniffing():
    with pytest.raises(UnsupportedImage):
        decode(b"<?php system($_GET['c']); ?>", name="evil.png", mime="image/png")


def test_disallowed_mime_type_is_rejected():
    with pytest.raises(UnsupportedImage):
        decode(png_bytes(), mime="text/html")


def test_gif_is_not_an_accepted_format():
    with pytest.raises(UnsupportedImage):
        decode(png_bytes(fmt="GIF"), name="x.png")  # real content is GIF, name lies


def test_oversized_file_is_rejected():
    with pytest.raises(PayloadTooLarge):
        decode(b"\x89PNG" + b"0" * (SETTINGS.max_upload_bytes + 1))


def test_tiny_and_huge_dimensions_are_rejected():
    with pytest.raises(ValidationFailed):
        decode(png_bytes(10, 10))
    with pytest.raises(ValidationFailed):
        decode(png_bytes(2500, 100))


def test_path_traversal_in_filename_is_harmless():
    # Only the extension is inspected; the name is never used to touch the file system.
    image = decode(png_bytes(), name="../../etc/passwd.png")
    assert image.width == 100


def test_truncated_image_is_rejected():
    with pytest.raises(UnsupportedImage):
        decode(png_bytes(200, 400)[:200])


def test_jpeg_round_trip_keeps_shape():
    pixels = np.full((120, 60, 3), 90, dtype=np.uint8)
    decoded = decode(encode_jpeg(pixels), name="x.jpg", mime="image/jpeg")
    assert decoded.pixels.shape == (120, 60, 3)


# ---------------------------------------------------------------------- geometry
def test_box_clipping_and_validity():
    box = Box(-10, -5, 500, 700).clipped(400, 600)
    assert (box.x1, box.y1, box.x2, box.y2) == (0, 0, 400, 600)
    assert not Box(10, 10, 10.5, 40).is_valid()


def test_person_shaped_crop_is_not_padded():
    crop = np.zeros((200, 100, 3), dtype=np.uint8)
    assert pad_to_person_aspect(crop).shape == (200, 100, 3)


def test_wide_crop_is_padded_not_stretched():
    padded = pad_to_person_aspect(np.full((100, 300, 3), 255, dtype=np.uint8))
    assert padded.shape[0] / padded.shape[1] == pytest.approx(2.0, rel=0.02)
    assert padded[:, :, 0].min() < 255  # padding colour is present


def test_crop_person_stays_inside_the_image():
    pixels = np.zeros((300, 200, 3), dtype=np.uint8)
    crop = crop_person(pixels, Box(150, 50, 260, 290))  # box sticks out of the image
    assert crop.shape[0] > 0 and crop.shape[1] > 0


# ------------------------------------------------------------------------ quality
def noisy(height, width, seed=0):
    return np.random.default_rng(seed).integers(0, 255, (height, width, 3), dtype=np.uint8)


def test_sharp_person_sized_crop_has_no_flags():
    report = assess_crop(noisy(200, 90))
    assert report.usable and report.flags == []


def test_tiny_crop_is_blocking():
    report = assess_crop(noisy(20, 10))
    assert not report.usable and "too small" in report.blocking_reason


def test_flat_image_is_flagged_blurry():
    flat = np.full((200, 90, 3), 128, dtype=np.uint8)
    assert "blurry" in assess_crop(flat).flags


def test_person_touching_frame_edge_is_flagged():
    box = Box(0, 10, 90, 210)
    report = assess_crop(noisy(200, 90), source_box=box, image_size=(400, 300))
    assert "cut_off_by_frame" in report.flags


def test_low_detector_score_is_flagged():
    assert "uncertain_detection" in assess_crop(noisy(200, 90), detector_score=0.4).flags


def test_benchmark_sized_crops_are_not_flagged_low_resolution():
    # Market-1501 style 128x64 crops must not be flagged just for being small benchmark images.
    assert "low_resolution" not in assess_crop(noisy(128, 64)).flags
