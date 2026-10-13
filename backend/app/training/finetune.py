"""
Fine-tune the embedding backbone with batch-hard triplet loss.

In plain words: this continues training the pretrained OSNet on the DEVELOPMENT identities of a
dataset (never the calibration or test identities), then saves a checkpoint together with a record
of exactly which people it saw. The evaluation later refuses to score a checkpoint whose training
people overlap its calibration/test people, so a fine-tuned result can never be inflated by leakage.

What it does NOT do: it does not claim improvement. Whether the fine-tuned backbone is better is
decided only by running the evaluation (ablation variant "triplet fine-tuned backbone") on held-out
people. The script reports training loss only.

Defaults are CPU-friendly: only the last stage (conv4, conv5, fc) is trained and the network stays
in eval mode, so batch-norm statistics are not disturbed by tiny batches.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

from ..core.errors import ValidationFailed
from ..cv.embedding.osnet_ain import OSNetAIN
from ..cv.embedding.registry import EmbeddingModelSpec
from ..cv.embedding.weights import load_state_dict, locate_official_weights, sha256_of_file
from ..cv.geometry import pad_to_person_aspect
from ..cv.imaging import load_rgb_file
from ..evaluation.datasets import ImageRecord
from .triplet import PKBatchSampler, batch_hard_triplet_loss

logger = logging.getLogger(__name__)

TRAINABLE_PREFIXES = {
    "head": ("conv4.", "conv5.", "fc."),  # last stage only: fast on CPU, least risk of forgetting
    "all": ("",),
}


@dataclass
class FineTuneConfig:
    dataset: str
    seed: int = 0
    epochs: int = 3
    batches_per_epoch: int = 40
    people_per_batch: int = 8
    photos_per_person: int = 4
    learning_rate: float = 1e-4
    weight_decay: float = 5e-4
    margin: float = 0.3
    trainable: str = "head"  # "head" | "all"
    max_identities: int | None = None
    max_images_per_identity: int = 20
    protocol: dict = field(default_factory=dict)  # the evaluation protocol this checkpoint belongs to


class _TrainImages(Dataset):
    """Training photos with light augmentation. No hue shift: clothing colour IS the identity cue."""

    def __init__(self, records: list[ImageRecord], labels: list[int], spec: EmbeddingModelSpec, seed: int):
        self.records, self.labels, self.spec = records, labels, spec
        self.mean = np.array(spec.mean, dtype=np.float32)
        self.std = np.array(spec.std, dtype=np.float32)
        self.rng = np.random.default_rng(seed)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int):
        height, width = self.spec.input_height, self.spec.input_width
        image = pad_to_person_aspect(load_rgb_file(self.records[index].path))
        image = cv2.resize(image, (width + 16, height + 32), interpolation=cv2.INTER_LINEAR)
        top = int(self.rng.integers(0, 33))  # random crop = small shifts of the person in the frame
        left = int(self.rng.integers(0, 17))
        image = image[top : top + height, left : left + width]
        if self.rng.random() < 0.5:
            image = image[:, ::-1]  # horizontal flip
        image = image.astype(np.float32) / 255.0
        image = image * self.rng.uniform(0.8, 1.2) + self.rng.uniform(-0.08, 0.08)  # brightness / contrast
        if self.rng.random() < 0.3:  # random erasing: simulates occlusion
            eh, ew = int(height * self.rng.uniform(0.1, 0.3)), int(width * self.rng.uniform(0.2, 0.5))
            y, x = int(self.rng.integers(0, height - eh)), int(self.rng.integers(0, width - ew))
            image[y : y + eh, x : x + ew] = self.rng.random(3)
        image = (np.clip(image, 0, 1) - self.mean) / self.std
        return torch.from_numpy(np.ascontiguousarray(image.transpose(2, 0, 1))), self.labels[index]


def select_training_records(records: list[ImageRecord], dev_ids: set[str], config: FineTuneConfig) -> list[ImageRecord]:
    """Photos of the development people only, optionally capped (deterministically) for speed."""
    rng = np.random.default_rng(config.seed)
    by_person: dict[str, list[ImageRecord]] = {}
    for record in records:
        if record.identity in dev_ids:
            by_person.setdefault(record.identity, []).append(record)
    people = sorted(p for p, images in by_person.items() if len(images) >= 2)
    if config.max_identities is not None:
        people = people[: config.max_identities]
    selected: list[ImageRecord] = []
    for person in people:
        images = sorted(by_person[person], key=lambda r: r.path.name)
        if len(images) > config.max_images_per_identity:
            images = [images[i] for i in sorted(rng.choice(len(images), config.max_images_per_identity, replace=False))]
        selected += images
    return selected


def finetune(
    spec: EmbeddingModelSpec,
    weights_dir: Path,
    records: list[ImageRecord],
    dev_ids: set[str],
    config: FineTuneConfig,
    output: Path,
    *,
    base_state: dict | None = None,
    progress: Callable[[str], None] = lambda _: None,
) -> dict:
    """Train and save ``output`` (a .pt file) plus ``output.with_suffix('.json')``. Returns the metadata."""
    if config.trainable not in TRAINABLE_PREFIXES:
        raise ValidationFailed(f"trainable must be one of {sorted(TRAINABLE_PREFIXES)}")
    torch.manual_seed(config.seed)

    chosen = select_training_records(records, dev_ids, config)
    people = sorted({r.identity for r in chosen})
    if len(people) < max(config.people_per_batch, 10):
        raise ValidationFailed(f"Only {len(people)} development identities with 2+ photos are available; need at least "
                               f"{max(config.people_per_batch, 10)}.")
    label_of = {person: i for i, person in enumerate(people)}
    labels = [label_of[r.identity] for r in chosen]

    # Start from the verified pretrained weights (or an injected state, used by the unit tests).
    if base_state is None:
        base_path = locate_official_weights(spec, weights_dir)
        base_state, base_sha = load_state_dict(base_path), sha256_of_file(base_path)
    else:
        base_sha = "injected-for-test"
    model = OSNetAIN(spec.channels, spec.feature_dim)
    model.load_state_dict(base_state, strict=True)
    model.eval()  # keeps batch-norm statistics fixed (tiny batches would corrupt them)

    prefixes = TRAINABLE_PREFIXES[config.trainable]
    trainable = []
    for name, parameter in model.named_parameters():
        parameter.requires_grad_(name.startswith(prefixes))
        if parameter.requires_grad:
            trainable.append(parameter)
    optimiser = torch.optim.AdamW(trainable, lr=config.learning_rate, weight_decay=config.weight_decay)

    sampler = PKBatchSampler(labels, config.people_per_batch, config.photos_per_person, config.batches_per_epoch, config.seed)
    loader = DataLoader(_TrainImages(chosen, labels, spec, config.seed), batch_sampler=sampler, num_workers=0)

    history: list[dict] = []
    started = time.perf_counter()
    for epoch in range(config.epochs):
        sampler.set_epoch(epoch)
        losses, active = [], []
        for images, batch_labels in loader:
            features = model(images)
            loss, stats = batch_hard_triplet_loss(features, batch_labels, config.margin)
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            losses.append(stats.loss)
            active.append(stats.active_fraction)
        history.append({"epoch": epoch + 1, "loss": float(np.mean(losses)), "active_triplets": float(np.mean(active))})
        progress(f"epoch {epoch + 1}/{config.epochs}  loss {history[-1]['loss']:.4f}  active triplets {history[-1]['active_triplets']:.0%}")

    metadata = {
        "what": "OSNet-AIN fine-tuned with batch-hard triplet loss (cosine distance)",
        "model": spec.name,
        "base_weights_sha256": base_sha,
        "config": asdict(config),
        "dev_identities": people,  # EVERY person the network saw: the evaluation checks these against its test people
        "training_images": len(chosen),
        "history": history,
        "seconds": round(time.perf_counter() - started, 1),
        "torch": str(torch.__version__),  # a plain str: the safe loader (weights_only=True) rejects richer objects
        "validated": False,
        "note": "Training loss only. Whether this checkpoint is better must be shown by the held-out evaluation.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "meta": metadata}, output)
    output.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    logger.info("Saved fine-tuned checkpoint %s", output)
    return metadata
