"""
Fine-tune the backbone with batch-hard triplet loss (metric learning + hard-negative mining).

In plain words: trains ONLY on the "development" people of a dataset - the people set aside by the
evaluation protocol so they never overlap with the calibration or test people - and saves a
checkpoint that remembers who it trained on. Nothing is claimed about improvement: you then run the
evaluation, which scores the checkpoint on held-out people (and refuses it if there is any overlap).

IMPORTANT: use the SAME protocol options here and in run_evaluation.py (seed, fractions), so the
development people are the same ones the evaluation holds out.

    python scripts/finetune_triplet.py --dataset market1501 --seed 0 --epochs 3 \\
        --out backend/weights/finetuned/market_seed0.pt

    python scripts/run_evaluation.py --dataset market1501 --seeds 0 \\
        --finetuned-checkpoint backend/weights/finetuned/market_seed0.pt \\
        --variants thr thr_margin thr_margin_finetuned

CPU time: the default trains only the last stage; expect a few minutes per epoch on a laptop.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.cv.embedding.registry import get_spec  # noqa: E402
from app.evaluation.datasets import find_dataset, load_records  # noqa: E402
from app.evaluation.protocol import ProtocolConfig, build_protocol  # noqa: E402
from app.training.finetune import FineTuneConfig, finetune  # noqa: E402


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--seed", type=int, default=0, help="the protocol seed (must match the evaluation)")
    parser.add_argument("--dev-fraction", type=float, default=0.4)
    parser.add_argument("--calibration-fraction", type=float, default=0.2)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batches-per-epoch", type=int, default=40)
    parser.add_argument("--people-per-batch", type=int, default=8)
    parser.add_argument("--photos-per-person", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--margin", type=float, default=0.3)
    parser.add_argument("--trainable", choices=["head", "all"], default="head")
    parser.add_argument("--max-identities", type=int, default=None, help="cap development people (speed)")
    parser.add_argument("--max-images", type=int, default=20)
    parser.add_argument("--out", type=Path, default=settings.weights_dir / "finetuned" / "finetuned.pt")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    info = find_dataset(settings.datasets_dir, args.dataset)
    if info is None or not info.available:
        print(f"Dataset '{args.dataset}' not found or unusable in {settings.datasets_dir}.", file=sys.stderr)
        return 2

    records = load_records(info)
    protocol_config = ProtocolConfig(seed=args.seed, dev_fraction=args.dev_fraction, calibration_fraction=args.calibration_fraction)
    protocol = build_protocol(records, protocol_config)  # only used to learn WHO the development people are
    print(f"Development people (never in calibration/test for seed {args.seed}): {len(protocol.dev_ids)}")

    config = FineTuneConfig(
        dataset=info.name, seed=args.seed, epochs=args.epochs, batches_per_epoch=args.batches_per_epoch,
        people_per_batch=args.people_per_batch, photos_per_person=args.photos_per_person, learning_rate=args.lr,
        margin=args.margin, trainable=args.trainable, max_identities=args.max_identities,
        max_images_per_identity=args.max_images, protocol=protocol_config.to_dict(),
    )
    meta = finetune(get_spec(settings.embedding_model), settings.weights_dir, records, protocol.dev_ids, config, args.out, progress=print)

    print(f"\nSaved {args.out}\n  trained on {len(meta['dev_identities'])} people / {meta['training_images']} images in {meta['seconds']} s")
    print("  NOT yet validated: this is training loss only. Evaluate it on held-out people:")
    print(f"    python scripts/run_evaluation.py --dataset {info.name} --seeds {args.seed} "
          f"--dev-fraction {args.dev_fraction} --calibration-fraction {args.calibration_fraction} "
          f"--finetuned-checkpoint {args.out} --variants thr thr_margin thr_margin_finetuned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
