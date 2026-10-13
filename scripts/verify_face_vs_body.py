"""
End-to-end check of the RUNNING system: does adding the face stop strangers being accepted?

In plain words: it enrols several real people (two photos each) through the normal API, then shows the system
  * new photos of those same people  - they should be MATCHED to the right person, and
  * photos of people who were never enrolled - they should be UNKNOWN (never accepted).
It runs the identical queries twice - under the original BODY-ONLY policy and under the FACE + BODY policy - and prints
the two result tables side by side, so the effect of the face is measured, not claimed.

Honest limits (also printed in the report):
  * the pictures are LFW head-and-shoulders photographs, which are NOT what the body model was built for (it expects
    full-body pedestrian crops), so the body-only column shows how the body model behaves on this kind of picture, not
    its best case. The face stage is measured separately on the full LFW protocol (scripts/evaluate_face_lfw.py).
  * a small random sample; the numbers describe this run, they are not a benchmark.

It only touches identities whose reference ID starts with ``lfwcheck-`` (it removes them at the end) and puts the
policy back as it found it. Use a test instance, not a gallery you care about:

    $env:REID_DATA_DIR = "D:\\scratch\\data"; powershell -File scripts\\start.ps1 -Port 8765
    python scripts/verify_face_vs_body.py --lfw D:\\data\\lfw --base-url http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))
from _client import Api  # noqa: E402

PREFIX = "lfwcheck-"


def photo(root: Path, name: str, index: int) -> Path:
    return root / name / f"{name}_{index:04d}.jpg"


def reference_of(name: str) -> str:
    return PREFIX + name.lower().replace("_", "-")


def ask(api: Api, picture: Path) -> dict:
    return api.post_form("/api/reid/predict", {"mode": "crop", "top_k": "3"}, [("image", picture)])["people"][0]["decision"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lfw", required=True, type=Path, help="folder that contains lfw/<Person_Name>/<Person_Name>_0001.jpg")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--enrolled", type=int, default=10, help="how many people to enrol")
    parser.add_argument("--strangers", type=int, default=60, help="how many never-enrolled people to test")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=None, help="write the numbers as JSON")
    parser.add_argument("--details", action="store_true", help="also print WHO was wrongly accepted and with which scores (for diagnosis)")
    args = parser.parse_args()
    mistakes: list[str] = []

    api = Api(args.base_url, args.api_key)
    root = args.lfw / "lfw"
    if not api.get("/api/readiness")["components"]["face_models"]["ok"]:
        raise SystemExit("The server has no face models loaded - run scripts/download_weights.py and restart it.")
    existing = api.get("/api/gallery", {"limit": 100})["items"]
    if any(not item["reference_id"].startswith(PREFIX) for item in existing):
        print("NOTE: the gallery already contains other people; they stay, but they can change the results. Use a clean test instance for clean numbers.")

    rng = random.Random(args.seed)
    people = sorted(d.name for d in root.iterdir() if d.is_dir() and len(list(d.glob("*.jpg"))) >= 4)
    enrolled = rng.sample(people, args.enrolled)
    strangers = rng.sample([p for p in people if p not in enrolled], args.strangers)

    for name in enrolled:  # photos 1 and 2 are the references; 3 and 4 are held back as "seen again"
        api.post_form("/api/gallery/enroll", {"reference_id": reference_of(name), "consent_confirmed": "true", "images_are_crops": "true"},
                      [("images", photo(root, name, 1)), ("images", photo(root, name, 2))])
    previous = api.get("/api/config")["policy"]

    def run(mode: str) -> dict:
        api.post_json("/api/config/thresholds", {"accept_threshold": previous["accept_threshold"], "matching_mode": mode, "confirm": True,
                                                  "note": f"verify_face_vs_body.py ({mode})"})
        count = {"same_person_queries": 0, "matched_correct_person": 0, "matched_WRONG_person": 0, "review": 0, "unknown": 0,
                 "stranger_queries": 0, "stranger_ACCEPTED": 0, "stranger_review": 0, "stranger_unknown": 0}
        for name in enrolled:
            for index in (3, 4):
                d = ask(api, photo(root, name, index))
                count["same_person_queries"] += 1
                if d["outcome"] == "accepted":
                    count["matched_correct_person" if d["accepted_reference_id"] == reference_of(name) else "matched_WRONG_person"] += 1
                else:
                    count["review" if d["outcome"] == "review_required" else "unknown"] += 1
        for name in strangers:
            d = ask(api, photo(root, name, 1))
            count["stranger_queries"] += 1
            count["stranger_ACCEPTED" if d["outcome"] == "accepted" else ("stranger_review" if d["outcome"] == "review_required" else "stranger_unknown")] += 1
            if d["outcome"] == "accepted" and mode == "face_body":
                mistakes.append(f"stranger {name}_0001 accepted as {d['accepted_reference_id']} (face {d['top1_face_score']}, body {d['top1_body_score']})")
        return count

    try:
        results = {"body_only": run("body"), "face_and_body": run("face_body")}
    finally:  # leave the server as we found it
        api.post_json("/api/config/thresholds", {"accept_threshold": previous["accept_threshold"], "matching_mode": previous["matching_mode"],
                                                  "confirm": True, "note": "verify_face_vs_body.py: restored"})
        for name in enrolled:
            ref = reference_of(name)
            api.delete(f"/api/gallery/{ref}", {"confirm": ref})

    b, f = results["body_only"], results["face_and_body"]
    rows = [("People enrolled", args.enrolled, args.enrolled), ("", "", ""),
            ("SAME-PERSON queries", b["same_person_queries"], f["same_person_queries"]),
            ("  matched to the right person", b["matched_correct_person"], f["matched_correct_person"]),
            ("  matched to the WRONG person", b["matched_WRONG_person"], f["matched_WRONG_person"]),
            ("  sent to review", b["review"], f["review"]),
            ("  rejected (unknown)", b["unknown"], f["unknown"]), ("", "", ""),
            ("STRANGER queries (never enrolled)", b["stranger_queries"], f["stranger_queries"]),
            ("  ACCEPTED (false accept)", b["stranger_ACCEPTED"], f["stranger_ACCEPTED"]),
            ("  sent to review", b["stranger_review"], f["stranger_review"]),
            ("  correctly rejected (unknown)", b["stranger_unknown"], f["stranger_unknown"])]
    print(f"\n{'':40}{'BODY ONLY':>12}{'FACE + BODY':>14}")
    for label, a, c in rows:
        print(f"{label:40}{a!s:>12}{c!s:>14}")
    if args.details and mistakes:
        print("\nFalse accepts under FACE + BODY:")
        for line in mistakes:
            print("  ", line)
    print("\nCaveats: LFW head-and-shoulders photos are outside the body model's design (it expects full-body pedestrian crops); a small "
          "random sample from public-figure news photos. Read it as 'what the face adds', not as an accuracy benchmark.")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"seed": args.seed, "people_enrolled": args.enrolled, "strangers": args.strangers,
                                         "results": results}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
