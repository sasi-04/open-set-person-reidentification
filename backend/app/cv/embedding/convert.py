"""
One-off conversion of an official Torchreid training checkpoint into a plain, tensors-only weight file.

In plain words: Torchreid publishes weights as ``*.pth.tar`` training checkpoints that also contain the optimiser and
scheduler objects. PyTorch's safe loader (``weights_only=True``, which cannot run code hidden in a pickle) refuses such files.
So this module is used ONCE, by ``scripts/download_weights.py``, and ONLY after the downloaded file's SHA-256 has been matched
to the pinned value: it opens the archive with the unrestricted loader, keeps just the network tensors (dropping the identity
classifier, the optimiser and the scheduler, and the ``module.`` prefix) and saves them as a plain state dict. From then on the
application only ever reads the converted file, with the safe loader and its own pinned hash.
"""

from __future__ import annotations

from pathlib import Path

import torch

from ...core.errors import ModelUnavailable


def convert_torchreid_checkpoint(source: Path, destination: Path) -> int:
    """Write ``destination`` (tensors only) from the verified checkpoint ``source``. Returns the number of tensors kept."""
    try:
        payload = torch.load(source, map_location="cpu", weights_only=False)  # safe ONLY because the caller verified the hash
    except Exception as exc:
        raise ModelUnavailable(f"Could not read the checkpoint {source.name}: {exc}") from exc
    state = payload.get("state_dict") if isinstance(payload, dict) else None
    if not isinstance(state, dict) or not state:
        raise ModelUnavailable(f"{source.name} does not contain a 'state_dict'.")
    kept = {}
    for key, value in state.items():
        key = key[len("module.") :] if key.startswith("module.") else key
        if key.startswith("classifier.") or not isinstance(value, torch.Tensor):
            continue
        kept[key] = value.detach().cpu().contiguous()
    destination.parent.mkdir(parents=True, exist_ok=True)
    torch.save(kept, destination)
    return len(kept)
