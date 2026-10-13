"""
The contract every embedding backbone must satisfy.

In plain words: the rest of the application only ever talks to this small
interface - "give me crops, I give you unit-length vectors". That is what makes
the backbone swappable: write another class with these members and register it
in ``factory.py``; no other file needs to change.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import numpy as np


class EmbeddingExtractor(Protocol):
    name: str  # e.g. "osnet_ain_x1_0"
    dim: int  # length of one embedding vector
    fingerprint: str  # changes whenever the produced embeddings would change (cache key)

    def embed(self, crops: Sequence[np.ndarray]) -> np.ndarray:
        """RGB uint8 crops -> float32 array (N, dim), every row L2-normalised."""
        ...

    def info(self) -> dict:
        """Facts for the Model & Thresholds screen (source, device, timings ...)."""
        ...
