"""
Which hardware runs the neural networks?

In plain words: ``auto`` uses the GPU when PyTorch can see one and quietly falls
back to the CPU otherwise. Asking explicitly for ``cuda`` on a machine without
a GPU is a configuration mistake, so that case raises a clear error instead of
silently running slowly.
"""

from __future__ import annotations

import logging

import torch

from .errors import ModelUnavailable

logger = logging.getLogger(__name__)


def resolve_device(preference: str) -> torch.device:
    if preference == "cpu":
        return torch.device("cpu")

    cuda_ok = torch.cuda.is_available()
    if preference == "cuda":
        if not cuda_ok:
            raise ModelUnavailable(
                "REID_DEVICE=cuda was requested but PyTorch cannot see a CUDA GPU. "
                "Use REID_DEVICE=cpu or REID_DEVICE=auto."
            )
        return torch.device("cuda")

    # preference == "auto"
    device = torch.device("cuda" if cuda_ok else "cpu")
    logger.info("Device selected automatically: %s", device)
    return device


def describe_device(device: torch.device) -> dict[str, str | int | None]:
    info: dict[str, str | int | None] = {"type": device.type, "name": "CPU", "torch": torch.__version__}
    if device.type == "cuda":
        info["name"] = torch.cuda.get_device_name(device)
        info["memory_mb"] = int(torch.cuda.get_device_properties(device).total_memory / 2**20)
    return info
