"""
The open-set evaluation protocol: who is enrolled, who is a stranger, who is held out.

In plain words: to measure false accepts honestly we must be strict about
which people are allowed to appear where. This module takes a flat list of
labelled images and builds three PEOPLE-DISJOINT groups (nobody appears in two):

    dev           people for training / hard-negative mining (not used for scoring)
    calibration   people used ONLY to choose thresholds and fit confidence models
    test          people used ONLY for the final, reported numbers

Inside each of calibration and test, people are split again:

    enrolled   -> a few photos become the GALLERY ("gallery shots"); their other
                  photos are KNOWN queries ("this person is enrolled; find them")
    unknown    -> never enrolled; all their photos are UNKNOWN queries
                  ("this person is a stranger; the system must not accept them")

Everything is driven by one seed, so the same configuration always produces the
same split. ``assert_disjoint`` re-checks the guarantees and is run by the tests.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

import numpy as np

from .datasets import ImageRecord


@dataclass(frozen=True)
class ProtocolConfig:
    seed: int = 0
    dev_fraction: float = 0.4
    calibration_fraction: float = 0.2  # the rest (1 - dev - calibration) is the test split
    enrolled_fraction: float = 0.5  # share of each evaluation split's people who are enrolled
    gallery_shots: int = 3  # reference images per enrolled person
    max_identities_per_split: int | None = None  # cap people per split (speed on CPU)
    max_images_per_identity: int | None = 12  # cap photos per person (speed on CPU)
    cross_camera: bool = True  # a query never matches a gallery image from its own camera

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SplitProtocol:
    name: str
    gallery: list[ImageRecord]
    known_queries: list[ImageRecord]
    unknown_queries: list[ImageRecord]

    @property
    def enrolled_ids(self) -> set[str]:
        return {r.identity for r in self.gallery}

    @property
    def unknown_ids(self) -> set[str]:
        return {r.identity for r in self.unknown_queries}

    def summary(self) -> dict:
        return {
            "enrolled_identities": len(self.enrolled_ids),
            "unknown_identities": len(self.unknown_ids),
            "gallery_images": len(self.gallery),
            "known_queries": len(self.known_queries),
            "unknown_queries": len(self.unknown_queries),
        }


@dataclass
class Protocol:
    config: ProtocolConfig
    dev_ids: set[str]
    calibration: SplitProtocol
    test: SplitProtocol

    def summary(self) -> dict:
        return {
            "config": self.config.to_dict(),
            "dev_identities": len(self.dev_ids),
            "calibration": self.calibration.summary(),
            "test": self.test.summary(),
        }

    def assert_disjoint(self) -> None:
        """Raise if any person appears in two partitions, or a query image is also a gallery image."""
        groups = {
            "dev": self.dev_ids,
            "calibration-enrolled": self.calibration.enrolled_ids,
            "calibration-unknown": self.calibration.unknown_ids,
            "test-enrolled": self.test.enrolled_ids,
            "test-unknown": self.test.unknown_ids,
        }
        names = list(groups)
        for i, first in enumerate(names):
            for second in names[i + 1 :]:
                overlap = groups[first] & groups[second]
                if overlap:
                    raise AssertionError(f"Identity leakage: {sorted(overlap)[:3]} appear in both {first} and {second}")
        for split in (self.calibration, self.test):
            gallery_paths = {r.path for r in split.gallery}
            if gallery_paths & {r.path for r in split.known_queries}:
                raise AssertionError(f"{split.name}: a gallery image is also used as a known query")


def build_protocol(records: list[ImageRecord], config: ProtocolConfig) -> Protocol:
    if config.gallery_shots < 1:
        raise ValueError("gallery_shots must be at least 1")
    if not 0 < config.dev_fraction + config.calibration_fraction < 1:
        raise ValueError("dev_fraction + calibration_fraction must leave room for a test split")

    by_identity: dict[str, list[ImageRecord]] = defaultdict(list)
    for record in records:
        by_identity[record.identity].append(record)

    # A known person needs gallery shots PLUS at least one photo left to use as a query.
    minimum_images = config.gallery_shots + 1
    usable = sorted(identity for identity, images in by_identity.items() if len(images) >= minimum_images)
    if len(usable) < 10:
        raise ValueError(
            f"Only {len(usable)} people have at least {minimum_images} images; need at least 10 to build splits."
        )

    rng = np.random.default_rng(config.seed)
    shuffled = [usable[i] for i in rng.permutation(len(usable))]
    n_dev = int(round(len(shuffled) * config.dev_fraction))
    n_cal = int(round(len(shuffled) * config.calibration_fraction))
    dev_ids = set(shuffled[:n_dev])
    cal_ids = shuffled[n_dev : n_dev + n_cal]
    test_ids = shuffled[n_dev + n_cal :]

    protocol = Protocol(
        config=config,
        dev_ids=dev_ids,
        calibration=_build_split("calibration", cal_ids, by_identity, config, rng),
        test=_build_split("test", test_ids, by_identity, config, rng),
    )
    protocol.assert_disjoint()
    return protocol


def _build_split(
    name: str,
    identities: list[str],
    by_identity: dict[str, list[ImageRecord]],
    config: ProtocolConfig,
    rng: np.random.Generator,
) -> SplitProtocol:
    identities = list(identities)
    if config.max_identities_per_split is not None:
        identities = identities[: config.max_identities_per_split]
    n_enrolled = max(1, int(round(len(identities) * config.enrolled_fraction)))
    enrolled, unknown = identities[:n_enrolled], identities[n_enrolled:]

    gallery, known_queries, unknown_queries = [], [], []
    for identity in enrolled:
        images = _cap(by_identity[identity], config.max_images_per_identity, rng)
        shots = _pick_gallery_shots(images, config.gallery_shots, rng)
        shot_paths = {r.path for r in shots}
        gallery += shots
        known_queries += [r for r in images if r.path not in shot_paths]
    for identity in unknown:
        unknown_queries += _cap(by_identity[identity], config.max_images_per_identity, rng)

    return SplitProtocol(name, gallery, known_queries, unknown_queries)


def _cap(images: list[ImageRecord], limit: int | None, rng: np.random.Generator) -> list[ImageRecord]:
    ordered = sorted(images, key=lambda r: r.path.name)
    if limit is None or len(ordered) <= limit:
        return ordered
    keep = sorted(rng.choice(len(ordered), size=limit, replace=False))
    return [ordered[i] for i in keep]


def _pick_gallery_shots(images: list[ImageRecord], n: int, rng: np.random.Generator) -> list[ImageRecord]:
    """Choose gallery photos spread over as many different cameras as possible (round robin)."""
    by_camera: dict[int | None, list[ImageRecord]] = defaultdict(list)
    for image in images:
        by_camera[image.camera].append(image)
    for group in by_camera.values():
        rng.shuffle(group)
    cameras = sorted(by_camera, key=lambda c: (c is None, c if c is not None else 0))
    rng.shuffle(cameras)

    chosen: list[ImageRecord] = []
    while len(chosen) < n and any(by_camera.values()):
        for camera in cameras:
            if by_camera[camera] and len(chosen) < n:
                chosen.append(by_camera[camera].pop())
    return chosen
