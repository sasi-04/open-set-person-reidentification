"""
The OSNet embedding extractor.

In plain words: this class owns the loaded neural network. It is created ONCE
when the server starts (loading weights is slow), put into evaluation mode,
and then reused for every request. For each batch of person crops it:

  1. resizes + normalises the pixels the way the network was trained;
  2. runs the network with gradients switched off (``torch.inference_mode``);
  3. optionally averages the result with the embedding of the mirrored crop
     (flip test-time augmentation - a cheap trick that usually helps ReID);
  4. L2-normalises, so every embedding has length 1 and a plain dot product
     equals cosine similarity;
  5. refuses to return anything that is not finite or not the right size.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
import torch
from torch.nn import functional as F

from ...core.errors import ModelUnavailable, ProcessingFailed
from .optimize import fold_batch_norm
from .osnet_ain import OSNetAIN
from .registry import EmbeddingModelSpec
from .weights import load_state_dict, locate_official_weights, sha256_of_file

logger = logging.getLogger(__name__)


class OSNetExtractor:
    def __init__(
        self,
        spec: EmbeddingModelSpec,
        model: OSNetAIN,
        device: torch.device,
        *,
        batch_size: int,
        use_flip_tta: bool,
        weights_label: str,
        weights_sha256: str,
        custom_checkpoint: bool,
        load_seconds: float,
        optimisations: tuple[str, ...] = (),
    ) -> None:
        self.spec = spec
        self.name = spec.name
        self.dim = spec.feature_dim
        self.device = device
        self.batch_size = batch_size
        self.use_flip_tta = use_flip_tta
        self.weights_label = weights_label
        self.weights_sha256 = weights_sha256
        self.custom_checkpoint = custom_checkpoint
        self.load_seconds = load_seconds
        self.optimisations = optimisations
        self.warmup_seconds = 0.0

        self._model = model
        self._lock = threading.Lock()  # one forward pass at a time; CPU cores are shared anyway
        self._mean = torch.tensor(spec.mean, dtype=torch.float32, device=device).view(1, 3, 1, 1)
        self._std = torch.tensor(spec.std, dtype=torch.float32, device=device).view(1, 3, 1, 1)

    # ----------------------------------------------------------------- loading
    @classmethod
    def load(
        cls,
        spec: EmbeddingModelSpec,
        weights_dir: Path,
        device: torch.device,
        *,
        checkpoint: Path | None = None,
        batch_size: int = 32,
        use_flip_tta: bool = False,
        fold_bn: bool = False,
    ) -> OSNetExtractor:
        """Build the network, load verified weights, switch to eval mode. Raises ModelUnavailable.

        ``fold_bn`` merges batch-norm layers into the convolutions: the same output, and a small (~4% on the
        development CPU, not consistently measurable) speed-up. Off by default.
        """
        started = time.perf_counter()

        if checkpoint is not None:
            if not checkpoint.is_file():
                raise ModelUnavailable(f"The configured checkpoint does not exist: {checkpoint}")
            weights_path, custom = checkpoint, True
            weights_label = f"custom checkpoint: {checkpoint.name}"
        else:
            weights_path, custom = locate_official_weights(spec, weights_dir), False
            weights_label = f"official {spec.weights.filename}"

        state_dict = load_state_dict(weights_path)
        model = OSNetAIN(spec.channels, spec.feature_dim)
        try:
            model.load_state_dict(state_dict, strict=True)
        except RuntimeError as exc:
            raise ModelUnavailable(
                f"The weights in {weights_path.name} do not fit the '{spec.name}' architecture: {exc}"
            ) from exc

        model.to(device).eval()  # eval mode: batch-norm uses its learned statistics
        optimisations: tuple[str, ...] = ()
        if fold_bn:
            folded = fold_batch_norm(model)
            optimisations = (f"batch-norm folded into {folded} layers",)
        for parameter in model.parameters():
            parameter.requires_grad_(False)

        extractor = cls(
            spec,
            model,
            device,
            batch_size=batch_size,
            use_flip_tta=use_flip_tta,
            weights_label=weights_label,
            weights_sha256=sha256_of_file(weights_path),
            custom_checkpoint=custom,
            load_seconds=time.perf_counter() - started,
            optimisations=optimisations,
        )
        extractor._warm_up()
        logger.info(
            "Embedding model %s ready on %s (load %.2fs, warm-up %.2fs, dim=%d)",
            spec.name,
            device,
            extractor.load_seconds,
            extractor.warmup_seconds,
            extractor.dim,
        )
        return extractor

    def _warm_up(self) -> None:
        """Run one throw-away batch so the first real request is not slowed by lazy initialisation."""
        started = time.perf_counter()
        dummy = np.zeros((1, self.spec.input_height, self.spec.input_width, 3), dtype=np.uint8)
        self.embed(list(dummy))
        self.warmup_seconds = time.perf_counter() - started

    # --------------------------------------------------------------- inference
    @property
    def fingerprint(self) -> str:
        """Identifies the exact embedding function (used as a cache key in evaluation)."""
        return f"{self.name}-{self.weights_sha256[:12]}-flip{int(self.use_flip_tta)}"

    def embed(self, crops: Sequence[np.ndarray]) -> np.ndarray:
        """Normal embeddings (with flip averaging if ``use_flip_tta`` is on)."""
        return self._embed_all(crops, mirrored=False)

    def embed_mirrored(self, crops: Sequence[np.ndarray]) -> np.ndarray:
        """Embeddings of the horizontally flipped crops only (used to build flip-TTA in evaluation)."""
        return self._embed_all(crops, mirrored=True)

    def _embed_all(self, crops: Sequence[np.ndarray], *, mirrored: bool) -> np.ndarray:
        if len(crops) == 0:
            return np.zeros((0, self.dim), dtype=np.float32)

        outputs = []
        for start in range(0, len(crops), self.batch_size):
            batch = self._to_tensor(crops[start : start + self.batch_size])
            outputs.append(self._forward(batch, mirrored))
        embeddings = torch.cat(outputs).cpu().numpy().astype(np.float32, copy=False)
        return self._validate(embeddings, expected_rows=len(crops))

    def _to_tensor(self, crops: Sequence[np.ndarray]) -> torch.Tensor:
        size = (self.spec.input_width, self.spec.input_height)  # cv2 wants (width, height)
        resized = []
        for crop in crops:
            if crop.ndim != 3 or crop.shape[2] != 3 or crop.shape[0] < 2 or crop.shape[1] < 2:
                raise ProcessingFailed(f"A crop with shape {crop.shape} cannot be embedded.")
            shrinking = crop.shape[0] > size[1]
            resized.append(
                cv2.resize(crop, size, interpolation=cv2.INTER_AREA if shrinking else cv2.INTER_LINEAR)
            )
        batch = torch.from_numpy(np.stack(resized)).to(self.device)  # (B, H, W, 3) uint8
        batch = batch.permute(0, 3, 1, 2).float().div_(255.0)  # (B, 3, H, W) in [0, 1]
        return (batch - self._mean) / self._std

    def _forward(self, batch: torch.Tensor, mirrored: bool = False) -> torch.Tensor:
        with self._lock, torch.inference_mode():  # no gradients, no autograd bookkeeping
            if mirrored:
                return F.normalize(self._model(torch.flip(batch, dims=[3])), dim=1)
            features = F.normalize(self._model(batch), dim=1)
            if self.use_flip_tta:
                flipped = F.normalize(self._model(torch.flip(batch, dims=[3])), dim=1)
                features = F.normalize(features + flipped, dim=1)
        return features

    def _validate(self, embeddings: np.ndarray, expected_rows: int) -> np.ndarray:
        if embeddings.shape != (expected_rows, self.dim):
            raise ProcessingFailed(
                f"Embedding shape {embeddings.shape} does not match the expected {(expected_rows, self.dim)}."
            )
        if not np.isfinite(embeddings).all():
            raise ProcessingFailed("The model produced non-finite values (NaN/Inf) for this input.")
        norms = np.linalg.norm(embeddings, axis=1)
        if not np.allclose(norms, 1.0, atol=1e-3):
            raise ProcessingFailed("Embeddings are not unit length after normalisation.")
        return embeddings

    # ------------------------------------------------------------------ status
    def info(self) -> dict:
        return {
            "architecture": self.spec.display_name,
            "name": self.name,
            "embedding_dim": self.dim,
            "input_size": [self.spec.input_height, self.spec.input_width],
            "weights": self.weights_label,
            "weights_sha256": self.weights_sha256,
            "weights_verified_against_pinned_hash": not self.custom_checkpoint,
            "weights_license": self.spec.weights_license,
            "weights_source": self.spec.weights_source,
            "training_data": "custom fine-tuned checkpoint (see its metadata)"
            if self.custom_checkpoint
            else self.spec.training_data,
            "parameters": int(sum(p.numel() for p in self._model.parameters())),
            "flip_tta": self.use_flip_tta,
            "optimisations": list(self.optimisations),
            "device": str(self.device),
            "load_seconds": round(self.load_seconds, 3),
            "warmup_seconds": round(self.warmup_seconds, 3),
            "fingerprint": self.fingerprint,
        }
