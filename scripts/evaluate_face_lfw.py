"""
Measure the FACE stage on the standard LFW verification benchmark.

In plain words: "Labeled Faces in the Wild" ships a list of 6,000 picture pairs - 3,000 show the same person, 3,000
show two different people - split into 10 folds. For every pair this runs the SAME face code the application
uses (YuNet finds the face, SFace fingerprints it), scores the pair by cosine similarity and reports

  * accuracy with the standard 10-fold protocol (the threshold is chosen on 9 folds and tested on the 10th),
  * what happens at the threshold the application ships with (genuine pairs accepted, impostor pairs wrongly accepted),
  * how many pictures had no face found, and the spread of the face-quality measurements.

Why this matters: it is a real, repeatable number for the face component, so nobody has to take "99 %" on trust.
Why it is not enough: LFW is an easy benchmark of mostly frontal, well-lit news photographs of public figures. It says
nothing about phone-camera selfies in poor light, masks, CCTV distance, twins or deliberate attacks. See
docs/FACE_AND_BODY_MATCHING.md.

Get the data (research use only; never bundled with this project):
    pair list : https://ndownloader.figshare.com/files/5976006   (pairs.txt)
    pictures  : https://ndownloader.figshare.com/files/5976018   (lfw.tgz, 173 MB, sha256 055f7d9c...d536c0)
Extract so that   <folder>/lfw/<Person_Name>/<Person_Name>_0001.jpg   exists, then:

    python scripts/evaluate_face_lfw.py --folder D:\\data\\lfw --out docs/results/face_lfw.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.cv.face.engine import FaceEngine  # noqa: E402

SHIPPED_THRESHOLD = 0.363  # the cosine threshold the OpenCV SFace model card recommends; also the application's default


def read_pairs(path: Path) -> list[list[tuple[str, int, str, int, int]]]:
    """Folds of (name_a, index_a, name_b, index_b, same) - the standard LFW 'pairs.txt' layout."""
    lines = [line.split() for line in path.read_text().splitlines() if line.strip()]
    folds, per_fold = int(lines[0][0]), int(lines[0][1])
    body, result = lines[1:], []
    for fold in range(folds):
        chunk = body[fold * 2 * per_fold : (fold + 1) * 2 * per_fold]
        rows = [(r[0], int(r[1]), r[0], int(r[2]), 1) for r in chunk[:per_fold]]
        rows += [(r[0], int(r[1]), r[2], int(r[3]), 0) for r in chunk[per_fold:]]
        result.append(rows)
    return result


def picture(folder: Path, name: str, index: int) -> Path:
    return folder / "lfw" / name / f"{name}_{index:04d}.jpg"


def best_threshold(scores: np.ndarray, same: np.ndarray) -> float:
    """The cut-off that classifies the most training pairs correctly."""
    candidates = np.unique(np.round(scores, 3))
    accuracy = [((scores >= t) == same).mean() for t in candidates]
    return float(candidates[int(np.argmax(accuracy))])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--folder", required=True, type=Path, help="folder that contains pairs.txt and lfw/")
    parser.add_argument("--out", type=Path, default=None, help="write the measurements as JSON")
    parser.add_argument("--limit-folds", type=int, default=10, help="use only the first N folds (quick check)")
    parser.add_argument("--tail-people", type=int, default=3000,
                        help="also compare this many DIFFERENT people with each other (every pair is a stranger pair) to measure the "
                             "rare high-scoring tail that decides the safe threshold; 0 = skip")
    args = parser.parse_args()

    engine = FaceEngine.load(get_settings().weights_dir)
    folds = read_pairs(args.folder / "pairs.txt")[: args.limit_folds]

    wanted = sorted({(n, i) for fold in folds for a, b, c, d, _ in fold for n, i in ((a, b), (c, d))})
    print(f"{len(wanted)} different pictures in {sum(len(f) for f in folds)} pairs; computing face fingerprints ...")
    embedding: dict[tuple[str, int], np.ndarray | None] = {}
    quality_rows, started = [], time.perf_counter()
    for count, (name, index) in enumerate(wanted, 1):
        bgr = cv2.imread(str(picture(args.folder, name, index)))
        reading = None if bgr is None else engine.read_best(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        embedding[(name, index)] = None if reading is None else reading.embedding
        if reading is not None:
            quality_rows.append({**reading.quality.metrics, "usable": reading.quality.usable, "flags": reading.quality.flags})
        if count % 500 == 0:
            print(f"  {count}/{len(wanted)}  ({(time.perf_counter() - started) / count * 1000:.0f} ms per picture)", flush=True)
    per_picture_ms = (time.perf_counter() - started) / len(wanted) * 1000

    no_face = sum(v is None for v in embedding.values())
    scored = []  # per fold: (scores, same)
    pairs_without_face = 0
    for fold in folds:
        scores, same = [], []
        for na, ia, nb, ib, is_same in fold:
            a, b = embedding[(na, ia)], embedding[(nb, ib)]
            if a is None or b is None:
                pairs_without_face += 1
                scores.append(-1.0)  # a missing face can never support a match
            else:
                scores.append(float(a @ b))
            same.append(is_same)
        scored.append((np.array(scores), np.array(same, dtype=bool)))

    fold_accuracy = []
    for held_out in range(len(scored) if len(scored) > 1 else 0):  # needs at least two folds (one to choose on, one to test on)
        train_scores = np.concatenate([s for k, (s, _) in enumerate(scored) if k != held_out])
        train_same = np.concatenate([y for k, (_, y) in enumerate(scored) if k != held_out])
        threshold = best_threshold(train_scores, train_same)
        test_scores, test_same = scored[held_out]
        fold_accuracy.append(float(((test_scores >= threshold) == test_same).mean()))

    all_scores = np.concatenate([s for s, _ in scored])
    all_same = np.concatenate([y for _, y in scored])
    genuine, impostor = all_scores[all_same], all_scores[~all_same]
    at_shipped = {
        "threshold": SHIPPED_THRESHOLD,
        "same_person_pairs_accepted": float((genuine >= SHIPPED_THRESHOLD).mean()),
        "different_people_pairs_wrongly_accepted": float((impostor >= SHIPPED_THRESHOLD).mean()),
        "accuracy": float(((all_scores >= SHIPPED_THRESHOLD) == all_same).mean()),
    }
    operating_points = {}
    for far in (1e-2, 1e-3):
        threshold = float(np.quantile(impostor, 1 - far))
        operating_points[f"threshold_for_FAR_{far:g}"] = {
            "threshold": round(threshold, 3), "same_person_pairs_accepted": float((genuine >= threshold).mean())
        }

    # ---- the stranger tail: one picture each of many different people, every pair compared (3,000 people = 4.5 million pairs)
    tail_report = None
    if args.tail_people > 0:
        import random

        rng = random.Random(0)
        root = args.folder / "lfw"
        names = sorted(d.name for d in root.iterdir() if d.is_dir())
        picked = rng.sample(names, min(args.tail_people, len(names)))
        print(f"stranger tail: {len(picked)} different people, one picture each ...")
        vectors = []
        for name in picked:
            image = sorted((root / name).glob("*.jpg"))[0]
            bgr = cv2.imread(str(image))
            reading = None if bgr is None else engine.read_best(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            if reading is not None and reading.embedding is not None:
                vectors.append(reading.embedding)
        matrix = np.stack(vectors)
        similarity = matrix @ matrix.T
        stranger_scores = similarity[np.triu_indices(len(matrix), k=1)]
        pairs_total = int(stranger_scores.size)
        tail_report = {
            "different_people": len(matrix), "stranger_pairs": pairs_total,
            "highest_stranger_score": float(stranger_scores.max()),
            "threshold_for_false_accept_rate": {
                f"{rate:g}": {"threshold": round(float(np.quantile(stranger_scores, 1 - rate)), 3),
                              "same_person_pairs_accepted_at_that_threshold": float((genuine >= np.quantile(stranger_scores, 1 - rate)).mean())}
                for rate in (1e-4, 1e-5, 1e-6)},
            "stranger_pairs_at_or_above": {str(t): int((stranger_scores >= t).sum()) for t in (0.363, 0.40, 0.45, 0.50)},
            "same_person_pairs_accepted_at": {str(t): float((genuine >= t).mean()) for t in (0.363, 0.40, 0.45, 0.50)},
        }

    sharp = np.array([q["sharpness"] for q in quality_rows if "sharpness" in q])
    face_px = np.array([q["face_px"] for q in quality_rows])
    flag_counts: dict[str, int] = {}
    for q in quality_rows:
        for flag in q["flags"]:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1
    report = {
        "dataset": "LFW (Labeled Faces in the Wild), standard 10-fold 'pairs.txt' protocol",
        "pairs": int(len(all_scores)), "folds": len(scored), "pictures": len(wanted),
        "pictures_without_a_face_found": int(no_face), "pairs_affected_by_a_missing_face": int(pairs_without_face),
        "ten_fold_accuracy_mean": float(np.mean(fold_accuracy)) if fold_accuracy else None,
        "ten_fold_accuracy_std": float(np.std(fold_accuracy)) if fold_accuracy else None,
        "at_model_card_threshold": at_shipped, "operating_points": operating_points, "stranger_tail": tail_report,
        "score_distribution": {
            "same_person_median": float(np.median(genuine)), "same_person_p5": float(np.quantile(genuine, 0.05)),
            "different_people_median": float(np.median(impostor)), "different_people_p99": float(np.quantile(impostor, 0.99)),
            "different_people_max": float(impostor.max()),
        },
        "face_quality_measurements": {
            "face_px_p5_median": [float(np.quantile(face_px, 0.05)), float(np.median(face_px))],
            "sharpness_p1_p5_median": [float(np.quantile(sharp, 0.01)), float(np.quantile(sharp, 0.05)), float(np.median(sharp))],
            "flags": flag_counts,
        },
        "speed": {"ms_per_picture_detect_and_embed": round(per_picture_ms, 1)},
        "caveats": [
            "LFW is easy: mostly frontal, well lit photographs of public figures. Phone selfies in poor light, masks, CCTV "
            "distance, twins and deliberate attacks are NOT represented.",
            "The threshold was NOT tuned on these pairs; it is the OpenCV model-card default. A deployment must calibrate its own "
            "threshold on its own camera data.",
        ],
    }
    print(json.dumps(report, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
