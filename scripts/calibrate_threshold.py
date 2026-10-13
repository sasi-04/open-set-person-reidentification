"""
Choose the acceptance threshold on the CALIBRATION split (the test split is never read).

In plain words: the same workflow as the "Calibrate threshold" button in the Evaluation Lab, from the
command line. You say what to hold fixed ("keep 90% of enrolled people accepted and correct" or "never
let more than 1% of strangers in"), and it searches the calibration people for the threshold - and
optionally a margin rule - that does best. If the target cannot be met it SAYS SO and refuses to call
the result calibrated.

    python scripts/calibrate_threshold.py --dataset market1501 --mode fixed_recall --target-recall 0.90
    python scripts/calibrate_threshold.py --dataset market1501 --mode fixed_far --target-far 0.01 --max-identities 150

The result is written to backend/data/reports/. To make it live: open "Model & Thresholds" and press
"Apply this calibration" (it checks that the model matches), or run the same calibration from the
Evaluation Lab, which stores it in the database.
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
from app.evaluation.calibration import OperatingTarget  # noqa: E402
from app.evaluation.datasets import find_dataset  # noqa: E402
from app.evaluation.protocol import ProtocolConfig  # noqa: E402
from app.evaluation.report import render_markdown  # noqa: E402
from app.evaluation.runner import CalibrationRequest, make_extractor_factory, run_calibration  # noqa: E402


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--mode", choices=["fixed_recall", "fixed_far"], default="fixed_recall")
    parser.add_argument("--target-recall", type=float, default=0.90)
    parser.add_argument("--target-far", type=float, default=0.01)
    parser.add_argument("--recall-metric", choices=["dir1", "tar"], default="dir1")
    parser.add_argument("--no-margin", action="store_true", help="do not search for a top-1/top-2 margin rule")
    parser.add_argument("--gallery-shots", type=int, default=3)
    parser.add_argument("--max-identities", type=int, default=None)
    parser.add_argument("--max-images", type=int, default=12)
    parser.add_argument("--dev-fraction", type=float, default=0.4)
    parser.add_argument("--calibration-fraction", type=float, default=0.2)
    parser.add_argument("--out-dir", type=Path, default=settings.report_dir)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    info = find_dataset(settings.datasets_dir, args.dataset)
    if info is None or not info.available:
        print(f"Dataset '{args.dataset}' not found or unusable in {settings.datasets_dir}.", file=sys.stderr)
        return 2

    request = CalibrationRequest(
        dataset=info.name, seed=args.seed, use_margin=not args.no_margin,
        use_flip_tta=settings.use_flip_tta, checkpoint=settings.embedding_checkpoint,  # must match the LIVE model
        target=OperatingTarget(args.mode, args.target_recall, args.target_far, args.recall_metric),
        protocol=ProtocolConfig(seed=args.seed, dev_fraction=args.dev_fraction, calibration_fraction=args.calibration_fraction,
                                gallery_shots=args.gallery_shots, max_identities_per_split=args.max_identities,
                                max_images_per_identity=args.max_images),
    )
    device = resolve_device(settings.device)
    factory = make_extractor_factory(settings.embedding_model, settings.weights_dir, device, settings.embedding_batch_size, settings.fold_batch_norm)
    settings.ensure_directories()

    last = {"text": ""}

    def progress(stage: str, fraction: float) -> None:
        text = f"[{fraction:5.1%}] {stage}"
        if text != last["text"]:
            print(text, flush=True)
            last["text"] = text

    result = run_calibration(info, request, cache_dir=settings.cache_dir, make_extractor=factory, progress=progress)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_{info.name}_calibration.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    path.with_suffix(".md").write_text(render_markdown(result), encoding="utf-8")

    chosen = result["selected"]
    print("\n" + ("TARGET REACHED" if chosen["target_achieved"] else "TARGET NOT REACHED") + f" on the calibration split ({result['metadata']['operating_target']})")
    print(f"  accept threshold : {chosen['threshold']:.4f}")
    print(f"  minimum margin   : {'none' if chosen['min_margin'] is None else format(chosen['min_margin'], '.4f')}")
    print(f"  calibration FAR  : {chosen['calibration']['far']:.2%}  (95% upper bound {chosen['far_upper_bound_95']:.2%}; {chosen['n_unknown']} strangers)")
    for note in chosen["notes"] + result["warnings"]:
        print(f"  note: {note}")
    print(f"\nSaved {path}")
    return 0 if chosen["target_achieved"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
