"""Inference-only speed-up: fold batch normalisation into the convolutions. At inference time a
batch-norm layer is just "multiply by a constant, add a constant" per channel - the same thing a
convolution followed by it can do in one step.
"""

from __future__ import annotations

from torch import nn
from torch.nn.utils.fusion import fuse_conv_bn_eval, fuse_linear_bn_eval

from . import osnet as plain_osnet
from . import osnet_ain as ain_osnet

_CONV_BN = (ain_osnet.ConvLayer, ain_osnet.Conv1x1, ain_osnet.Conv1x1Linear, plain_osnet.ConvLayer, plain_osnet.Conv1x1, plain_osnet.Conv1x1Linear)
_LIGHT = (ain_osnet.LightConv3x3, plain_osnet.LightConv3x3)


def fold_batch_norm(model: nn.Module) -> int:
    """Fuse every conv+BN pair in place. Returns how many pairs were folded."""
    if model.training:
        raise RuntimeError("fold_batch_norm needs a model in eval() mode")
    folded = 0
    for module in model.modules():
        if isinstance(module, _CONV_BN) and isinstance(module.bn, nn.BatchNorm2d):
            module.conv = fuse_conv_bn_eval(module.conv, module.bn)
            module.bn = nn.Identity()
            folded += 1
        elif isinstance(module, _LIGHT):
            module.conv2 = fuse_conv_bn_eval(module.conv2, module.bn)
            module.bn = nn.Identity()
            folded += 1

    # The final embedding layer is Linear -> BatchNorm1d -> ReLU.
    linear, norm, relu = model.fc
    if isinstance(norm, nn.BatchNorm1d):
        model.fc = nn.Sequential(fuse_linear_bn_eval(linear, norm), relu)
        folded += 1
    return folded
