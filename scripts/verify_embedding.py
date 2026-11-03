"""
Check that an embedding model genuinely separates people - before trusting it with anything else.

In plain words: a network can load without errors, output 512 finite numbers of unit length and still be useless for telling
people apart. This script measures the one thing that matters: on real photos of people taken by different cameras, is the nearest
gallery picture the SAME person? It uses the project's own preprocessing and the models listed in the registry.

Protocol (closed set, deliberately simple): N random Market-1501 identities; one query image each; a gallery of up to K images of the
same identity taken by OTHER cameras; cosine similarity; report Rank-1 and mAP. Chance level is 1/N.

    python scripts/verify_embedding.py --dataset market1501                       # the configured model
    python scripts/verify_embedding.py --dataset market1501 --model osnet_ain_x1_0   # the weights that FAILED (see docs/MODEL_VERIFICATION.md)

Exit code 0 = Rank-1 at or above --min-rank1 (default 0.5), 1 = below it.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
import time
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.cv.embedding.extractor import OSNetExtractor  # noqa: E402
from app.cv.embedding.registry import EMBEDDING_MODELS, get_spec  # noqa: E402
from app.cv.imaging import load_rgb_file  # noqa: E402

NAME = re.compile(r"^(-?\d+)_c(\d)")


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", default="market1501")
    parser.add_argument("--model", default=settings.embedding_model, choices=sorted(EMBEDDING_MODELS))
    parser.add_argument("--identities", type=int, default=100)
    parser.add_argument("--gallery-per-identity", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--min-rank1", type=float, default=0.5)
    args = parser.parse_args()

    root = REPO_ROOT / "datasets" / args.dataset / "bounding_box_test"
    if not root.is_dir():
        print(f"{root} not found - see datasets/README.md")
        return 2
    by_id: dict[str, list[tuple[int, Path]]] = {}
    for path in sorted(root.glob("*.jpg")):
        match = NAME.match(path.name)
        if match and int(match.group(1)) > 0:
            by_id.setdefault(match.group(1), []).append((int(match.group(2)), path))
    rng = random.Random(args.seed)
    eligible = sorted(i for i, items in by_id.items() if len({c for c, _ in items}) >= 2 and len(items) >= args.gallery_per_identity + 1)
    ids = rng.sample(eligible, min(args.identities, len(eligible)))

    queries, gallery = [], []
    for identity in ids:
        camera, path = rng.choice(by_id[identity])
        queries.append((identity, path))
        others = [item for item in by_id[identity] if item[0] != camera]
        gallery += [(identity, p) for _, p in rng.sample(others, min(args.gallery_per_identity, len(others)))]

    spec = get_spec(args.model)
    if not spec.verified:
        print(f"NOTE: {spec.display_name} is flagged unverified in the registry: {spec.verification_note}\n")
    extractor = OSNetExtractor.load(spec, settings.weights_dir, torch.device("cpu"), batch_size=32)

    started = time.perf_counter()
    q = extractor.embed([load_rgb_file(p) for _, p in queries])
    g = extractor.embed([load_rgb_file(p) for _, p in gallery])
    similarity = q @ g.T
    gallery_ids = np.array([identity for identity, _ in gallery])
    hits, precisions = 0, []
    for row, (identity, _) in enumerate(queries):
        relevant = gallery_ids[np.argsort(-similarity[row])] == identity
        hits += int(relevant[0])
        cumulative = np.cumsum(relevant)
        precisions.append(float(np.sum(cumulative / (np.arange(len(relevant)) + 1) * relevant) / max(relevant.sum(), 1)))
    rank1, mean_ap = hits / len(queries), float(np.mean(precisions))

    print(f"model {spec.display_name} ({spec.name}), weights {extractor.weights_label}")
    print(f"{len(queries)} queries, {len(gallery)} gallery images, cross-camera, closed set (chance Rank-1 = {1 / len(queries):.1%})")
    print(f"Rank-1 {rank1:.1%}   mAP {mean_ap:.1%}   ({time.perf_counter() - started:.0f} s)")
    return 0 if rank1 >= args.min_rank1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
