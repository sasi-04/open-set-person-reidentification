"""
Rebuild the demo's sample pictures from the two prepared street scenes (public-domain photos, heads blurred).

In plain words: the demo needs a few pictures whose "right answer" is known in advance - the same person seen
again, a stranger, and a poor-quality picture. This script derives them from two CC0 photos
(see samples/SOURCES.md) with fixed, simple recipes, using the SERVER'S OWN person detector to find the boxes.

The recipes were fixed before looking at any result and are not tuned to make the demo look good:

    person_A_reference_1   tight crop of the most confident person in scene A
    person_A_reference_2   the same crop, mirrored (a second reference photo)
    query_1_same_person    the same person "seen again": a looser crop, 55% of the size, 20% darker
    query_2_stranger       a tight crop of the most confident person in scene B (a different person, in a different place)
    query_3_blurry         the same person in a loose box, half size, heavily out of focus (Gaussian blur radius 6).
                           This recipe is DELIBERATELY strong enough to trip the system's own sharpness check
                           (backend/app/cv/quality.py: Laplacian variance < 12). It exercises the REVIEW path;
                           it says nothing about how often real footage is that blurry.
    clip_street.avi        a 3 s clip with a slow zoom: scene A, scene B, scene A
    clip_faces.avi         a 3 s clip of the FACE demonstration photos: Collins, Ride (a stranger), Collins

HONEST LIMIT: "same person seen again" is derived from the SAME source photo, because no public multi-camera
photo of one person is bundled. It shows how the system behaves; it is not a test of cross-camera accuracy.
For that, use a real benchmark (README section 9).

Run (the server must be running):   python demo/make_samples.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import Api  # noqa: E402

SAMPLES = Path(__file__).resolve().parent / "samples"


def best_person(api: Api, scene: Path) -> list[float]:
    answer = api.post_form("/api/reid/detect", {}, [("image", scene)])
    usable = [d for d in answer["detections"] if d["quality"]["usable"]]
    if not usable:
        raise SystemExit(f"The detector found nobody usable in {scene.name}.")
    best = max(usable, key=lambda d: d["detector_score"])
    print(f"  {scene.name}: {len(answer['detections'])} people found; using box {best['box']} (detector confidence {best['detector_score']:.3f})")
    return best["box"]


def crop(image: Image.Image, box: list[float], grow: float = 0.0, grow_x: float | None = None) -> Image.Image:
    """Cut a box out of the photo, optionally with extra margin (``grow_x`` for the sides only, default = ``grow``)."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    gx = grow if grow_x is None else grow_x
    x1, y1, x2, y2 = x1 - gx * w, y1 - grow * h, x2 + gx * w, y2 + grow * h
    return image.crop((max(0, int(x1)), max(0, int(y1)), min(image.width, int(x2)), min(image.height, int(y2))))


def zoom_frame(image: Image.Image, size: tuple[int, int], zoom: float) -> np.ndarray:
    """Fit ``image`` inside ``size`` on black, then zoom in slightly around the centre (a slow camera push-in)."""
    canvas = Image.new("RGB", size, (0, 0, 0))
    fitted = image.copy()
    fitted.thumbnail(size)
    canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    frame = np.asarray(canvas)
    matrix = cv2.getRotationMatrix2D((size[0] / 2, size[1] / 2), 0, zoom)
    return cv2.cvtColor(cv2.warpAffine(frame, matrix, size, flags=cv2.INTER_LINEAR), cv2.COLOR_RGB2BGR)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    api = Api(args.base_url)

    scene_a, scene_b = SAMPLES / "scene_A_street_amsterdam.jpg", SAMPLES / "scene_B_station_square.jpg"
    for scene in (scene_a, scene_b):
        if not scene.is_file():
            raise SystemExit(f"Missing {scene}. Run  python demo/prepare_scenes.py  (see samples/SOURCES.md).")
    print("Finding people with the server's detector:")
    box_a, box_b = best_person(api, scene_a), best_person(api, scene_b)

    image_a = ImageOps.exif_transpose(Image.open(scene_a)).convert("RGB")
    image_b = ImageOps.exif_transpose(Image.open(scene_b)).convert("RGB")
    person = crop(image_a, box_a)

    person.save(SAMPLES / "person_A_reference_1.jpg", quality=92)
    ImageOps.mirror(person).save(SAMPLES / "person_A_reference_2.jpg", quality=92)

    again = crop(image_a, box_a, grow=0.12)
    again = again.resize((int(again.width * 0.55), int(again.height * 0.55)), Image.LANCZOS)
    ImageEnhance.Brightness(again).enhance(0.8).save(SAMPLES / "query_1_same_person.jpg", quality=90)

    crop(image_b, box_b).save(SAMPLES / "query_2_stranger.jpg", quality=92)

    # A loose, detector-style box (30 % extra at each side, so the server does not need to pad it with grey -
    # padding edges would add artificial sharpness), half size, out of focus.
    loose = crop(image_a, box_a, grow_x=0.3)
    half = loose.resize((loose.width // 2, loose.height // 2), Image.LANCZOS).filter(ImageFilter.GaussianBlur(6))
    half.save(SAMPLES / "query_3_blurry.jpg", quality=90)

    size = (480, 640)
    # Middle second: the stranger's part of the station square at full size (a whole 7-person scene squeezed into a
    # 480x640 frame would make everyone tiny and just demonstrate the 'too small' path, which Match Studio already shows).
    middle = crop(image_b, box_b, grow=0.15, grow_x=1.1)
    writer = cv2.VideoWriter(str(SAMPLES / "clip_street.avi"), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, size)
    for k in range(30):
        scene = middle if 10 <= k < 20 else image_a
        writer.write(zoom_frame(scene, size, 1.0 + 0.002 * k))
    writer.release()

    # A second clip for the FACE demonstration: the enrolled person, a stranger, the enrolled person again (public-domain NASA
    # photographs, see samples/faces/SOURCES.md). Built only if those photos have been fetched (prepare_faces.py).
    faces = SAMPLES / "faces" / "test"
    parts = [faces / "collins" / "collins_test_1_nasa_jacket_1999.jpg", faces / "ride" / "ride_stranger_2_blue_shirt_1983.jpg",
             faces / "collins" / "collins_test_3_hard_hat_2004.jpg"]
    if all(p.is_file() for p in parts):
        pictures = [ImageOps.exif_transpose(Image.open(p)).convert("RGB") for p in parts]
        writer = cv2.VideoWriter(str(SAMPLES / "clip_faces.avi"), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, size)
        for k in range(30):
            writer.write(zoom_frame(pictures[k // 10], size, 1.0 + 0.002 * (k % 10)))
        writer.release()

    for path in sorted(SAMPLES.glob("*")):
        if path.suffix.lower() in {".jpg", ".avi"}:
            print(f"  wrote {path.name:30s} {path.stat().st_size / 1024:8.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
