"""
Metric learning pieces: the batch-hard triplet loss and the P x K batch sampler.

In plain words: the pretrained network already places photos of the same person near each other.
Fine-tuning with a TRIPLET loss tightens that further, and "batch-hard" mining aims it at exactly
the cases that cause false accepts:

  for every photo in a batch (the "anchor") find
     the HARDEST POSITIVE  - the farthest photo of the SAME person, and
     the HARDEST NEGATIVE  - the closest photo of a DIFFERENT person (the look-alike!)
  and demand that the positive is closer than the negative by at least a margin.

A batch is built from P people with K photos each (the "P x K sampler") so that every anchor has
both positives and negatives to choose from. Distances are COSINE distances (1 - similarity), the
same measure the deployed system ranks with.

Reference: Hermans, Beyer, Leibe - "In Defense of the Triplet Loss for Person Re-Identification" (2017).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import numpy as np
import torch
from torch.nn import functional as F
from torch.utils.data import Sampler


@dataclass(frozen=True)
class TripletStats:
    loss: float
    active_fraction: float  # share of anchors whose triplet still violates the margin (still "learning")
    mean_positive_distance: float
    mean_negative_distance: float


def batch_hard_triplet_loss(
    embeddings: torch.Tensor, labels: torch.Tensor, margin: float = 0.3
) -> tuple[torch.Tensor, TripletStats]:
    """Mean batch-hard triplet loss for a batch of (B, D) embeddings with integer person labels (B,)."""
    if embeddings.ndim != 2 or labels.ndim != 1 or len(embeddings) != len(labels):
        raise ValueError("embeddings must be (B, D) and labels (B,)")

    normalised = F.normalize(embeddings, dim=1)
    distance = 1.0 - normalised @ normalised.T  # cosine distance, (B, B)

    same_person = labels[:, None] == labels[None, :]
    not_self = ~torch.eye(len(labels), dtype=torch.bool, device=labels.device)
    positive_mask = same_person & not_self
    negative_mask = ~same_person

    # An anchor with no positive (or no negative) in the batch cannot form a triplet.
    usable = positive_mask.any(dim=1) & negative_mask.any(dim=1)
    if not usable.any():
        raise ValueError("The batch has no valid triplets: use P >= 2 people with K >= 2 photos each.")

    # Hardest positive = LARGEST distance among positives; hardest negative = SMALLEST among negatives.
    hardest_positive = torch.where(positive_mask, distance, torch.full_like(distance, float("-inf"))).max(dim=1).values
    hardest_negative = torch.where(negative_mask, distance, torch.full_like(distance, float("inf"))).min(dim=1).values

    per_anchor = F.relu(hardest_positive - hardest_negative + margin)[usable]
    stats = TripletStats(
        loss=float(per_anchor.detach().mean()),
        active_fraction=float((per_anchor.detach() > 0).float().mean()),
        mean_positive_distance=float(hardest_positive.detach()[usable].mean()),
        mean_negative_distance=float(hardest_negative.detach()[usable].mean()),
    )
    return per_anchor.mean(), stats


class PKBatchSampler(Sampler[list[int]]):
    """Yields batches of dataset indices: P different people x K photos each.

    A person with fewer than K photos is sampled WITH replacement (some photos repeat) so every batch
    keeps the same shape. The shuffling is driven by ``seed`` and the epoch number, so a run is
    reproducible.
    """

    def __init__(self, labels: Sequence[int], people_per_batch: int, photos_per_person: int, batches_per_epoch: int, seed: int = 0):
        if people_per_batch < 2 or photos_per_person < 2:
            raise ValueError("Need at least 2 people and 2 photos per person per batch.")
        self.by_person: dict[int, list[int]] = {}
        for index, label in enumerate(labels):
            self.by_person.setdefault(int(label), []).append(index)
        if len(self.by_person) < people_per_batch:
            raise ValueError(f"Only {len(self.by_person)} people available but {people_per_batch} are needed per batch.")
        self.p, self.k, self.batches, self.seed, self.epoch = people_per_batch, photos_per_person, batches_per_epoch, seed, 0

    def set_epoch(self, epoch: int) -> None:
        self.epoch = epoch

    def __len__(self) -> int:
        return self.batches

    def __iter__(self) -> Iterator[list[int]]:
        rng = np.random.default_rng((self.seed, self.epoch))
        people = sorted(self.by_person)
        for _ in range(self.batches):
            chosen = rng.choice(people, size=self.p, replace=False)
            batch: list[int] = []
            for person in chosen:
                photos = self.by_person[int(person)]
                batch += [int(i) for i in rng.choice(photos, size=self.k, replace=len(photos) < self.k)]
            yield batch
