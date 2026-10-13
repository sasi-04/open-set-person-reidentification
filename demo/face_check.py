"""
Try the system with YOUR OWN volunteers' photos - no web interface needed.

In plain words: put photos of the people who have agreed to take part in a folder, run this, and it tells you - for every
test photo - whether the system said MATCH (and to whom), UNKNOWN or REVIEW, with the face and body scores, next to
what the answer SHOULD have been. It is the quickest honest way to see the system work (or fail) on real people.

Folder layout (names are only labels; use first names or nicknames - they become reference IDs like "check-anna"):

    my_photos/
        enroll/
            anna/   anna_1.jpg  anna_2.jpg        <- 2-3 clear, front-facing photos of each person to enrol
            ben/    ben_1.jpg   ben_2.jpg
        test/
            anna/   new_photo.jpg  back_view.jpg  <- NEW photos of enrolled people: should be MATCH (or REVIEW if poor)
            ben/    ...
            visitor/  ...                         <- anyone NOT enrolled (a folder name that is not in enroll/): should be UNKNOWN

Run (the server must be running, normally on http://127.0.0.1:8000):

    python demo/face_check.py my_photos --i-have-consent
    python demo/face_check.py my_photos --i-have-consent --keep      # leave the people enrolled afterwards
    python demo/face_check.py --cleanup                              # remove everyone this script enrolled

CONSENT: only use photos of people who have agreed. Enrolling stores a fingerprint of their face and body (biometric data)
until you delete them - this script deletes them again at the end unless you pass --keep. It only ever touches reference
IDs that start with "check-".

TIP for the strongest demonstration: put in test/ a photo of someone NOT enrolled who is wearing clothes similar to an
enrolled person's. A clothing-only matcher accepts that person; the face-first matcher should say UNKNOWN.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import Api, ApiError  # noqa: E402

PREFIX = "check-"
PHOTO = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
LABEL = {"accepted": "MATCH", "unknown": "UNKNOWN", "review_required": "REVIEW", "processing_error": "ERROR"}


def photos(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in PHOTO) if folder.is_dir() else []


def reference_of(name: str) -> str:
    return PREFIX + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def remove_checked(api: Api) -> int:
    removed = 0
    for item in api.get("/api/gallery", {"search": PREFIX, "limit": 100})["items"]:
        if item["reference_id"].startswith(PREFIX):
            api.delete(f"/api/gallery/{item['reference_id']}", {"confirm": item["reference_id"]})
            removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", nargs="?", type=Path, help="the folder with enroll/ and test/")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--i-have-consent", action="store_true", help="confirm that every person in the photos agreed to take part")
    parser.add_argument("--mode", choices=("crop", "all"), default="crop",
                        help="crop = each photo is one person (head-and-shoulders or tight crop); all = find the people in a full photo")
    parser.add_argument("--keep", action="store_true", help="leave the enrolled people in the gallery afterwards")
    parser.add_argument("--cleanup", action="store_true", help="only remove the people this script enrolled, then stop")
    args = parser.parse_args()
    api = Api(args.base_url, args.api_key)
    try:
        ready = api.get("/api/readiness")
    except ApiError as error:
        raise SystemExit(f"The server is not answering ({error.message}). Start it with scripts\\start.ps1.") from None

    if args.cleanup:
        print(f"Removed {remove_checked(api)} person(s) enrolled by this script.")
        return 0
    if not args.folder:
        parser.error("give the folder with enroll/ and test/")
    if not args.i_have_consent:
        raise SystemExit("Add --i-have-consent to confirm that every person in these photos agreed to take part.")

    policy = api.get("/api/config")["policy"]
    faces_on = policy["matching_mode"] == "face_body" and ready["components"]["face_models"]["ok"]
    print(f"Matching mode: {'FACE + BODY' if faces_on else 'BODY ONLY'}  (policy v{policy['version']}; face threshold {policy.get('face_accept_threshold')}, body threshold {policy['accept_threshold']})")
    if not faces_on:
        print("NOTE: faces are not in use - results will reflect clothing and build only. Turn on 'Face + body' in Model & System.\n")

    enrolled = {}
    for person in sorted(p for p in (args.folder / "enroll").iterdir() if p.is_dir()):
        pictures = photos(person)
        if not pictures:
            continue
        reference = reference_of(person.name)
        try:
            api.delete(f"/api/gallery/{reference}", {"confirm": reference})  # start from a known state
        except ApiError:
            pass
        answer = api.post_form("/api/gallery/enroll", {"reference_id": reference, "consent_confirmed": "true", "images_are_crops": "true" if args.mode == "crop" else "false"},
                               [("images", p) for p in pictures])
        usable = sum(f.get("face_status") == "ready" for f in answer["files"])
        enrolled[person.name.lower()] = reference
        print(f"enrolled {person.name:<14} {len(pictures)} photo(s), usable face in {usable}" + ("   <-- NO USABLE FACE: add a clear front-facing photo" if faces_on and usable == 0 else ""))
        for warning in answer["warnings"]:
            print("   warning:", warning[:140])

    rows, good = [], 0
    print(f"\n{'photo':<34}{'should be':<18}{'system said':<22}{'face':>7}{'body':>7}  note")
    try:
        for person in sorted(p for p in (args.folder / "test").iterdir() if p.is_dir()):
            expected_ref = enrolled.get(person.name.lower())
            for picture in photos(person):
                response = api.post_form("/api/reid/predict", {"mode": args.mode, "top_k": "3"}, [("image", picture)])
                result = response["people"][0] if response["people"] else None
                if result is None:
                    continue
                d = result["decision"]
                said = LABEL[d["outcome"]] + (f" {d['accepted_reference_id'].removeprefix(PREFIX)}" if d["accepted_reference_id"] else "")
                should = f"MATCH {person.name}" if expected_ref else "UNKNOWN"
                # a poor photo of an enrolled person may legitimately be REVIEW; a stranger must never be a MATCH
                ok = (d["accepted_reference_id"] == expected_ref) if expected_ref and d["outcome"] == "accepted" else (
                    d["outcome"] in ("review_required", "unknown") if expected_ref else d["outcome"] != "accepted")
                if expected_ref and d["outcome"] == "unknown":
                    ok = False
                good += ok
                f = d.get("top1_face_score")
                b = d.get("top1_body_score") if d.get("top1_body_score") is not None else (d["top1_score"] if d.get("basis") == "body" else None)
                note = (result.get("face") or {}).get("message") or ""
                rows.append(ok)
                print(f"{(person.name + '/' + picture.name)[:33]:<34}{should:<18}{said:<22}{'-' if f is None else f'{f:.2f}':>7}{'-' if b is None else f'{b:.2f}':>7}  {'OK ' if ok else '!! '}{note[:60]}")
    finally:
        if not args.keep:
            print(f"\n(removed {remove_checked(api)} enrolled person(s); use --keep to leave them)")

    print(f"\n{good} of {len(rows)} photos behaved as expected.  OK = right person matched / stranger not matched / a poor photo sent to review.")
    print("Remember: a small, friendly sample is a demonstration, not an accuracy measurement.")
    return 0 if good == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
