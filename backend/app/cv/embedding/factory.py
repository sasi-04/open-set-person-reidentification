"""
Builds the embedding extractor named in the settings.

In plain words: one small function so the rest of the app never needs to know
*which* backbone is in use. To plug in a different backbone family, add a
branch here that returns an object satisfying ``EmbeddingExtractor``.
"""

from __future__ import annotations

import torch

from ...core.config import Settings
from .base import EmbeddingExtractor
from .extractor import OSNetExtractor
from .registry import get_spec


def build_extractor(
    settings: Settings,
    device: torch.device,
    *,
    use_flip_tta: bool | None = None,
    checkpoint=None,
) -> EmbeddingExtractor:
    """``use_flip_tta`` / ``checkpoint`` override the settings (used by the evaluation ablations)."""
    spec = get_spec(settings.embedding_model)
    return OSNetExtractor.load(
        spec,
        settings.weights_dir,
        device,
        checkpoint=checkpoint if checkpoint is not None else settings.embedding_checkpoint,
        batch_size=settings.embedding_batch_size,
        use_flip_tta=settings.use_flip_tta if use_flip_tta is None else use_flip_tta,
        fold_bn=settings.fold_batch_norm,
    )
