"""
Finding and reading evaluation datasets.

In plain words: benchmark datasets are NOT part of this repository (they are
licensed for research and must not be redistributed). You download one
yourself and drop it in the ``datasets/`` folder; this module notices it.

Two folder layouts are understood:

  market1501   the official Market-1501 layout
               (bounding_box_train/, bounding_box_test/, query/ ; file names like
                0002_c1s1_000451_03.jpg  = person 0002, camera 1, sequence 1 ...)
  folder       <dataset>/<person_id>/<image>.jpg   (camera read from "c3" in the
               file name if present - useful for your own authorised data)

An optional ``dataset.json`` next to the images can set ``name``, ``kind``
("benchmark" or "smoke_test"), ``description`` and ``license``. The synthetic
smoke-test set we generate for plumbing checks is marked ``smoke_test`` so it
can never be mistaken for a benchmark in the UI or reports.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
_MARKET_NAME = re.compile(r"^(-?\d+)_c(\d+)s(\d+)_(\d+)_(\d+)")
_CAMERA_IN_NAME = re.compile(r"c(\d+)", re.IGNORECASE)

MARKET_NOTE = (
    "Market-1501 (Zheng et al., ICCV 2015) is released for non-commercial research. "
    "Do not redistribute it; cite the paper when you publish results."
)


@dataclass(frozen=True)
class ImageRecord:
    path: Path
    identity: str
    camera: int | None  # None when the dataset does not tell us


@dataclass
class DatasetInfo:
    name: str
    root: Path
    layout: str  # "market1501" | "folder"
    kind: str = "benchmark"  # "benchmark" | "smoke_test"
    description: str = ""
    license_note: str = ""
    n_identities: int = 0
    n_images: int = 0
    n_cameras: int = 0
    available: bool = True
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "layout": self.layout,
            "kind": self.kind,
            "description": self.description,
            "license_note": self.license_note,
            "identities": self.n_identities,
            "images": self.n_images,
            "cameras": self.n_cameras,
            "available": self.available,
            "problems": self.problems,
        }


# ----------------------------------------------------------------------------
# Reading
# ----------------------------------------------------------------------------


def _images_in(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def _find_market_root(root: Path) -> Path | None:
    for candidate in (root, *[p for p in root.iterdir() if p.is_dir()]):
        if (candidate / "bounding_box_test").is_dir() and (candidate / "query").is_dir():
            return candidate
    return None


def _read_market(root: Path) -> list[ImageRecord]:
    """Pool train + gallery + query images. Junk (-1) and distractor (0000) files are dropped."""
    records = []
    for sub in ("bounding_box_train", "bounding_box_test", "query"):
        folder = root / sub
        if not folder.is_dir():
            continue
        for path in _images_in(folder):
            match = _MARKET_NAME.match(path.name)
            if not match:
                continue
            person, camera = int(match.group(1)), int(match.group(2))
            if person <= 0:
                continue
            records.append(ImageRecord(path, f"{person:04d}", camera))
    # The same file can appear in both gallery and query folders only by naming accident; dedupe by name.
    unique = {record.path.name: record for record in records}
    return sorted(unique.values(), key=lambda r: (r.identity, r.path.name))


def _read_folder(root: Path) -> list[ImageRecord]:
    records = []
    for person_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for path in _images_in(person_dir):
            camera_match = _CAMERA_IN_NAME.search(path.stem)
            records.append(ImageRecord(path, person_dir.name, int(camera_match.group(1)) if camera_match else None))
    return records


def _read_manifest(root: Path) -> dict:
    manifest = root / "dataset.json"
    if manifest.is_file():
        try:
            return json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Ignoring unreadable manifest %s", manifest)
    return {}


def load_records(info: DatasetInfo) -> list[ImageRecord]:
    if info.layout == "market1501":
        market_root = _find_market_root(info.root)
        return _read_market(market_root) if market_root else []
    return _read_folder(info.root)


# ----------------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------------


def inspect_dataset(root: Path) -> DatasetInfo:
    manifest = _read_manifest(root)
    market_root = _find_market_root(root)
    layout = "market1501" if market_root else "folder"
    info = DatasetInfo(
        name=str(manifest.get("name") or root.name),
        root=root,
        layout=layout,
        kind=str(manifest.get("kind") or "benchmark"),
        description=str(manifest.get("description") or ""),
        license_note=str(manifest.get("license") or (MARKET_NOTE if layout == "market1501" else "")),
    )
    try:
        records = load_records(info)
    except OSError as exc:
        info.available, info.problems = False, [f"Could not read the folder: {exc}"]
        return info

    info.n_images = len(records)
    info.n_identities = len({r.identity for r in records})
    info.n_cameras = len({r.camera for r in records if r.camera is not None})
    if info.n_identities < 10:
        info.available = False
        info.problems.append(
            f"Only {info.n_identities} identities with images were found; at least 10 are needed to build splits."
        )
    return info


def discover_datasets(datasets_dir: Path) -> list[DatasetInfo]:
    """Every sub-folder of ``datasets/`` is a candidate dataset."""
    if not datasets_dir.is_dir():
        return []
    found = []
    for folder in sorted(p for p in datasets_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
        found.append(inspect_dataset(folder))
    return found


def find_dataset(datasets_dir: Path, name: str) -> DatasetInfo | None:
    for info in discover_datasets(datasets_dir):
        if info.name == name or info.root.name == name:
            return info
    return None
