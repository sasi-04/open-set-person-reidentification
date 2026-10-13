"""
Finding, verifying and safely loading model weight files.

In plain words: the app NEVER downloads anything by itself while it is
running. Weights are fetched once, on purpose, by ``scripts/download_weights.py``.
This module then makes sure the file on disk is exactly the file we expect
before PyTorch ever reads it:

  1. the file must exist;
  2. its SHA-256 must match the pinned value in the registry (for official weights);
  3. it is opened with ``torch.load(weights_only=True)``, which can only
     produce tensors and plain containers - it cannot run code hidden inside a
     pickle file;
  4. every key must fit the architecture (strict loading).

A fine-tuned checkpoint that you trained yourself has no pinned hash; it is
loaded with the same safe loader and its hash is *reported*, not trusted.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import torch

from ...core.errors import ModelUnavailable
from .registry import EmbeddingModelSpec

logger = logging.getLogger(__name__)


def sha256_of_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def locate_official_weights(spec: EmbeddingModelSpec, weights_dir: Path) -> Path:
    """Return the path of the verified official weight file, or raise a helpful error."""
    path = weights_dir / spec.weights.filename
    if not path.is_file():
        raise ModelUnavailable(
            f"Weights for '{spec.name}' were not found at {path}. "
            "Run:  python scripts/download_weights.py",
            details={"missing_file": str(path)},
        )
    actual = sha256_of_file(path)
    if actual != spec.weights.sha256:
        raise ModelUnavailable(
            f"The weight file {path.name} is corrupted or not the official file "
            f"(SHA-256 mismatch). Delete it and re-run scripts/download_weights.py.",
            details={"expected_sha256": spec.weights.sha256, "actual_sha256": actual},
        )
    return path


def read_checkpoint_metadata(path: Path) -> dict:
    """The ``meta`` record stored beside the weights by our fine-tuning script ({} if there is none).

    Used by the evaluation to see WHICH PEOPLE a fine-tuned checkpoint was trained on.
    """
    try:
        payload = torch.load(path, map_location="cpu", weights_only=True)
    except Exception as exc:
        raise ModelUnavailable(f"Could not read the checkpoint {path.name}: {exc}") from exc
    meta = payload.get("meta") if isinstance(payload, dict) else None
    return meta if isinstance(meta, dict) else {}


def load_state_dict(path: Path) -> dict[str, torch.Tensor]:
    """Read a checkpoint as a plain {name: tensor} dictionary, without executing pickled code."""
    try:
        payload = torch.load(path, map_location="cpu", weights_only=True)
    except Exception as exc:  # torch raises many different types for bad files
        raise ModelUnavailable(
            f"Could not read the checkpoint {path.name}: {exc}. "
            "The file may be corrupted or may not be a plain PyTorch state dict."
        ) from exc

    # Fine-tuned checkpoints written by our trainer wrap the weights: {"state_dict": ..., "meta": ...}
    if isinstance(payload, dict) and "state_dict" in payload:
        payload = payload["state_dict"]
    if not isinstance(payload, dict) or not payload:
        raise ModelUnavailable(f"The checkpoint {path.name} does not contain a state dictionary.")

    # Tolerate checkpoints saved from nn.DataParallel ("module.") and drop any classifier head.
    cleaned = {}
    for key, value in payload.items():
        key = key[len("module.") :] if key.startswith("module.") else key
        if key.startswith("classifier."):
            continue
        cleaned[key] = value
    return cleaned
