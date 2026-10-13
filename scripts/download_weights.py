"""
Download the pretrained model weights - on purpose, once, with verification.

In plain words: the web application never fetches models by itself. Run this
script one time after installing; it downloads

  * the OSNet-AIN person-embedding weights (MIT licence, ~9 MB for x1_0) and
    checks them against a pinned SHA-256 hash, and
  * the torchvision person-detector weights (BSD licence, ~75 MB) and checks
    them against the hash prefix baked into the official file name, and
  * the two face models (YuNet detector, MIT, 0.2 MB; SFace recogniser, Apache-2.0, 37 MB) from the OpenCV model zoo,
    checked against the SHA-256 that the zoo itself publishes in its Git-LFS pointer files,

into ``backend/weights/``. A file that fails its check is deleted, never used.

Usage (from the repository root, with the backend venv active):

    python scripts/download_weights.py                       # default models from .env
    python scripts/download_weights.py --embedding osnet_ain_x0_25
    python scripts/download_weights.py --detector ssdlite320_mobilenet_v3_large
    python scripts/download_weights.py --skip-detector
    python scripts/download_weights.py --skip-face        # body-only system: no face models
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.cv.detection.detector import DETECTORS  # noqa: E402
from app.cv.embedding.registry import EMBEDDING_MODELS  # noqa: E402
from app.cv.face.registry import FACE_MODEL_FILES  # noqa: E402


def download(url: str, destination: Path) -> str:
    """Stream ``url`` to ``destination`` (via a .part file) and return its SHA-256."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": "reid-lab-setup/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(1 << 20):
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done / 2**20:6.1f} / {total / 2**20:.1f} MB", end="", flush=True)
    print()
    partial.replace(destination)
    return digest.hexdigest()


def fetch_embedding_weights(name: str, weights_dir: Path) -> bool:
    spec = EMBEDDING_MODELS[name]
    target = weights_dir / spec.weights.filename
    print(f"[embedding] {spec.display_name}  ({spec.weights.size_bytes / 2**20:.1f} MB)")
    print(f"  source : {spec.weights.url}")
    print(f"  licence: {spec.weights_license}")
    if target.exists():
        existing = hashlib.sha256(target.read_bytes()).hexdigest()
        if existing == spec.weights.sha256:
            print("  already present and verified - skipping.")
            return True
        print("  existing file failed verification - downloading again.")
    actual = download(spec.weights.url, target)
    if actual != spec.weights.sha256:
        target.unlink(missing_ok=True)
        print(f"  !! SHA-256 MISMATCH (got {actual}); file deleted.", file=sys.stderr)
        return False
    print("  verified (SHA-256 matches the pinned value).")
    return True


def fetch_detector_weights(name: str, weights_dir: Path) -> bool:
    spec = DETECTORS[name]
    target = weights_dir / spec.filename
    print(f"[detector] {spec.display_name}")
    print(f"  source : {spec.weights_url}")
    print("  licence: BSD-3-Clause (torchvision); trained on COCO")
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest().startswith(spec.hash_prefix):
        print("  already present and verified - skipping.")
        return True
    actual = download(spec.weights_url, target)
    if not actual.startswith(spec.hash_prefix):
        target.unlink(missing_ok=True)
        print(f"  !! hash prefix mismatch (expected {spec.hash_prefix}, got {actual[:8]}); file deleted.", file=sys.stderr)
        return False
    print(f"  verified (SHA-256 starts with {spec.hash_prefix}, as in the official file name).")
    return True


def fetch_face_weights(weights_dir: Path) -> bool:
    ok = True
    for spec in FACE_MODEL_FILES:
        target = weights_dir / spec.filename
        print(f"[face {spec.role}] {spec.filename}  ({spec.size_bytes / 2**20:.1f} MB)")
        print(f"  source : {spec.url}")
        print(f"  licence: {spec.licence}")
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == spec.sha256:
            print("  already present and verified - skipping.")
            continue
        actual = download(spec.url, target)
        if actual != spec.sha256:
            target.unlink(missing_ok=True)
            print(f"  !! SHA-256 MISMATCH (got {actual}); file deleted.", file=sys.stderr)
            ok = False
            continue
        print("  verified (SHA-256 matches the value published by the OpenCV model zoo).")
    return ok


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--embedding", default=settings.embedding_model, choices=sorted(EMBEDDING_MODELS))
    parser.add_argument("--detector", default=settings.detector_model, choices=sorted(DETECTORS))
    parser.add_argument("--skip-detector", action="store_true", help="do not fetch the person detector")
    parser.add_argument("--skip-face", action="store_true", help="do not fetch the face models (the system then matches on the body only)")
    args = parser.parse_args()

    weights_dir = settings.weights_dir
    ok = fetch_embedding_weights(args.embedding, weights_dir)
    if not args.skip_detector:
        ok = fetch_detector_weights(args.detector, weights_dir) and ok
    if not args.skip_face:
        ok = fetch_face_weights(weights_dir) and ok

    print("\nDone." if ok else "\nFinished with errors - see messages above.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
