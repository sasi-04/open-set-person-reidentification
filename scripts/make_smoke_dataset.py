"""
Generate a small SYNTHETIC person dataset for checking that the pipeline runs.

In plain words: this draws cartoon "mannequins" - a head, a shirt, trousers -
with a few random variations (pose, lighting, camera colour cast, blur, noise)
so that we have labelled images of "different people seen by different
cameras" without using anyone's real photos. Groups of four mannequins
deliberately wear almost the SAME clothing colours, to mimic the
low-inter-class-variance situation (same uniform, similar build).

WHAT THIS IS NOT: a benchmark. A network trained on real photographs will find
these cartoons strange, and the numbers on them mean nothing about real-world
accuracy. The dataset is stamped ``"kind": "smoke_test"`` in ``dataset.json`` so
the application labels every result computed on it accordingly.

Usage:
    python scripts/make_smoke_dataset.py                    # datasets/smoke_synthetic
    python scripts/make_smoke_dataset.py --identities 120 --images 8 --seed 1
"""

from __future__ import annotations

import argparse
import colorsys
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

REPO_ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 64, 128  # same shape as Market-1501 crops
N_CAMERAS = 4


def hsv(h: float, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, min(max(s, 0), 1), min(max(v, 0), 1))
    return int(r * 255), int(g * 255), int(b * 255)


def make_identities(count: int, rng: np.random.Generator, group_size: int = 4) -> list[dict]:
    """People come in look-alike groups: same base clothing colours, tiny per-person differences."""
    people = []
    for index in range(count):
        if index % group_size == 0:  # start a new look-alike group
            base = {
                "shirt": (rng.random(), rng.uniform(0.3, 0.9), rng.uniform(0.25, 0.85)),
                "pants": (rng.random(), rng.uniform(0.1, 0.8), rng.uniform(0.15, 0.6)),
            }
        people.append({
            "id": f"P{index + 1:04d}",
            "shirt": tuple(c + rng.normal(0, 0.012) for c in base["shirt"]),
            "pants": tuple(c + rng.normal(0, 0.012) for c in base["pants"]),
            "skin": hsv(0.07, rng.uniform(0.2, 0.55), rng.uniform(0.6, 0.95)),
            "hair": hsv(rng.uniform(0.05, 0.12), rng.uniform(0.3, 0.8), rng.uniform(0.05, 0.4)),
            "build": rng.uniform(0.92, 1.08),
            "stripe": bool(rng.random() < 0.3),
        })
    return people


def camera_effect(image: Image.Image, camera: int, rng: np.random.Generator) -> Image.Image:
    """Each camera has its own colour cast, brightness, blur and noise."""
    tint = [(1.0, 1.0, 1.0), (1.08, 1.0, 0.92), (0.92, 1.0, 1.08), (1.0, 1.06, 0.94)][camera % N_CAMERAS]
    gain = [1.0, 0.85, 1.1, 0.95][camera % N_CAMERAS]
    array = np.asarray(image, dtype=np.float32) * np.array(tint) * gain
    array += rng.normal(0, [2.0, 5.0, 3.0, 4.0][camera % N_CAMERAS], array.shape)
    blurred = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))
    return blurred.filter(ImageFilter.GaussianBlur([0.3, 0.9, 0.5, 0.7][camera % N_CAMERAS]))


def render(person: dict, camera: int, rng: np.random.Generator) -> Image.Image:
    background = hsv(rng.uniform(0, 1), rng.uniform(0.0, 0.25), rng.uniform(0.45, 0.8))
    image = Image.new("RGB", (WIDTH, HEIGHT), background)
    draw = ImageDraw.Draw(image)

    shift = int(rng.integers(-4, 5))  # where the person stands
    lighting = rng.uniform(0.85, 1.15)
    shirt = hsv(*(person["shirt"][0:2]), person["shirt"][2] * lighting)
    pants = hsv(*(person["pants"][0:2]), person["pants"][2] * lighting)
    half = int(13 * person["build"])
    cx = WIDTH // 2 + shift

    draw.ellipse([cx - 8, 10, cx + 8, 30], fill=person["skin"])  # head
    draw.pieslice([cx - 9, 8, cx + 9, 28], 180, 360, fill=person["hair"])  # hair
    draw.rectangle([cx - half, 32, cx + half, 70], fill=shirt)  # torso
    if person["stripe"]:
        for y in range(36, 70, 8):
            draw.rectangle([cx - half, y, cx + half, y + 2], fill=hsv(0, 0, 0.9))
    swing = int(rng.integers(-3, 4))  # arms
    draw.rectangle([cx - half - 6 + swing, 33, cx - half, 66], fill=shirt)
    draw.rectangle([cx + half, 33, cx + half + 6 - swing, 66], fill=shirt)
    gap = int(rng.integers(0, 4))  # legs (walking pose)
    draw.rectangle([cx - half, 70, cx - 1 - gap, 114], fill=pants)
    draw.rectangle([cx + 1 + gap, 70, cx + half, 114], fill=pants)
    draw.rectangle([cx - half, 114, cx - 1 - gap, 120], fill=(25, 25, 25))  # shoes
    draw.rectangle([cx + 1 + gap, 114, cx + half, 120], fill=(25, 25, 25))

    if rng.random() < 0.5:
        image = image.transpose(Image.FLIP_LEFT_RIGHT)  # walking direction
    return camera_effect(image, camera, rng)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "datasets" / "smoke_synthetic")
    parser.add_argument("--identities", type=int, default=100)
    parser.add_argument("--images", type=int, default=8, help="images per identity")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    for person in make_identities(args.identities, rng):
        folder = args.out / person["id"]
        folder.mkdir(parents=True, exist_ok=True)
        for index in range(args.images):
            camera = (index % N_CAMERAS) + 1
            render(person, camera, rng).save(folder / f"c{camera}_{index:03d}.jpg", quality=92)

    (args.out / "dataset.json").write_text(json.dumps({
        "name": args.out.name,
        "kind": "smoke_test",
        "description": "Synthetic cartoon mannequins for verifying the pipeline. NOT a benchmark: results on it "
                       "say nothing about real-world accuracy.",
        "license": "Generated by scripts/make_smoke_dataset.py (no third-party data).",
    }, indent=2), encoding="utf-8")
    print(f"Wrote {args.identities} identities x {args.images} images to {args.out}")


if __name__ == "__main__":
    main()
