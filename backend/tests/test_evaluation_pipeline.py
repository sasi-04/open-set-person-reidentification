"""
Evaluation-pipeline tests.

A FAKE extractor (embedding = a fixed random projection of the image's mean colour) stands in for the
neural network, so these tests are fast and deterministic and check the PLUMBING:
identity-disjoint splits, cross-camera masking, calibration/test separation, reproducibility and
honest reporting. They say nothing about how well the real model performs.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.evaluation import metrics as m
from app.evaluation.calibration import OperatingTarget, select_operating_point
from app.evaluation.datasets import ImageRecord, inspect_dataset, load_records
from app.evaluation.protocol import Protocol, ProtocolConfig, SplitProtocol, build_protocol
from app.evaluation.runner import (
    CalibrationRequest,
    EvaluationRequest,
    run_calibration,
    run_evaluation,
)
from app.evaluation.scoring import score_split


# ------------------------------------------------------------------------- fixtures
class FakeExtractor:
    """Deterministic stand-in for OSNetExtractor. Records every image it is asked to embed."""

    name = "fake"
    weights_sha256 = "0" * 64
    batch_size = 8
    use_flip_tta = False
    fingerprint = "fake-0-flip0"

    def __init__(self, noise: float = 0.0, seed: int = 0):
        self.projection = np.random.default_rng(seed).normal(size=(3, 16))
        self.noise, self.calls = noise, 0
        self.rng = np.random.default_rng(seed + 1)

    def _embed(self, crops, shift: float = 0.0):
        self.calls += len(crops)
        vectors = np.stack([c.reshape(-1, 3).mean(axis=0) / 255.0 for c in crops]) @ self.projection
        vectors = vectors + self.rng.normal(0, self.noise, vectors.shape) + shift
        return (vectors / np.linalg.norm(vectors, axis=1, keepdims=True)).astype(np.float32)

    def embed(self, crops):
        return self._embed(crops)

    def embed_mirrored(self, crops):
        return self._embed(crops, shift=0.001)

    def info(self):
        return {"architecture": "Fake", "name": "fake", "weights": "fake", "device": "cpu",
                "load_seconds": 0.0, "warmup_seconds": 0.0, "fingerprint": self.fingerprint}


def make_dataset(root: Path, identities: int = 40, images: int = 6, cameras: int = 3, kind="benchmark") -> Path:
    """Folder dataset: each person has a distinctive colour plus small per-image variation."""
    rng = np.random.default_rng(5)
    for index in range(identities):
        base = rng.integers(30, 225, 3)
        folder = root / f"P{index:03d}"
        folder.mkdir(parents=True)
        for number in range(images):
            pixels = np.clip(base + rng.integers(-8, 9, 3), 0, 255).astype(np.uint8)
            Image.fromarray(np.tile(pixels, (64, 32, 1))).save(folder / f"c{number % cameras + 1}_{number:02d}.png")
    (root / "dataset.json").write_text(json.dumps({"name": root.name, "kind": kind}))
    return root


@pytest.fixture()
def dataset(tmp_path):
    return inspect_dataset(make_dataset(tmp_path / "toy"))


def records_of(dataset_info) -> list[ImageRecord]:
    return load_records(dataset_info)


def request_for(dataset_info, **overrides) -> EvaluationRequest:
    base = dict(
        dataset=dataset_info.name,
        seeds=(0,),
        target=OperatingTarget("fixed_recall", target_recall=0.5),
        variants=("nn_baseline", "thr", "thr_margin", "thr_confidence", "thr_margin_flip"),
        protocol=ProtocolConfig(dev_fraction=0.2, calibration_fraction=0.3, gallery_shots=2, max_images_per_identity=6),
        bootstrap_samples=30,
    )
    base.update(overrides)
    return EvaluationRequest(**base)


# ------------------------------------------------------------------------ dataset readers
def test_market1501_layout_is_parsed_and_junk_images_are_dropped(tmp_path):
    root = tmp_path / "market1501" / "Market-1501-v15.09.15"  # real downloads unpack into a nested folder
    for sub in ("bounding_box_train", "bounding_box_test", "query"):
        (root / sub).mkdir(parents=True)
    pixels = Image.fromarray(np.zeros((128, 64, 3), dtype=np.uint8))
    for person in range(1, 13):
        for camera in (1, 2, 3):
            pixels.save(root / "bounding_box_train" / f"{person:04d}_c{camera}s1_00{camera}000_00.jpg")
    pixels.save(root / "bounding_box_test" / "-1_c1s1_000151_00.jpg")  # distractor ("-1": not a labelled person)
    pixels.save(root / "bounding_box_test" / "0000_c2s1_000151_01.jpg")  # junk ("0000": detector false positive)
    pixels.save(root / "query" / "0003_c1s1_001051_00.jpg")  # a query image of person 3 (pooled with the rest)

    info = inspect_dataset(tmp_path / "market1501")
    records = load_records(info)
    assert info.layout == "market1501" and info.kind == "benchmark" and info.available
    assert info.n_identities == 12 and info.n_cameras == 3
    assert {r.identity for r in records} == {f"{p:04d}" for p in range(1, 13)}  # -1 and 0000 are gone
    assert len(records) == 12 * 3 + 1
    assert next(r for r in records if "0003_c1s1_001051" in r.path.name).camera == 1
    assert "non-commercial research" in info.license_note


def test_folder_layout_reads_cameras_from_file_names_and_manifest_marks_smoke_tests(tmp_path):
    info = inspect_dataset(make_dataset(tmp_path / "mine", identities=12, images=4, kind="smoke_test"))
    assert info.layout == "folder" and info.kind == "smoke_test"
    assert {r.camera for r in load_records(info)} == {1, 2, 3}


def test_a_dataset_with_too_few_people_is_reported_unusable(tmp_path):
    info = inspect_dataset(make_dataset(tmp_path / "tiny", identities=4, images=4))
    assert not info.available and "at least 10" in info.problems[0]


# --------------------------------------------------------------------------- protocol
def test_splits_are_identity_disjoint(dataset):
    protocol = build_protocol(records_of(dataset), ProtocolConfig(dev_fraction=0.2, calibration_fraction=0.3))
    protocol.assert_disjoint()
    groups = [protocol.dev_ids, protocol.calibration.enrolled_ids, protocol.calibration.unknown_ids,
              protocol.test.enrolled_ids, protocol.test.unknown_ids]
    assert all(g for g in groups)
    assert sum(len(g) for g in groups) == len(set().union(*groups))  # no person in two groups


def test_leakage_is_detected():
    shared = ImageRecord(Path("x/a.jpg"), "P1", 1)
    split = SplitProtocol("test", [shared], [], [ImageRecord(Path("x/b.jpg"), "P1", 2)])  # P1 both enrolled AND unknown
    leaky = Protocol(ProtocolConfig(), set(), SplitProtocol("calibration", [], [], []), split)
    with pytest.raises(AssertionError, match="leakage"):
        leaky.assert_disjoint()


def test_gallery_images_are_never_queries(dataset):
    protocol = build_protocol(records_of(dataset), ProtocolConfig())
    for split in (protocol.calibration, protocol.test):
        assert not {r.path for r in split.gallery} & {r.path for r in split.known_queries}


def test_same_seed_gives_identical_protocol_and_other_seeds_differ(dataset):
    records = records_of(dataset)
    first = build_protocol(records, ProtocolConfig(seed=3))
    again = build_protocol(records, ProtocolConfig(seed=3))
    other = build_protocol(records, ProtocolConfig(seed=4))
    assert [r.path for r in first.test.gallery] == [r.path for r in again.test.gallery]
    assert first.test.enrolled_ids == again.test.enrolled_ids
    assert first.test.enrolled_ids != other.test.enrolled_ids


def test_gallery_shots_are_spread_over_cameras(dataset):
    protocol = build_protocol(records_of(dataset), ProtocolConfig(gallery_shots=3))
    by_person: dict[str, list[int | None]] = {}
    for record in protocol.test.gallery:
        by_person.setdefault(record.identity, []).append(record.camera)
    assert all(len(set(cameras)) == len(cameras) for cameras in by_person.values())


def test_protocol_refuses_tiny_datasets():
    records = [ImageRecord(Path(f"{i}.jpg"), f"P{i % 3}", 1) for i in range(30)]
    with pytest.raises(ValueError, match="at least 10"):
        build_protocol(records, ProtocolConfig())


# ---------------------------------------------------------------------------- scoring
def unit(*values):
    v = np.asarray(values, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_cross_camera_rule_hides_the_true_identitys_same_camera_gallery_images():
    gallery = [ImageRecord(Path("a1"), "A", 1), ImageRecord(Path("a2"), "A", 2), ImageRecord(Path("b1"), "B", 1)]
    split = SplitProtocol("t", gallery, [ImageRecord(Path("q"), "A", 1)], [])
    g_emb = np.stack([unit(1, 0, 0), unit(0.2, 1, 0), unit(0, 0, 1)])
    query = np.stack([unit(1, 0, 0)])  # identical to a1, which shares camera 1 with the query

    with_rule = score_split(split, g_emb, query, np.zeros((0, 3)), cross_camera=True)
    without = score_split(split, g_emb, query, np.zeros((0, 3)), cross_camera=False)
    assert without.qs.top1_score[0] == pytest.approx(1.0)  # trivial same-camera match
    assert with_rule.qs.top1_score[0] < 0.5 or not with_rule.qs.top1_correct[0]  # a1 must not be used


def test_known_query_without_cross_camera_gallery_image_is_dropped_and_counted():
    gallery = [ImageRecord(Path("a1"), "A", 1), ImageRecord(Path("b1"), "B", 2)]
    split = SplitProtocol("t", gallery, [ImageRecord(Path("q"), "A", 1)], [ImageRecord(Path("u"), "C", 1)])
    scored = score_split(split, np.stack([unit(1, 0), unit(0, 1)]), np.stack([unit(1, 0)]),
                         np.stack([unit(0.7, 0.7)]), cross_camera=True)
    assert scored.dropped_known_queries == 1 and scored.qs.n_known == 0 and scored.qs.n_unknown == 1


def test_scoring_marks_correct_identification_and_rank():
    gallery = [ImageRecord(Path("a1"), "A", 1), ImageRecord(Path("b1"), "B", 1), ImageRecord(Path("c1"), "C", 1)]
    split = SplitProtocol("t", gallery, [ImageRecord(Path("qa"), "A", 2), ImageRecord(Path("qb"), "B", 2)], [])
    g = np.stack([unit(1, 0, 0), unit(0, 1, 0), unit(0, 0, 1)])
    q = np.stack([unit(1, 0.1, 0), unit(0.6, 1, 0)])  # first is closest to A (correct); second's true id B is rank 2? no: B=1.0
    scored = score_split(split, g, q, np.zeros((0, 3)), cross_camera=True)
    assert scored.qs.top1_correct.tolist() == [True, True]
    assert scored.qs.true_rank.tolist() == [1, 1]
    assert scored.cmc[0] == 1.0 and scored.mean_ap == pytest.approx(1.0)


# ---------------------------------------------------------------------- calibration
def test_fixed_far_selection_respects_the_target_on_calibration_data():
    rng = np.random.default_rng(0)
    n = 500
    qs = m.QueryScores(
        is_known=np.r_[np.ones(n, bool), np.zeros(n, bool)],
        top1_score=np.r_[rng.normal(0.8, 0.08, n), rng.normal(0.5, 0.08, n)],
        margin=np.full(2 * n, 0.2), top1_correct=np.r_[np.ones(n, bool), np.zeros(n, bool)],
        true_rank=np.r_[np.ones(n, int), np.zeros(n, int)], cluster=np.arange(2 * n))
    chosen = select_operating_point(qs, OperatingTarget("fixed_far", target_far=0.02))
    assert chosen.target_achieved
    assert chosen.calibration["far"] <= 0.02
    assert chosen.far_upper_bound_95 > chosen.calibration["far"] - 1e-12  # the bound is never optimistic
    assert chosen.calibration["tar"] > 0.5  # and it keeps most enrolled people


def test_unreachable_target_is_reported_not_hidden():
    rng = np.random.default_rng(1)
    n = 300  # known and unknown scores drawn from the SAME distribution: no threshold can separate them
    qs = m.QueryScores(
        is_known=np.r_[np.ones(n, bool), np.zeros(n, bool)], top1_score=rng.normal(0.6, 0.1, 2 * n),
        margin=np.full(2 * n, 0.1), top1_correct=np.r_[rng.random(n) < 0.5, np.zeros(n, bool)],
        true_rank=np.r_[np.ones(n, int), np.zeros(n, int)], cluster=np.arange(2 * n))
    chosen = select_operating_point(qs, OperatingTarget("fixed_recall", target_recall=0.99))
    assert chosen.target_achieved is False
    assert any("could NOT be met" in note for note in chosen.notes)


def test_small_calibration_sets_are_flagged_for_tiny_far_targets():
    rng = np.random.default_rng(2)
    n = 50
    qs = m.QueryScores(
        is_known=np.r_[np.ones(n, bool), np.zeros(n, bool)],
        top1_score=np.r_[rng.normal(0.9, 0.03, n), rng.normal(0.4, 0.05, n)], margin=np.full(2 * n, 0.2),
        top1_correct=np.r_[np.ones(n, bool), np.zeros(n, bool)],
        true_rank=np.r_[np.ones(n, int), np.zeros(n, int)], cluster=np.arange(2 * n))
    chosen = select_operating_point(qs, OperatingTarget("fixed_far", target_far=0.001))
    assert chosen.sample_size_adequate is False  # 50 strangers cannot resolve 0.1%


def test_invalid_targets_are_rejected():
    with pytest.raises(ValueError):
        OperatingTarget("fixed_recall", target_recall=1.5).validate()
    with pytest.raises(ValueError):
        OperatingTarget("sometimes").validate()


# ------------------------------------------------------------------ end-to-end runs
def factory_for(extractor):
    return lambda checkpoint: extractor


def test_full_run_produces_all_variants_and_selects_on_calibration(dataset, tmp_path):
    result = run_evaluation(dataset, request_for(dataset), cache_dir=tmp_path / "cache",
                            make_extractor=factory_for(FakeExtractor(noise=0.02)))
    assert set(result["variants"]) == {"nn_baseline", "thr", "thr_margin", "thr_confidence", "thr_margin_flip"}
    baseline = result["variants"]["nn_baseline"]["per_seed"][0]["test"]
    assert baseline["far"] == 1.0  # a nearest neighbour that never rejects accepts every stranger
    assert result["selected_variant"]["selected_on"] == "calibration split"
    assert result["metadata"]["is_benchmark"] is True and result["warnings"] == []
    thr = result["variants"]["thr"]["per_seed"][0]
    assert thr["selected"]["calibration"]["counts"]["unknown_queries"] > 0  # chosen on calibration data
    assert thr["test"]["counts"]["unknown_queries"] > 0  # reported on test data


def test_runs_are_reproducible_with_fixed_seeds(dataset, tmp_path):
    def headline(cache):
        r = run_evaluation(dataset, request_for(dataset, seeds=(0, 1)), cache_dir=cache,
                           make_extractor=factory_for(FakeExtractor(noise=0.02, seed=9)))
        return {k: v["summary"] for k, v in r["variants"].items()}

    assert headline(tmp_path / "a") == headline(tmp_path / "b")


def test_smoke_dataset_results_are_labelled_not_a_benchmark(tmp_path):
    info = inspect_dataset(make_dataset(tmp_path / "smoke", kind="smoke_test"))
    result = run_evaluation(info, request_for(info), cache_dir=tmp_path / "c", make_extractor=factory_for(FakeExtractor(0.02)))
    assert result["metadata"]["is_benchmark"] is False
    assert "NOT benchmark results" in result["warnings"][0]


def test_missing_finetuned_checkpoint_is_reported_as_unavailable(dataset, tmp_path):
    request = request_for(dataset, variants=("thr_margin", "thr_margin_finetuned"))
    result = run_evaluation(dataset, request, cache_dir=tmp_path / "c", make_extractor=factory_for(FakeExtractor(0.02)))
    assert result["variants"]["thr_margin_finetuned"]["status"] == "unavailable"
    assert result["variants"]["thr_margin"]["status"] == "ok"


def test_impossible_target_yields_no_selected_variant(dataset, tmp_path):
    noisy = FakeExtractor(noise=5.0)  # pure noise: nothing is separable
    request = request_for(dataset, target=OperatingTarget("fixed_recall", target_recall=0.99))
    result = run_evaluation(dataset, request, cache_dir=tmp_path / "c", make_extractor=factory_for(noisy))
    assert result["selected_variant"]["key"] is None
    assert result["variants"]["thr"]["summary"]["targets_achieved"] == 0


def test_calibration_run_never_embeds_a_test_image(dataset, tmp_path):
    extractor = FakeExtractor(noise=0.02)
    seen: list[int] = []
    original = extractor.embed

    def spy(crops):
        seen.append(len(crops))
        return original(crops)

    extractor.embed = spy  # type: ignore[method-assign]
    request = CalibrationRequest(dataset=dataset.name, target=OperatingTarget("fixed_recall", target_recall=0.5),
                                 protocol=ProtocolConfig(dev_fraction=0.2, calibration_fraction=0.3, gallery_shots=2))
    protocol = build_protocol(load_records(dataset), request.protocol)
    calibration_images = {r.path for s in (protocol.calibration,) for r in s.gallery + s.known_queries + s.unknown_queries}
    test_images = {r.path for r in protocol.test.gallery + protocol.test.known_queries + protocol.test.unknown_queries}

    result = run_calibration(dataset, request, cache_dir=tmp_path / "c", make_extractor=factory_for(extractor))
    assert sum(seen) == len(calibration_images)  # exactly the calibration images were embedded, none else
    assert not calibration_images & test_images
    assert result["metadata"]["split_used"].startswith("calibration")
    assert result["proposed_policy"]["status"] in ("calibrated", "experimental")


def test_embedding_cache_avoids_recomputation(dataset, tmp_path):
    extractor = FakeExtractor(noise=0.02)
    request = request_for(dataset, variants=("thr",))
    run_evaluation(dataset, request, cache_dir=tmp_path / "c", make_extractor=factory_for(extractor))
    first_run_calls = extractor.calls
    run_evaluation(dataset, request, cache_dir=tmp_path / "c", make_extractor=factory_for(extractor))
    second_run_calls = extractor.calls - first_run_calls
    # The first run embedded every dataset image plus the latency benchmark. The second run must only
    # repeat the benchmark (a fixed number of calls), so it is far cheaper than the first.
    assert second_run_calls < first_run_calls * 0.5
