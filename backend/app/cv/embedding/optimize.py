"""
Inference-only speed-up: fold batch normalisation into the convolutions.

In plain words: at inference time a batch-norm layer is just "multiply by a constant, add a
constant" per channel - the same thing a convolution followed by it can do in one step. So we
rewrite each (convolution -> batch-norm) pair into a single convolution with adjusted weights.
The network computes the SAME function (verified by a test to ~1e-5) but runs fewer operations.

Why this exists: profiling the backbone on CPU showed convolutions at ~62% of the time and
batch-norm at ~13% (see docs/PERFORMANCE.md), which suggested folding could save up to that much.
HONEST RESULT: measured fairly (interleaved A/B runs) the saving on the development laptop was only
about 4% for single crops and nothing in batches, within the noise of that machine. It is therefore
OFF by default (REID_FOLD_BATCH_NORM) and kept as a tested, opt-in option for other hardware.

This is applied once, after the weights are loaded and the model is in eval mode. A fused model
can no longer be trained - the training code builds its own, un-fused copy.
"""

from __future__ import annotations

from torch import nn
from torch.nn.utils.fusion import fuse_conv_bn_eval, fuse_linear_bn_eval

from .osnet_ain import Conv1x1, Conv1x1Linear, ConvLayer, LightConv3x3, OSNetAIN


def fold_batch_norm(model: OSNetAIN) -> int:
    """Fuse every conv+BN pair in place. Returns how many pairs were folded."""
    if model.training:
        raise RuntimeError("fold_batch_norm needs a model in eval() mode")
    folded = 0
    for module in model.modules():
        if isinstance(module, ConvLayer | Conv1x1 | Conv1x1Linear) and isinstance(module.bn, nn.BatchNorm2d):
            module.conv = fuse_conv_bn_eval(module.conv, module.bn)
            module.bn = nn.Identity()
            folded += 1
        elif isinstance(module, LightConv3x3):
            module.conv2 = fuse_conv_bn_eval(module.conv2, module.bn)
            module.bn = nn.Identity()
            folded += 1

    # The final embedding layer is Linear -> BatchNorm1d -> ReLU.
    linear, norm, relu = model.fc
    if isinstance(norm, nn.BatchNorm1d):
        model.fc = nn.Sequential(fuse_linear_bn_eval(linear, norm), relu)
        folded += 1
    return folded
