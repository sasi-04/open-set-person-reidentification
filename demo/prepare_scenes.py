"""
Fetch the two public-domain street photos used by the demo and blur people's heads.

In plain words: the demo needs real photos with real pedestrians. Both are CC0 (public domain) on Wikimedia Commons,
but a licence for the picture is not a licence to circulate recognisable strangers, so before they go into a pack
that is shared around a company, this script blurs the HEAD region of every detected person. The system never uses
faces - it matches on the whole body (clothing, build, posture) - so blurring costs the demonstration nothing.

What it does:
  1. asks the Commons API for each photo's 960-px version, author and licence (and refuses anything that is not CC0);
  2. finds the people with the SERVER'S person detector (the server must be running);
  3. blurs the top ~17 % of each person's box, centred, and saves the scenes into demo/samples/.

It is a one-time step: the blurred scenes are already in the repository. Re-run it only to rebuild them.
    python demo/prepare_scenes.py
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import Api  # noqa: E402

SAMPLES = Path(__file__).resolve().parent / "samples"
USER_AGENT = "OpenIDVisionDemo/1.0 (demo sample preparation; contact: project owner)"
SCENES = {
    "scene_A_street_amsterdam.jpg":
        "File:2010.04 - 'Photo of people and Spring in the city', walking along the street Prins Hendrikkade, near Central Station "
        "Amsterdam city; Dutch urban photography by Fons Heijnsbroek, Netherlands, geotagged (27456703400).jpg",
    "scene_B_station_square.jpg":
        "File:Man is walking with other people over the station square of Central Station Amsterdam city; "
        "free photo, Fons Heijnsbroek, 11-04-2022.tif",
}


def commons_info(title: str) -> dict:
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo&iiprop=extmetadata|url&iiurlwidth=960&titles="
           + urllib.parse.quote(title))
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=60) as response:
        page = next(iter(json.load(response)["query"]["pages"].values()))
    info = page["imageinfo"][0]
    meta = info["extmetadata"]
    return {
        "licence": meta["LicenseShortName"]["value"], "author": re.sub("<[^>]+>", "", meta["Artist"]["value"]),
        "page": info["descriptionurl"], "thumb": info["thumburl"],
    }


def download(url: str) -> Image.Image:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=120) as response:
        return ImageOps.exif_transpose(Image.open(io.BytesIO(response.read()))).convert("RGB")


def blur_heads(image: Image.Image, boxes: list[list[float]]) -> int:
    done = 0
    for x1, y1, x2, y2 in boxes:
        w, h = x2 - x1, y2 - y1
        if h < 40:
            continue
        head = (int(x1 + 0.18 * w), max(0, int(y1 - 0.01 * h)), int(x2 - 0.18 * w), int(y1 + 0.17 * h))
        region = image.crop(head).filter(ImageFilter.GaussianBlur(max(5, (head[3] - head[1]) * 0.38)))
        image.paste(region, head[:2])
        done += 1
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    api = Api(args.base_url)
    SAMPLES.mkdir(exist_ok=True)

    for filename, title in SCENES.items():
        info = commons_info(title)
        if info["licence"] != "CC0":
            raise SystemExit(f"Refusing {filename}: its licence is {info['licence']!r}, not CC0.")
        print(f"{filename}: {info['licence']} by {info['author']}\n  {info['page']}")
        image = download(info["thumb"])
        raw = io.BytesIO()
        image.save(raw, "JPEG", quality=92)
        temporary = SAMPLES / ("_tmp_" + filename)
        temporary.write_bytes(raw.getvalue())
        try:
            boxes = [d["box"] for d in api.post_form("/api/reid/detect", {}, [("image", temporary)])["detections"]]
        finally:
            temporary.unlink(missing_ok=True)
        print(f"  people found: {len(boxes)}; heads blurred: {blur_heads(image, boxes)}")
        image.save(SAMPLES / filename, "JPEG", quality=92)
    return 0


if __name__ == "__main__":
    sys.exit(main())
