"""
Run every demo scenario against the RUNNING OpenID Vision server and show the real results.

In plain words: this does by script what you would do by hand in the web interface - enrol a few example people, then show the
system pictures and short clips, and print what it decided and why. Nothing is faked or pre-recorded: every line comes from the
live server's own answers, and each scenario states the answer it SHOULD give so you can see at a glance whether the system behaved.

    python demo/run_demo.py                      # the scenarios (about 40 s on a laptop CPU)
    python demo/run_demo.py --compare            # also re-run the face photos under the OLD clothing-only policy, side by side
    python demo/run_demo.py --lab                # also the Lookalike Failure Lab on the synthetic smoke-test set (1-2 min)
    python demo/run_demo.py --cleanup            # remove what the demo created

The scenarios, in two parts:
  PART A - FACE + BODY (the main show): the same person in different clothes and years is recognised; strangers are not.
  PART B - NO USABLE FACE: pictures with the heads blurred (so no face can be used) show the safe fallback - the system will not
           accept on clothing alone; it asks a person (REVIEW).
It enrols three example people (reference IDs start with "demo-") and leaves them in the gallery so you can repeat any scenario by
hand with the pictures in demo/samples/. Nothing else in the gallery is touched. The pictures are public domain (demo/samples/SOURCES.md).

``--compare`` and ``--enable-faces`` create a new, audited policy version (and ``--compare`` puts the old one back at the end).
Standard library only: runs with any Python 3.9+.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import Api, ApiError  # noqa: E402

HERE = Path(__file__).resolve().parent
SAMPLES = HERE / "samples"
FACES = SAMPLES / "faces"
PEOPLE = {  # reference id -> (label, [reference photos])
    "demo-collins": ("Example person 1 (public-domain NASA photos)", sorted((FACES / "enroll" / "collins").glob("*.jpg"))),
    "demo-jemison": ("Example person 2 (public-domain NASA photos)", sorted((FACES / "enroll" / "jemison").glob("*.jpg"))),
    "demo-person-a": ("Example person 3 - street photo, head blurred, so NO face on file", [SAMPLES / "person_A_reference_1.jpg", SAMPLES / "person_A_reference_2.jpg"]),
}
LABELS = {"accepted": "MATCH", "unknown": "UNKNOWN", "review_required": "REVIEW", "processing_error": "PROCESSING ERROR"}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def say(text: str = "") -> None:
    print(text, flush=True)


def label(outcome: str) -> str:
    return LABELS.get(outcome, outcome.upper())


def save_json(folder: Path, name: str, data) -> None:
    (folder / name).write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------------------------------- set-up
def check_server(api: Api) -> dict:
    try:
        ready = api.get("/api/readiness")
    except ApiError as error:
        raise SystemExit(f"\nThe server is not answering ({error.message}).\nStart it first, in another window:   powershell -ExecutionPolicy Bypass -File scripts\\start.ps1\nthen run this demo again.") from None
    if ready["status"] == "not_ready":
        raise SystemExit("\nThe server is running but its models are not loaded: " + str(ready["components"]["embedding_model"].get("error")) + "\nSee README section 22 (troubleshooting).")
    return ready


def set_mode(api: Api, mode: str, note: str) -> dict:
    policy = api.get("/api/config")["policy"]
    body = {"accept_threshold": policy["accept_threshold"], "min_margin": policy["min_margin"], "margin_action": policy["margin_action"],
            "review_on_quality_flags": policy["review_on_quality_flags"], "matching_mode": mode, "confirm": True, "note": note}
    return api.post_json("/api/config/thresholds", body)


def enrol_examples(api: Api) -> None:
    existing = {item["reference_id"] for item in api.get("/api/gallery", {"search": "demo-", "limit": 100})["items"]}
    for reference, (text, photos) in PEOPLE.items():
        if reference in existing:  # start from a known state; only OUR example identities are replaced
            api.delete(f"/api/gallery/{reference}", {"confirm": reference})
        answer = api.post_form("/api/gallery/enroll", {"reference_id": reference, "label": text, "consent_confirmed": "true", "images_are_crops": "true"},
                               [("images", photo) for photo in photos])
        usable = sum(f.get("face_status") == "ready" for f in answer["files"])
        say(f"   enrolled {reference:<14} {len(photos)} photos, usable face on file in {usable}")


# --------------------------------------------------------------------------------------------------- scenarios
class Report:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, scenario: str, expected: str, actual: str, ok: bool, detail: str) -> None:
        self.rows.append({"scenario": scenario, "expected": expected, "actual": actual, "ok": ok, "detail": detail})
        say(f"   -> {actual}   [{'OK, as intended' if ok else 'DIFFERENT FROM THE INTENDED RESULT'}]")
        for line in detail.split("\n"):
            say(f"      {line}")
        say()


def predict(api: Api, picture: Path, mode: str, out: Path, name: str) -> dict:
    response = api.post_form("/api/reid/predict", {"mode": mode, "top_k": "3"}, [("image", picture)])
    save_json(out, f"{name}.decision.json", response)
    for fmt in ("json", "csv"):
        (out / f"{name}.decision_record.{fmt}").write_bytes(api.get(f"/api/reid/history/{response['request_id']}/export", {"format": fmt}, raw=True))
    return response


def describe(person: dict) -> str:
    d = person["decision"]
    parts = [f"{label(d['outcome'])}: {d['reason']}"]
    if d.get("matching_mode") == "face_body":
        face = person.get("face") or {}
        parts.append(f"decided by: {d['basis']}   |   face similarity {d['top1_face_score'] if d['top1_face_score'] is not None else '-'}"
                     f"   body similarity {d['top1_body_score'] if d['top1_body_score'] is not None else '-'}   |   face found: {face.get('status', '-')}")
    return "\n".join(parts)


def photo_scenario(api, report, out, number, title, story, picture: Path, expect_outcome, expect_ref, why, how="Match Studio -> tick 'Image is already a person crop' -> Run re-identification"):
    say(f"SCENARIO {number}: {title}")
    say(f"   {story}")
    say(f"   picture: demo/samples/{picture.relative_to(SAMPLES).as_posix()}      (web interface: {how})")
    say(f"   intended result: {label(expect_outcome)}{' ' + expect_ref.removeprefix('demo-') if expect_ref else ''} - {why}")
    response = predict(api, picture, "crop", out, f"scenario{number:02d}")
    person = response["people"][0]
    d = person["decision"]
    ok = d["outcome"] == expect_outcome and (expect_ref is None or d["accepted_reference_id"] == expect_ref)
    got = label(d["outcome"]) + (f" {d['accepted_reference_id'].removeprefix('demo-')}" if d["accepted_reference_id"] else "")
    report.add(f"{number}. {title}", label(expect_outcome) + (f" {expect_ref.removeprefix('demo-')}" if expect_ref else ""), got, ok,
               describe(person) + f"\nmeasured time for this request: {response['timings_ms']['total_ms']:.0f} ms")
    return d


def scene_scenario(api, report, out, number):
    say(f"SCENARIO {number}: a busy street scene - everyone is compared with the gallery")
    say("   Seven people in one photo (heads blurred, so no face is usable). Each is found and decided separately; nobody here is enrolled.")
    say("   picture: demo/samples/scene_B_station_square.jpg      (web interface: Match Studio -> tick 'Match everyone found in the image' -> Run re-identification)")
    say("   intended result: nobody is a MATCH")
    response = predict(api, SAMPLES / "scene_B_station_square.jpg", "all", out, f"scenario{number:02d}")
    outcomes: dict[str, int] = {}
    for person in response["people"]:
        d = person["decision"]
        outcomes[d["outcome"]] = outcomes.get(d["outcome"], 0) + 1
        score = f"{d['top1_score']:.3f}" if d["top1_score"] is not None else "  -  "
        say(f"      person {person['index'] + 1}: {label(d['outcome']):<16} best similarity {score}   detector confidence {person['detector_score']:.2f}")
    counts = ", ".join(f"{n} x {label(o)}" for o, n in sorted(outcomes.items()))
    report.add(f"{number}. Busy scene, everyone compared", "no MATCH", counts, outcomes.get("accepted", 0) == 0,
               f"{len(response['people'])} people found and decided separately; total time {response['timings_ms']['total_ms']:.0f} ms")


def video_scenario(api, report, out, number, clip: str, story: str, expect: list[str], created: list[str]):
    say(f"SCENARIO {number}: a 3-second clip (video, one frame sampled per second)")
    say(f"   {story}")
    say(f"   clip: demo/samples/{clip}      (web interface: Video Explorer -> Browse files -> 1 s -> Analyse video)")
    say("   intended result: " + ", ".join(expect))
    job = api.post_form("/api/video/analyze", {"every_seconds": "1", "max_frames": "10"}, [("video", SAMPLES / clip)])
    created.append(job["run_id"])
    started = time.time()
    while job["status"] in ("queued", "running"):
        time.sleep(1)
        job = api.get(f"/api/video/jobs/{job['run_id']}")
    if job["status"] != "succeeded":
        report.add(f"{number}. Video {clip}", "3 frames analysed", job["status"], False, str(job.get("error")))
        return
    result = job["result"]
    save_json(out, f"scenario{number:02d}_video.result.json", result)
    (out / f"scenario{number:02d}_video.frames.csv").write_bytes(api.get(f"/api/video/jobs/{job['run_id']}/export", {"format": "frames_csv"}, raw=True))
    got = []
    for frame in result["frames"]:
        kinds = [p["outcome"] for p in frame["people"]]
        top = "accepted" if "accepted" in kinds else ("review_required" if "review_required" in kinds else (kinds[0] if kinds else "none"))
        got.append(label(top) if top != "none" else "nobody found")
        say(f"      t = {frame['time_seconds']:.0f} s: {len(frame['people'])} person(s) -> " + (", ".join(label(k) for k in kinds) if kinds else "nobody found"))
    s = result["summary"]
    report.add(f"{number}. Video {clip}", " / ".join(expect), " / ".join(got), got == expect,
               f"{s['frames_processed']} frames, {s['people_detected']} people detected; median {s['latency_ms']['processing_per_frame'].get('p50', 0):.0f} ms per frame; "
               f"job took {time.time() - started:.0f} s. The uploaded video was deleted by the server after processing.")


def lab_scenario(api, report, out, number, created):
    say(f"SCENARIO {number}: the Lookalike Failure Lab (on the synthetic smoke-test dataset)")
    datasets = {d["name"]: d for d in api.get("/api/evaluation/datasets")}
    smoke = datasets.get("smoke_synthetic")
    if not smoke or not smoke["available"]:
        say("   skipped: no dataset is installed. Create the synthetic one with:  python scripts\\make_smoke_dataset.py  and run again with --lab")
        say()
        return
    say("   Searches the 'test' people for the pairs of DIFFERENT people the model finds most alike, builds a challenge set, lists real mistakes.")
    say("   (cartoon mannequins, BODY model only: the numbers prove the lab works, they say NOTHING about real accuracy)   web interface: Lookalike Failure Lab -> Run look-alike experiment")
    body = {"dataset": "smoke_synthetic", "seed": 0, "mining_split": "test", "top_pairs": 12, "images_per_pair": 2, "max_failures": 8,
            "target": {"mode": "fixed_recall", "target_recall": 0.9, "target_far": 0.01, "recall_metric": "dir1"},
            "protocol": {"gallery_shots": 3, "dev_fraction": 0.4, "calibration_fraction": 0.2, "max_identities_per_split": 30,
                         "max_images_per_identity": 8, "cross_camera": True}}
    run = api.post_json("/api/lookalike/run", body)
    created.append(run["run_id"])
    last = ""
    while run["status"] in ("queued", "running"):
        time.sleep(2)
        run = api.get(f"/api/lookalike/runs/{run['run_id']}")
        if run["stage"] != last:
            last = run["stage"]
            say(f"      ... {run['progress'] * 100:3.0f}%  {last}")
    if run["status"] != "succeeded":
        report.add(f"{number}. Lookalike Failure Lab", "finishes", run["status"], False, str(run.get("error")))
        return
    result = run["result"]
    folder = out / "lookalike_lab"
    folder.mkdir(exist_ok=True)
    for fmt, name in (("json", "experiment.json"), ("pairs_csv", "pairs.csv"), ("failures_csv", "failures.csv"), ("summary_csv", "summary.csv"), ("md", "report.md")):
        (folder / name).write_bytes(api.get(f"/api/lookalike/runs/{run['run_id']}/export", {"format": fmt}, raw=True))
    ch = result["models"]["baseline"]["challenge"]
    report.add(f"{number}. Lookalike Failure Lab (synthetic data)", "runs; honest warnings; no invented comparison", "finished",
               result["models"]["improved"]["status"] == "unavailable" and bool(result["warnings"]),
               f"{result['challenge_set']['counts']['identity_pairs']} look-alike pairs, hard strangers accepted {ch['false_accepts']}/{ch['impostor_pairs']} (all-pairs rate {ch['far_all_pairs_reference']:.1%}); "
               f"warnings: {len(result['warnings'])}; improved model: {result['models']['improved']['status']} (none has been trained). Exports saved in {folder.name}/")


def compare_with_body_only(api: Api, out: Path) -> None:
    """The same face photos, once under face + body and once under the old clothing-only policy."""
    say("=" * 100)
    say("COMPARISON: the same photos under the OLD clothing-only policy and under FACE + BODY")
    say("=" * 100)
    photos = [(FACES / "test" / "collins" / n, "demo-collins") for n in ("collins_test_1_nasa_jacket_1999.jpg", "collins_test_2_suit_jacket_2010.jpg", "collins_test_3_hard_hat_2004.jpg")]
    photos += [(FACES / "test" / "jemison" / n, "demo-jemison") for n in ("jemison_test_1_in_flight_1992.jpg", "jemison_test_2_lab_1992.jpg")]
    photos += [(FACES / "test" / "ride" / n, None) for n in ("ride_stranger_1_cockpit_1983.jpg", "ride_stranger_2_blue_shirt_1983.jpg", "ride_stranger_3_headset_1983.jpg")]
    original = api.get("/api/config")["policy"]
    table = {}
    try:
        for mode in ("body", "face_body"):
            set_mode(api, mode, f"run_demo.py --compare ({mode})")
            table[mode] = [(p.name, ref, api.post_form("/api/reid/predict", {"mode": "crop", "top_k": "3"}, [("image", p)])["people"][0]["decision"]) for p, ref in photos]
    finally:
        set_mode(api, original["matching_mode"], "run_demo.py --compare: restored")
    say(f"{'photo':<40}{'should be':<18}{'CLOTHING ONLY':<20}{'FACE + BODY':<20}")
    score = {"body": 0, "face_body": 0}
    rows = []
    for index, (name, ref, _) in enumerate(table["body"]):
        should = f"MATCH {ref.removeprefix('demo-')}" if ref else "UNKNOWN"
        cells = []
        for mode in ("body", "face_body"):
            d = table[mode][index][2]
            said = label(d["outcome"]) + (f" {d['accepted_reference_id'].removeprefix('demo-')}" if d["accepted_reference_id"] else "")
            good = (d["accepted_reference_id"] == ref) if ref else d["outcome"] != "accepted"
            score[mode] += good
            cells.append(said + ("" if good else "  (wrong)"))
        rows.append([name, should, *cells])
        say(f"{name[:39]:<40}{should:<18}{cells[0]:<20}{cells[1]:<20}")
    say(f"\nright answers: clothing only {score['body']} of {len(photos)}   |   face + body {score['face_body']} of {len(photos)}")
    say("(Same person in different clothes: clothing alone cannot recognise them. A small public-domain sample - a demonstration, not a benchmark.)\n")
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["photo", "should_be", "clothing_only", "face_and_body"])
    writer.writerows(rows)
    (out / "comparison_clothing_vs_face.csv").write_text(buffer.getvalue(), encoding="utf-8")


# ------------------------------------------------------------------------------------------------------ main
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="where the server is running")
    parser.add_argument("--api-key", default=None, help="only needed if the server was started with access keys switched on")
    parser.add_argument("--lab", action="store_true", help="also run the Lookalike Failure Lab (needs the synthetic dataset)")
    parser.add_argument("--compare", action="store_true", help="also show the face photos under the OLD clothing-only policy, side by side (temporarily changes the policy, then restores it)")
    parser.add_argument("--enable-faces", action="store_true", help="switch the policy to Face + body first (creates a new policy version) if it is not already on")
    parser.add_argument("--cleanup", action="store_true", help="remove the example people and the demo jobs, then stop")
    parser.add_argument("--output", default=None, help="folder for the saved results (default: demo/output_latest)")
    args = parser.parse_args()

    api = Api(args.base_url, args.api_key)
    ready = check_server(api)

    if args.cleanup:
        for reference in PEOPLE:
            try:
                api.delete(f"/api/gallery/{reference}", {"confirm": reference})
                say(f"Removed {reference}.")
            except ApiError:
                pass
        for job in api.get("/api/video/jobs", {"limit": 100})["items"]:
            if job["dataset"] in ("clip_street.avi", "clip_faces.avi"):
                api.delete(f"/api/video/jobs/{job['run_id']}")
                say("Removed a demo video job.")
        return 0

    out = Path(args.output) if args.output else HERE / "output_latest"
    out.mkdir(parents=True, exist_ok=True)
    policy = api.get("/api/config")["policy"]
    if args.enable_faces and policy["matching_mode"] != "face_body":
        policy = set_mode(api, "face_body", "run_demo.py --enable-faces")
    faces_on = policy["matching_mode"] == "face_body" and ready["components"]["face_models"]["ok"]
    model = ready["components"]["embedding_model"]
    say("=" * 100)
    say("OpenID Vision - demo run")
    say("=" * 100)
    say(f"server       : {args.base_url}   ({ready['status']}; {model.get('architecture')} on {ready['components']['device'].get('type', '?').upper()}; "
        f"face models {'loaded' if ready['components']['face_models']['ok'] else 'NOT loaded'})")
    say(f"matching mode: {'FACE + BODY (the face decides when a usable face is visible)' if faces_on else 'BODY ONLY - the face scenarios below will NOT behave as intended; use --enable-faces'}")
    say(f"decision rule: face MATCH at similarity >= {policy.get('face_accept_threshold')} (review band {policy.get('face_review_band')} below it); body threshold {policy['accept_threshold']:.2f}; "
        f"policy v{policy['version']}, status {policy['status'].upper()} - not calibrated on this system's own cameras")
    say("meaning     : similarity is a retrieval score from -1 to 1, NOT a probability.  UNKNOWN = no supported match, not a finding about a person.")
    say()
    say("SET-UP: the example people")
    enrol_examples(api)
    say()

    report, created = Report(), []
    say("#" * 100)
    say("PART A - FACE + BODY: the face decides when it can be trusted")
    say("#" * 100 + "\n")
    t = FACES / "test"
    photo_scenario(api, report, out, 1, "Same person, different clothes and 12 years later", "Example person 1, photographed in 2010 in a suit jacket - the enrolled photos show her in a flight suit and a navy jacket.",
                   t / "collins" / "collins_test_2_suit_jacket_2010.jpg", "accepted", "demo-collins", "the FACE matches, so clothing does not matter")
    photo_scenario(api, report, out, 2, "Same person, a different setting", "Example person 1 again, in a NASA jacket outdoors (1999).",
                   t / "collins" / "collins_test_1_nasa_jacket_1999.jpg", "accepted", "demo-collins", "the face matches")
    photo_scenario(api, report, out, 3, "A second enrolled person", "Example person 2 in flight, wearing a headband - unlike either enrolled photo.",
                   t / "jemison" / "jemison_test_1_in_flight_1992.jpg", "accepted", "demo-jemison", "the face matches the right person, not the other enrolled person")
    photo_scenario(api, report, out, 4, "A stranger", "Somebody who was never enrolled, in a dark-blue shirt.",
                   t / "ride" / "ride_stranger_2_blue_shirt_1983.jpg", "unknown", None, "the best face similarity is far below the threshold")
    photo_scenario(api, report, out, 5, "Another stranger", "A second picture of the same never-enrolled person, in a cockpit.",
                   t / "ride" / "ride_stranger_1_cockpit_1983.jpg", "unknown", None, "no enrolled face is close enough")
    video_scenario(api, report, out, 6, "clip_faces.avi", "Example person 1, then the stranger, then example person 1 again. Each sampled frame is judged on its own; nobody is tracked from frame to frame.",
                   ["MATCH", "UNKNOWN", "MATCH"], created)

    say("#" * 100)
    say("PART B - NO USABLE FACE: the safe fallback (heads are blurred in these pictures)")
    say("#" * 100 + "\n")
    photo_scenario(api, report, out, 7, "The enrolled street person, seen again - but no face is visible",
                   "Example person 3 again (a smaller, darker photo). The head is blurred, so only clothing and build can be compared.",
                   SAMPLES / "query_1_same_person.jpg", "review_required", None,
                   "clothing matches, but clothing alone is not enough for an automatic MATCH, so a person is asked")
    photo_scenario(api, report, out, 8, "A stranger without a visible face", "Somebody else, in a mustard jacket, head blurred.",
                   SAMPLES / "query_2_stranger.jpg", "unknown", None, "clothing and build are not similar enough")
    photo_scenario(api, report, out, 9, "A poor-quality picture", "Example person 3 again, half the size and heavily out of focus.",
                   SAMPLES / "query_3_blurry.jpg", "review_required", None, "the picture itself is shaky, so a human should look instead of the system guessing")
    scene_scenario(api, report, out, 10)
    video_scenario(api, report, out, 11, "clip_street.avi", "Example person 3, a different scene, example person 3 again - with blurred heads. The clothing matches in frames 1 and 3.",
                   ["REVIEW", "UNKNOWN", "REVIEW"], created)
    if args.lab:
        lab_scenario(api, report, out, 12, created)

    say("=" * 100)
    say("SUMMARY")
    say("=" * 100)
    for row in report.rows:
        say(f"  [{'OK' if row['ok'] else '!!'}] {row['scenario']:<62} intended: {row['expected']:<24} got: {row['actual']}")
    passed = sum(r["ok"] for r in report.rows)
    say(f"\n  {passed} of {len(report.rows)} scenarios behaved as intended.")
    if passed != len(report.rows):
        say("  If one differs: the policy may have been changed (Model & System Settings), the face models may not be loaded, or other people in the gallery may be interfering.")
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["scenario", "intended", "actual", "as_intended", "detail"])
    for row in report.rows:
        writer.writerow([row["scenario"], row["expected"], row["actual"], row["ok"], row["detail"].replace("\n", " | ")])
    (out / "summary.csv").write_text(buffer.getvalue(), encoding="utf-8")

    if args.compare:
        say()
        compare_with_body_only(api, out)
    say(f"\nSaved to: {out}   (decision records as JSON and CSV, video results, exports)")
    say("NEXT: open " + args.base_url + " and repeat any scenario by hand with the pictures in demo/samples/ - the example people are still enrolled.")
    say("      When finished:  python demo/run_demo.py --cleanup")
    return 0 if passed == len(report.rows) else 1


if __name__ == "__main__":
    sys.exit(main())
