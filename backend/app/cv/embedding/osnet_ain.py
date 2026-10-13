"""
OSNet-AIN: a small convolutional network that turns a picture of a person into
a 512-number "appearance fingerprint" (an embedding).

In plain words: this file is the neural-network *architecture* only - no
weights, no downloading, no application logic. It is a compact re-write of the
OSNet-AIN model from the open-source Torchreid project (MIT licence, Copyright
(c) 2018 Kaiyang Zhou). Layer and attribute names are intentionally identical
to the original so that the published pretrained weights fit this class
exactly. Anything that is not needed at inference time (the identity
classifier head, the ImageNet weight downloader) has been left out.

References
----------
* Zhou et al., "Omni-Scale Feature Learning for Person Re-Identification", ICCV 2019.
* Zhou et al., "Learning Generalisable Omni-Scale Representations for Person
  Re-Identification", TPAMI 2021 (the "AIN" variant adds instance normalisation
  in selected blocks, which helps when the camera / lighting changes).
"""

from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F

# --------------------------------------------------------------------------
# Small building blocks
# --------------------------------------------------------------------------


class ConvLayer(nn.Module):
    """Convolution -> normalisation -> ReLU. ``IN=True`` uses instance norm instead of batch norm."""

    def __init__(self, in_channels, out_channels, kernel_size, stride=1, padding=0, groups=1, IN=False):
        super().__init__()
        self.conv = nn.Conv2d(
            in_channels, out_channels, kernel_size, stride=stride, padding=padding, bias=False, groups=groups
        )
        self.bn = nn.InstanceNorm2d(out_channels, affine=True) if IN else nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU()

    def forward(self, x):
        return self.relu(self.bn(self.conv(x)))


class Conv1x1(nn.Module):
    """1x1 convolution -> batch norm -> ReLU."""

    def __init__(self, in_channels, out_channels, stride=1, groups=1):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, 1, stride=stride, padding=0, bias=False, groups=groups)
        self.bn = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU()

    def forward(self, x):
        return self.relu(self.bn(self.conv(x)))


class Conv1x1Linear(nn.Module):
    """1x1 convolution (+ optional batch norm), no activation."""

    def __init__(self, in_channels, out_channels, stride=1, bn=True):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, 1, stride=stride, padding=0, bias=False)
        self.bn = nn.BatchNorm2d(out_channels) if bn else None

    def forward(self, x):
        x = self.conv(x)
        return self.bn(x) if self.bn is not None else x


class LightConv3x3(nn.Module):
    """Cheap 3x3 convolution: a 1x1 mixing step followed by a depth-wise 3x3."""

    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, out_channels, 1, stride=1, padding=0, bias=False)
        self.conv2 = nn.Conv2d(
            out_channels, out_channels, 3, stride=1, padding=1, bias=False, groups=out_channels
        )
        self.bn = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU()

    def forward(self, x):
        return self.relu(self.bn(self.conv2(self.conv1(x))))


class LightConvStream(nn.Module):
    """``depth`` LightConv3x3 layers in a row (deeper stream = larger receptive field)."""

    def __init__(self, in_channels, out_channels, depth):
        super().__init__()
        if depth < 1:
            raise ValueError(f"depth must be >= 1, got {depth}")
        layers = [LightConv3x3(in_channels, out_channels)]
        layers += [LightConv3x3(out_channels, out_channels) for _ in range(depth - 1)]
        self.layers = nn.Sequential(*layers)

    def forward(self, x):
        return self.layers(x)


