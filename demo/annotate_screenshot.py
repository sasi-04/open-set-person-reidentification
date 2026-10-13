"""
Draw numbered callouts on the Match Studio screenshot, for the printed guide.

In plain words: a screenshot of a busy screen is hard to read for someone who has never seen it. This copies the real MATCH screenshot
and puts a numbered circle on each part the guide explains. Only circles and numbers are added; nothing in the picture is changed.

    python demo/annotate_screenshot.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SHOTS = Path(__file__).resolve().parent / "screenshots"
SOURCE = SHOTS / "03_match_studio_MATCH.png"
TARGET = SHOTS / "annotated_match_studio.png"

# (number, x, y) in the coordinates of the 1440-pixel-wide screenshot
CALLOUTS = [
    (1, 1011, 277),   # the MATCH badge and the plain-language reason
    (2, 1011, 571),   # face similarity bar with the threshold tick
    (3, 1011, 653),   # the face threshold tile
    (4, 1011, 1108),  # "Decided by the face"
    (5, 1011, 1262),  # face bar and body bar
    (6, 1011, 1500),  # the two faces side by side
    (7, 1011, 1760),  # colour cues
    (8, 1011, 1960),  # ranked candidates with face and body scores
    (9, 717, 420),    # the face box on the query picture
]


def main() -> int:
    image = Image.open(SOURCE).convert("RGB")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arialbd.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    for number, x, y in CALLOUTS:
        draw.ellipse((x - 17, y - 17, x + 17, y + 17), fill=(229, 57, 53), outline=(255, 255, 255), width=3)
        text = str(number)
        box = draw.textbbox((0, 0), text, font=font)
        draw.text((x - (box[2] - box[0]) / 2 - box[0], y - (box[3] - box[1]) / 2 - box[1]), text, fill=(255, 255, 255), font=font)
    image.crop((255, 0, image.width, min(image.height, 2120))).save(TARGET, optimize=True)
    print("wrote", TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

