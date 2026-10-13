"""
Fetch the public-domain face photos used by the face demonstration.

In plain words: to SHOW face matching you need photos of the same person in different clothes and settings, plus a
stranger. Photos of private people cannot be bundled, and news photos (like the LFW test set) cannot be redistributed. These
are NASA astronaut photographs on Wikimedia Commons that are in the PUBLIC DOMAIN (work of the US government) - the script
asks the Commons API for each file's licence and REFUSES anything that is not public domain or CC0.

It builds the folder layout that ``demo/face_check.py`` understands:

    demo/samples/faces/
        enroll/<person>/...   the photos used to enrol each person (two each)
        test/<person>/...     NEW photos of enrolled people (should be MATCH) and of a person who is NOT enrolled (should be UNKNOWN)

and writes ``demo/samples/faces/SOURCES.json`` (title, author, date, licence, page URL for every photo).

These are real, named public figures photographed at work. They are used here only to show that a face matcher recognises the
same person across photos; nothing is inferred about them. For your own demonstration, prefer photos of consenting volunteers
(see demo/face_check.py).

    python demo/prepare_faces.py
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

OUT = Path(__file__).resolve().parent / "samples" / "faces"
UA = {"User-Agent": "OpenIDVisionDemo/1.0 (demo sample preparation)"}
OK_LICENCES = ("public domain", "cc0", "pd-")

# (folder, role, file name on Commons, saved as)
PHOTOS = [
    ("collins", "enroll", "Commander Eileen Collins - GPN-2000-001177.jpg", "collins_enrol_1_orange_suit_1998.jpg"),
    ("collins", "enroll", "Eileen Collins, early NASA portrait.jpg", "collins_enrol_2_navy_jacket_early.jpg"),
    ("collins", "test", "Eileen Collins climbing into an M-113.jpg", "collins_test_1_nasa_jacket_1999.jpg"),
    ("collins", "test", "Defense.gov photo essay 100310-D-0653H-037.jpg", "collins_test_2_suit_jacket_2010.jpg"),
    ("collins", "test", "KSC-04pd1046.jpg", "collins_test_3_hard_hat_2004.jpg"),
    ("jemison", "enroll", "Mae Carol Jemison.jpg", "jemison_enrol_1_orange_suit_1992.jpg"),
    ("jemison", "enroll", "Mae Jemison - Official portrait of 1987 astronaut candidate.jpg", "jemison_enrol_2_blue_jacket_1987.jpg"),
    ("jemison", "test", "Mae Jemison floating in space during STS-47.jpg", "jemison_test_1_in_flight_1992.jpg"),
    ("jemison", "test", "Mae-jemison.jpg", "jemison_test_2_lab_1992.jpg"),
    ("ride", "test", "Dr. Sally Ride in Space Shuttle cockpit on mission STS-7 (1983) with three levitating calculators HP-41C.jpg", "ride_stranger_1_cockpit_1983.jpg"),
    ("ride", "test", "STS007-12-536.jpg", "ride_stranger_2_blue_shirt_1983.jpg"),
    ("ride", "test", "S83-35763.jpg", "ride_stranger_3_headset_1983.jpg"),
    # Strangers (never enrolled) photographed in the SAME orange flight suit as an enrolled person: the open-set stress test.
    # Measured with the real models against the enrolled orange-suit photos: body similarity 0.74 - 0.82 (above the 0.70
    # clothes-only threshold, so a clothes-only matcher accepts them) but face similarity <= 0.17 (so face + body says UNKNOWN).
    ("lookalike", "test", "Alan G. Poindexter.jpg", "stranger_same_suit_1_poindexter.jpg"),
    ("lookalike", "test", "Roberta Bondar2.jpg", "stranger_same_suit_2_bondar.jpg"),
    ("lookalike", "test", "Barry Wilmore.jpg", "stranger_same_suit_3_wilmore.jpg"),
]


def api(**params):
    params.update(format="json")
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))  # asked to slow down: wait, then try again
    raise RuntimeError("unreachable")


def find(file_name: str) -> dict:
    """The Commons record for one file, or an exception if it is missing or not public domain."""
    title = "File:" + file_name
    data = api(action="query", prop="imageinfo", iiprop="extmetadata|url|size", iiurlwidth=800, titles=title)
    page = next(iter(data["query"]["pages"].values()))
    if "imageinfo" not in page:
        # file names on Commons sometimes differ slightly; look for the closest match by search
        hits = api(action="query", list="search", srsearch=f'intitle:"{file_name.rsplit(".", 1)[0][:60]}"', srnamespace=6, srlimit=3)["query"]["search"]
        if not hits:
            raise SystemExit(f"Not found on Commons: {file_name}")
        return find(hits[0]["title"].removeprefix("File:"))
    info = page["imageinfo"][0]
    meta = info["extmetadata"]
    licence = (meta.get("LicenseShortName", {}).get("value") or "")
    if not licence.lower().startswith(OK_LICENCES):
        raise SystemExit(f"Refusing {file_name}: licence is {licence!r}, not public domain / CC0.")
    return {
        "title": page["title"], "licence": licence, "page": info["descriptionurl"], "thumb": info["thumburl"],
        "author": re.sub("<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()[:120],
        "date": re.sub("<[^>]+>", "", meta.get("DateTimeOriginal", {}).get("value", "")).strip()[:60],
    }


def main() -> int:
    sources = []
    for folder, role, file_name, saved_as in PHOTOS:
        record = find(file_name)
        time.sleep(1.0)
        data = urllib.request.urlopen(urllib.request.Request(record["thumb"], headers=UA), timeout=120).read()
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        destination = OUT / role / folder / saved_as
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, "JPEG", quality=92)
        sources.append({"file": f"{role}/{folder}/{saved_as}", "role": role, "person": folder, **{k: record[k] for k in ("title", "licence", "author", "date", "page")},
                        "size": list(image.size)})
        print(f"{role:<7}{folder:<9}{saved_as:<42} {record['licence']:<14} {image.size}")
    (OUT / "SOURCES.json").write_text(json.dumps(sources, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {len(sources)} photos and SOURCES.json to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
