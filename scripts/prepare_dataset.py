"""
Check, unpack and prepare an evaluation dataset.

In plain words: benchmark datasets are not part of this repository (they are licensed for research
and must not be redistributed), so YOU download one and put it in ``datasets/``. This script makes
that step safe and easy:

  inspect   Look at a folder in datasets/ and say, in plain words, whether the evaluation can use it
            (how many people, images, cameras; whether pictures open; what is missing).
  unpack    Safely unpack a downloaded .zip / .tar / .tar.gz into datasets/<name>. It refuses paths that
            try to escape the folder, and refuses to write into a folder that already has files.
  template  Write an empty ``hard_subset.json`` you can fill in by hand to mark genuinely
            "same clothing" queries (used instead of the colour-histogram proxy when present).

Examples (from the repository root, backend venv active):

    python scripts/prepare_dataset.py unpack C:/Downloads/Market-1501-v15.09.15.zip --name market1501
    python scripts/prepare_dataset.py inspect market1501
    python scripts/prepare_dataset.py template market1501

Market-1501 is for NON-COMMERCIAL RESEARCH. Obtain it from its authors (Zheng et al., ICCV 2015) and
cite their paper. Do not re-upload it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tarfile
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.cv.imaging import load_rgb_file  # noqa: E402
from app.evaluation.datasets import find_dataset, inspect_dataset, load_records  # noqa: E402


# ------------------------------------------------------------------------------ inspect
def cmd_inspect(args: argparse.Namespace) -> int:
    settings = get_settings()
    root = Path(args.name) if Path(args.name).is_dir() else settings.datasets_dir / args.name
    if not root.is_dir():
        print(f"There is no folder {root}.\nPut the dataset there (see: python scripts/prepare_dataset.py unpack --help).", file=sys.stderr)
        return 2

    info = inspect_dataset(root)
    records = load_records(info)
    print(f"Dataset      : {info.name}  ({info.layout} layout, {info.kind.replace('_', ' ')})")
    print(f"People       : {info.n_identities}")
    print(f"Images       : {info.n_images}")
    print(f"Cameras      : {info.n_cameras if info.n_cameras else 'not recorded in file names'}")

    if records:
        per_person = np.array(list(Counter(r.identity for r in records).values()))
        print(f"Images/person: min {per_person.min()}, median {int(np.median(per_person))}, max {per_person.max()}")
        usable = int((per_person >= 4).sum())
        print(f"People with >= 4 images (needed: 3 gallery + 1 query by default): {usable}")
        cameras = Counter(r.camera for r in records if r.camera is not None)
        if cameras:
            print("Images/camera:", ", ".join(f"c{c}={n}" for c, n in sorted(cameras.items())))

        rng = np.random.default_rng(0)
        sample = [records[i] for i in rng.choice(len(records), size=min(25, len(records)), replace=False)]
        unreadable = []
        for record in sample:
            try:
                load_rgb_file(record.path)
            except Exception:
                unreadable.append(record.path.name)
        print(f"Random readability check: {len(sample) - len(unreadable)}/{len(sample)} images open correctly"
              + (f"  (unreadable: {unreadable[:3]})" if unreadable else ""))

    problems = list(info.problems)
    if info.layout == "market1501":
        for sub in ("bounding_box_train", "bounding_box_test", "query"):
            if not any(root.rglob(sub)):
                problems.append(f"Expected a '{sub}' folder inside {root}.")
    if (root / "hard_subset.json").is_file():
        print("Same-clothing subset: MANUAL annotation file found (hard_subset.json) - it replaces the colour proxy.")
    else:
        print("Same-clothing subset: none supplied - the colour-histogram proxy will be used (see docs/EVALUATION.md).")

    if problems or not info.available:
        print("\nPROBLEMS:\n  - " + "\n  - ".join(problems or ["The dataset is not usable."]))
        return 1
    print("\nOK - this dataset can be used by the Evaluation Lab and scripts/run_evaluation.py.")
    if info.license_note:
        print(f"Licence note: {info.license_note}")
    return 0


# ------------------------------------------------------------------------------- unpack
def _safe_zip_extract(archive: Path, destination: Path) -> int:
    count = 0
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError(f"Refusing unsafe path inside the archive: {member.filename}")
            count += 1
        bundle.extractall(destination)
    return count


def _safe_tar_extract(archive: Path, destination: Path) -> int:
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        bundle.extractall(destination, filter="data")  # the "data" filter blocks absolute paths, links, device files
    return len(members)


def cmd_unpack(args: argparse.Namespace) -> int:
    archive = Path(args.archive)
    if not archive.is_file():
        print(f"Archive not found: {archive}", file=sys.stderr)
        return 2
    settings = get_settings()
    destination = settings.datasets_dir / args.name
    if destination.exists() and any(destination.iterdir()):
        print(f"{destination} already contains files. Choose another --name or remove it first.", file=sys.stderr)
        return 2
    free = shutil.disk_usage(settings.datasets_dir.anchor or ".").free
    if free < archive.stat().st_size * 4:
        print(f"Not enough free disk space on the datasets drive ({free / 2**30:.1f} GB free; need about "
              f"{archive.stat().st_size * 4 / 2**30:.1f} GB).", file=sys.stderr)
        return 2

    destination.mkdir(parents=True, exist_ok=True)
    print(f"Unpacking {archive.name} into {destination} ...")
    try:
        count = _safe_zip_extract(archive, destination) if zipfile.is_zipfile(archive) else _safe_tar_extract(archive, destination)
    except (tarfile.TarError, zipfile.BadZipFile, OSError, ValueError) as exc:
        shutil.rmtree(destination, ignore_errors=True)  # leave nothing half-unpacked behind
        print(f"Could not unpack the archive: {exc}", file=sys.stderr)
        return 1
    print(f"Unpacked {count} entries. Checking the result:\n")
    return cmd_inspect(argparse.Namespace(name=args.name))


# ------------------------------------------------------------------------------ template
def cmd_template(args: argparse.Namespace) -> int:
    settings = get_settings()
    info = find_dataset(settings.datasets_dir, args.name)
    if info is None:
        print(f"Dataset '{args.name}' not found in {settings.datasets_dir}.", file=sys.stderr)
        return 2
    target = info.root / "hard_subset.json"
    if target.exists():
        print(f"{target} already exists; not overwriting.", file=sys.stderr)
        return 2
    target.write_text(json.dumps({
        "_instructions": "List query images (paths relative to this folder) in which the person wears clothing "
                         "similar to ANOTHER enrolled person. Only 'hard_queries' is read; this field is ignored.",
        "hard_queries": [],
    }, indent=2), encoding="utf-8")
    print(f"Wrote {target}. Fill in 'hard_queries' with relative image paths, e.g. \"bounding_box_test/0002_c1s1_000451_03.jpg\".")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect", help="validate a dataset folder")
    inspect.add_argument("name", help="folder name inside datasets/ (or a full path)")
    inspect.set_defaults(func=cmd_inspect)

    unpack = sub.add_parser("unpack", help="safely unpack a downloaded archive")
    unpack.add_argument("archive", help=".zip / .tar / .tar.gz file")
    unpack.add_argument("--name", default="market1501", help="target folder name inside datasets/")
    unpack.set_defaults(func=cmd_unpack)

    template = sub.add_parser("template", help="create an empty hard_subset.json to annotate by hand")
    template.add_argument("name")
    template.set_defaults(func=cmd_template)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
