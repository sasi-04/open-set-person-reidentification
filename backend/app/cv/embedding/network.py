"""Builds the network architecture a registry entry names (so the rest of the app never needs to know which one it is)."""

from __future__ import annotations

from torch import nn

from ...core.errors import ValidationFailed
from .osnet import OSNet
from .osnet_ain import OSNetAIN
from .registry import EmbeddingModelSpec


def build_network(spec: EmbeddingModelSpec) -> nn.Module:
    if spec.architecture == "osnet":
        return OSNet(spec.channels, spec.feature_dim)
    if spec.architecture == "osnet_ain":
        return OSNetAIN(spec.channels, spec.feature_dim)
    raise ValidationFailed(f"Unknown network architecture '{spec.architecture}' for model '{spec.name}'.")
