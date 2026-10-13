"""
The catalogue of embedding models we know how to run.

In plain words: this is the ONE place that says which model names exist, how
big their layers are, what input size they expect, how to normalise pixels,
and where their pretrained weights come from (URL, file size, SHA-256 hash and
licence). If you want to try a different backbone, you add an entry here (and,
if it is not an OSNet, a small extractor class next to ``extractor.py``).

About the weights
-----------------
The pretrained OSNet-AIN weights are the ones released by the Torchreid
authors (MIT licence) for domain generalisation. They were trained on
MSMT17 + DukeMTMC-reID + CUHK03 - NOT on Market-1501 - so Market-1501 is an
unseen target domain for them, which makes it a fair evaluation set.
The copy we download is a byte-identical mirror on Hugging Face
(``LibreYOLO/LibreReID-osnet``, MIT) whose SHA-256 hashes were cross-checked
against the Hugging Face API. The files are checked against those hashes
before they are ever loaded.

Dataset-licence caveat (also stated in the README): those training sets are
research datasets with their own terms, and DukeMTMC-reID was withdrawn by its
authors in 2019 for privacy reasons. This prototype is for research
demonstration only.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.errors import ValidationFailed

_HF_BASE = "https://huggingface.co/LibreYOLO/LibreReID-osnet/resolve/main"


@dataclass(frozen=True)
class WeightFile:
    filename: str
    url: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class EmbeddingModelSpec:
    name: str
    display_name: str
    channels: tuple[int, int, int, int]  # width of the four stages of the network
    weights: WeightFile
    feature_dim: int = 512  # size of the embedding vector - the single source of truth
    input_height: int = 256
    input_width: int = 128
    mean: tuple[float, float, float] = (0.485, 0.456, 0.406)  # ImageNet statistics
    std: tuple[float, float, float] = (0.229, 0.224, 0.225)
    weights_license: str = "MIT (Torchreid); see training-data caveat in the README"
    weights_source: str = "https://huggingface.co/LibreYOLO/LibreReID-osnet"
    training_data: str = "MSMT17 + DukeMTMC-reID + CUHK03 (multi-source domain generalisation)"


def _weight(filename: str, sha256: str, size_bytes: int) -> WeightFile:
    return WeightFile(filename=filename, url=f"{_HF_BASE}/{filename}", sha256=sha256, size_bytes=size_bytes)


EMBEDDING_MODELS: dict[str, EmbeddingModelSpec] = {
    spec.name: spec
    for spec in (
        EmbeddingModelSpec(
            name="osnet_ain_x1_0",
            display_name="OSNet-AIN x1.0",
            channels=(64, 256, 384, 512),
            weights=_weight(
                "osnet_ain_x1_0.pt",
                "34c24e98b6b70c8b62480f846fd0d581aa2fd1535bc0276aecf1f10430b731d1",
                8_932_647,
            ),
        ),
        EmbeddingModelSpec(
            name="osnet_ain_x0_75",
            display_name="OSNet-AIN x0.75",
            channels=(48, 192, 288, 384),
            weights=_weight(
                "osnet_ain_x0_75.pt",
                "57b31d7f806edac586540e08e98c589f0010ad7876dacf4af013deaa284dd26d",
                5_375_571,
            ),
        ),
        EmbeddingModelSpec(
            name="osnet_ain_x0_5",
            display_name="OSNet-AIN x0.5",
            channels=(32, 128, 192, 256),
            weights=_weight(
                "osnet_ain_x0_5.pt",
                "510bcebae21bd0c0fcc7df388e97d2f687a9ee4befa4394d6fb1fb19aac0bce2",
                2_736_551,
            ),
        ),
        EmbeddingModelSpec(
            name="osnet_ain_x0_25",
            display_name="OSNet-AIN x0.25",
            channels=(16, 64, 96, 128),
            weights=_weight(
                "osnet_ain_x0_25.pt",
                "ce171fe160b3608f5e4c19489774991419be965b1d6f4bdccc4b4cfd2ef95347",
                1_001_683,
            ),
        ),
    )
}


def get_spec(name: str) -> EmbeddingModelSpec:
    try:
        return EMBEDDING_MODELS[name]
    except KeyError:
        raise ValidationFailed(
            f"Unknown embedding model '{name}'. Available: {', '.join(sorted(EMBEDDING_MODELS))}."
        ) from None
