"""
Run the built-in open-set example from the command line (the same analysis the home page shows) and save the result.

In plain words: the home page of the website has a "Run the example" button. This script presses it for you, prints one line per
photo - what the system (face + body) decided, whether that was right, and what a clothes-only matcher would have decided -
and writes everything to docs/results/open_set_example.json so the numbers quoted in the documents can be traced to a file.

It is READ-ONLY for your data: the example uses a private, temporary gallery held in the server's memory. Your real gallery,
decision history and audit trail are not touched. Exit code 0 = the system gave the right answer for every photo.

    python demo\\run_open_set_example.py                      (server on http://127.0.0.1:8000)
    python demo\\run_open_set_example.py --base-url http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import Api, ApiError  # noqa: E402

LOOKALIKE_GROUP = "lookalike"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "results" / "open_set_example.json"
WORDS = {"accepted": "MATCH", "unknown": "UNKNOWN", "review_required": "REVIEW", "processing_error": "ERROR"}
VERDICTS = {
    "correct": "right", "review": "sent to a person", "cautious": "not accepted", "false_accept": "STRANGER ACCEPTED",
    "wrong_person": "WRONG PERSON", "missed": "KNOWN PERSON MISSED", "risky": "ACCEPTED ON CLOTHES ALONE",
}


def describe(decision: dict) -> str:
    score = decision["face_score"] if decision["basis"] == "face" and decision["face_score"] is not None else decision["top1_score"]
    kind = "face" if decision["basis"] == "face" and decision["face_score"] is not None else "clothes"
    named = f" {decision['accepted_label']}" if decision["accepted_label"] else ""
    shown = "" if score is None else f" ({kind} {score:.2f})"
    return f"{WORDS.get(decision['outcome'], decision['outcome'])}{named}{shown} - {VERDICTS.get(decision['verdict'], decision['verdict'])}"


def count(results: list[dict], column: str, predicate) -> tuple[int, int]:
    chosen = [r for r in results if predicate(r)]
    return sum(1 for r in chosen if r[column]["verdict"] == "correct"), len(chosen)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=None, help="only needed if the server was started with access keys switched on")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="where to save the result (JSON)")
    args = parser.parse_args()
    api = Api(args.base_url, args.api_key)

    try:
        info = api.get("/api/demo")
        if not info["available"]:
            print("The example is not available on this server:", info["reason"])
            return 2
        started = time.perf_counter()
        prepared = api.post_json("/api/demo/prepare", {})
        print(f"Example gallery built in {prepared['built_ms'] / 1000:.1f} s: " + ", ".join(f"{p['label']} ({len(p['photos'])} photos, {p['n_faces']} with a usable face)" for p in prepared["people"]))
        rules = prepared["rules"]
        print(f"Rules in force: face line {rules['face_threshold']} (+ review band {rules['face_review_band']}), clothes line {rules['body_threshold']}, "
              f"policy v{rules['policy_version']} ({rules['policy_status']}).\n")

        results = []
        for case in info["cases"]:
            answer = api.post_json(f"/api/demo/cases/{case['id']}", {})
            results.append({"id": case["id"], "group": case["group"], "title": case["title"], "expect": case["expect"], **{k: answer[k] for k in ("face", "face_body", "clothes_only", "timings_ms")}})
        total_seconds = time.perf_counter() - started
    except ApiError as error:
        print("Could not run the example:", error)
        return 2

    width = max(len(r["id"]) for r in results)
    for r in results:
        print(f"{r['id']:<{width}}  right answer: {r['expect']['kind'].upper():<8} {r['title']}")
        print(f"{'':<{width}}    face + body : {describe(r['face_body'])}")
        print(f"{'':<{width}}    clothes only: {describe(r['clothes_only'])}")

    def line(label: str, column: str, predicate) -> dict:
        good, total = count(results, column, predicate)
        return {"label": label, "column": column, "right": good, "total": total}

    questions = [
        ("Known people recognised", lambda r: r["expect"]["kind"] == "match"),
        ("Strangers refused", lambda r: r["expect"]["kind"] == "unknown"),
        ("Strangers in the same clothes refused", lambda r: r["group"] == LOOKALIKE_GROUP),
        ("Known people with no usable face sent to a person", lambda r: r["expect"]["kind"] == "review"),
        ("All photos", lambda r: True),
    ]
    summary = [line(q, col, pred) for q, pred in questions for col in ("face_body", "clothes_only")]
    print("\n                                                      face + body   clothes only")
    for q, _ in questions:
        a = next(s for s in summary if s["label"] == q and s["column"] == "face_body")
        b = next(s for s in summary if s["label"] == q and s["column"] == "clothes_only")
        print(f"{q:<54}{a['right']:>3} of {a['total']:<8}{b['right']:>3} of {b['total']}")

    wrong = [r["id"] for r in results if r["face_body"]["verdict"] != "correct"]
    print(f"\nFace + body: {len(results) - len(wrong)} of {len(results)} photos decided exactly right"
          + (f"; NOT right: {', '.join(wrong)}" if wrong else "") + f".   (whole run {total_seconds:.1f} s)")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "what": "The built-in open-set example (GET /api/demo, POST /api/demo/prepare, POST /api/demo/cases/{id}) run against a live server.",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "server": args.base_url, "seconds": round(total_seconds, 1),
        "caveat": info["disclaimer"], "rules": rules, "summary": summary, "cases": results,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print("Saved", out)
    return 0 if not wrong else 1


if __name__ == "__main__":
    raise SystemExit(main())