class ChannelGate(nn.Module):
    """Learns, per picture, how much each feature channel should count (a tiny attention module)."""

    def __init__(self, in_channels, reduction=16):
        super().__init__()
        self.global_avgpool = nn.AdaptiveAvgPool2d(1)
        self.fc1 = nn.Conv2d(in_channels, in_channels // reduction, kernel_size=1, bias=True, padding=0)
        self.relu = nn.ReLU()
        self.fc2 = nn.Conv2d(in_channels // reduction, in_channels, kernel_size=1, bias=True, padding=0)
        self.gate_activation = nn.Sigmoid()

    def forward(self, x):
        gates = self.gate_activation(self.fc2(self.relu(self.fc1(self.global_avgpool(x)))))
        return x * gates


# --------------------------------------------------------------------------
# Omni-scale blocks: look at the person at several scales at once
# --------------------------------------------------------------------------


class OSBlock(nn.Module):
    """Four parallel streams (1..4 stacked 3x3 layers) merged through a shared channel gate."""

    def __init__(self, in_channels, out_channels, reduction=4, T=4):
        super().__init__()
        mid_channels = out_channels // reduction
        self.conv1 = Conv1x1(in_channels, mid_channels)
        self.conv2 = nn.ModuleList([LightConvStream(mid_channels, mid_channels, t) for t in range(1, T + 1)])
        self.gate = ChannelGate(mid_channels)
        self.conv3 = Conv1x1Linear(mid_channels, out_channels)
        self.downsample = Conv1x1Linear(in_channels, out_channels) if in_channels != out_channels else None

    def forward(self, x):
        identity = x
        x1 = self.conv1(x)
        x2 = 0
        for stream in self.conv2:
            x2 = x2 + self.gate(stream(x1))
        x3 = self.conv3(x2)
        if self.downsample is not None:
            identity = self.downsample(identity)
        return F.relu(x3 + identity)


class OSBlockINin(nn.Module):
    """Same as OSBlock but with instance normalisation inside the residual branch ("AIN")."""

    def __init__(self, in_channels, out_channels, reduction=4, T=4):
        super().__init__()
        mid_channels = out_channels // reduction
        self.conv1 = Conv1x1(in_channels, mid_channels)
        self.conv2 = nn.ModuleList([LightConvStream(mid_channels, mid_channels, t) for t in range(1, T + 1)])
        self.gate = ChannelGate(mid_channels)
        self.conv3 = Conv1x1Linear(mid_channels, out_channels, bn=False)
        self.downsample = Conv1x1Linear(in_channels, out_channels) if in_channels != out_channels else None
        self.IN = nn.InstanceNorm2d(out_channels, affine=True)

    def forward(self, x):
        identity = x
        x1 = self.conv1(x)
        x2 = 0
        for stream in self.conv2:
            x2 = x2 + self.gate(stream(x1))
        x3 = self.IN(self.conv3(x2))
        if self.downsample is not None:
            identity = self.downsample(identity)
        return F.relu(x3 + identity)


# --------------------------------------------------------------------------
# The full network
# --------------------------------------------------------------------------


class OSNetAIN(nn.Module):
    """Image batch (B, 3, 256, 128)  ->  raw embeddings (B, feature_dim).

    The output is *not* normalised here; the extractor L2-normalises it so the
    same code path is used for serving and for evaluation.
    """

    def __init__(self, channels: tuple[int, int, int, int], feature_dim: int = 512):
        super().__init__()
        blocks = [[OSBlockINin, OSBlockINin], [OSBlock, OSBlockINin], [OSBlockINin, OSBlock]]

        self.feature_dim = feature_dim
        self.conv1 = ConvLayer(3, channels[0], 7, stride=2, padding=3, IN=True)
        self.maxpool = nn.MaxPool2d(3, stride=2, padding=1)
        self.conv2 = self._make_stage(blocks[0], channels[0], channels[1])
        self.pool2 = nn.Sequential(Conv1x1(channels[1], channels[1]), nn.AvgPool2d(2, stride=2))
        self.conv3 = self._make_stage(blocks[1], channels[1], channels[2])
        self.pool3 = nn.Sequential(Conv1x1(channels[2], channels[2]), nn.AvgPool2d(2, stride=2))
        self.conv4 = self._make_stage(blocks[2], channels[2], channels[3])
        self.conv5 = Conv1x1(channels[3], channels[3])
        self.global_avgpool = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Sequential(nn.Linear(channels[3], feature_dim), nn.BatchNorm1d(feature_dim), nn.ReLU())

    @staticmethod
    def _make_stage(block_types, in_channels, out_channels):
        layers = [block_types[0](in_channels, out_channels)]
        layers += [block_types[i](out_channels, out_channels) for i in range(1, len(block_types))]
        return nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.conv1(x)
        x = self.maxpool(x)
        x = self.conv2(x)
        x = self.pool2(x)
        x = self.conv3(x)
        x = self.pool3(x)
        x = self.conv4(x)
        x = self.conv5(x)
        x = self.global_avgpool(x).flatten(1)
        return self.fc(x)
