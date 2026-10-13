"""
Run the full open-set evaluation from the command line.

In plain words: the same experiment the "Evaluation Lab" screen launches, but
with progress printed to the terminal and the result saved as JSON (plus a
readable Markdown report). Examples:

    # Quick smoke test on the synthetic dataset (verifies the pipeline only!)
    python scripts/run_evaluation.py --dataset smoke_synthetic --seeds 0 1 2

    # Real benchmark, "keep 90% of enrolled people, minimise false accepts"
    python scripts/run_evaluation.py --dataset market1501 --mode fixed_recall --target-recall 0.90 \\
        --seeds 0 1 2 --max-identities 150

    # Or: "never let more than 1% of strangers in, keep as many enrolled people as possible"
    python scripts/run_evaluation.py --dataset market1501 --mode fixed_far --target-far 0.01

Results are written to backend/data/reports/<timestamp>_<dataset>.json / .md
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.device import resolve_device  # noqa: E402
from app.evaluation.ablation import DEFAULT_VARIANT_KEYS, VARIANT_BY_KEY  # noqa: E402
from app.evaluation.calibration import OperatingTarget  # noqa: E402
from app.evaluation.datasets import find_dataset  # noqa: E402
from app.evaluation.protocol import ProtocolConfig  # noqa: E402
from app.evaluation.report import render_markdown  # noqa: E402
from app.evaluation.runner import EvaluationRequest, make_extractor_factory, run_evaluation  # noqa: E402


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True, help="folder name inside datasets/")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0])
    parser.add_argument("--mode", choices=["fixed_recall", "fixed_far"], default="fixed_recall")
    parser.add_argument("--target-recall", type=float, default=0.90)
    parser.add_argument("--target-far", type=float, default=0.01)
    parser.add_argument("--recall-metric", choices=["dir1", "tar"], default="dir1")
    parser.add_argument("--variants", nargs="+", default=list(DEFAULT_VARIANT_KEYS), choices=sorted(VARIANT_BY_KEY))
    parser.add_argument("--finetuned-checkpoint", type=Path, default=None)
    parser.add_argument("--gallery-shots", type=int, default=3)
    parser.add_argument("--max-identities", type=int, default=None, help="cap people per split (CPU-friendly)")
    parser.add_argument("--max-images", type=int, default=12, help="cap images per person")
    parser.add_argument("--dev-fraction", type=float, default=0.4)
    parser.add_argument("--calibration-fraction", type=float, default=0.2)
    parser.add_argument("--no-cross-camera", action="store_true")
    parser.add_argument("--bootstrap", type=int, default=settings.evaluation_bootstrap_samples)
    parser.add_argument("--out-dir", type=Path, default=settings.report_dir)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    info = find_dataset(settings.datasets_dir, args.dataset)
    if info is None or not info.available:
        print(f"Dataset '{args.dataset}' not found or unusable in {settings.datasets_dir}.", file=sys.stderr)
        if info:
            print("\n".join(info.problems), file=sys.stderr)
        return 2

    request = EvaluationRequest(
        dataset=info.name,
        seeds=tuple(args.seeds),
        target=OperatingTarget(args.mode, args.target_recall, args.target_far, args.recall_metric),
        variants=tuple(args.variants),
        protocol=ProtocolConfig(
            dev_fraction=args.dev_fraction, calibration_fraction=args.calibration_fraction,
            gallery_shots=args.gallery_shots, max_identities_per_split=args.max_identities,
            max_images_per_identity=args.max_images, cross_camera=not args.no_cross_camera),
        bootstrap_samples=args.bootstrap,
        finetuned_checkpoint=args.finetuned_checkpoint,
    )

    device = resolve_device(settings.device)
    factory = make_extractor_factory(
        settings.embedding_model, settings.weights_dir, device, settings.embedding_batch_size, settings.fold_batch_norm
    )

    last = {"stage": ""}

    def progress(stage: str, fraction: float) -> None:
        text = f"[{fraction:5.1%}] {stage}"
        if text != last["stage"]:
            print(text, flush=True)
            last["stage"] = text

    settings.ensure_directories()
    started = time.time()
    result = run_evaluation(info, request, cache_dir=settings.cache_dir, make_extractor=factory, progress=progress)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = args.out_dir / f"{stamp}_{info.name}.json"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    md_path = json_path.with_suffix(".md")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    print(f"\nFinished in {time.time() - started:.0f}s\n  JSON    : {json_path}\n  Markdown: {md_path}")
    for warning in result["warnings"]:
        print(f"  WARNING : {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
