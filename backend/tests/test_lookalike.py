"""
Lookalike Failure Lab tests.

A fake extractor stands in for the neural network (embedding = projection of the image's mean colour), so these
tests check the LOGIC: the pair mining is exact, the threshold never depends on the mined split, a second model is
refused unless it is clean, failures carry both facts and hypotheses, and runs are reproducible. They say nothing
about how well the real model performs.
"""

from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pytest
import torch

from app.evaluation.calibration import OperatingTarget
from app.evaluation.datasets import ImageRecord, inspect_dataset, load_records
from app.evaluation.embedding_store import EvaluationCancelled
from app.evaluation.lookalike import (
    HYPOTHESIS_STATUS,
    LookalikeRequest,
    MiningSet,
    challenge_measurement,
    explain_failure,
    genuine_pairs,
    pair_curve,
    run_lookalike,
    scan_identity_pairs,
    top_identity_pairs,
)
from app.evaluation.protocol import ProtocolConfig, build_protocol
from tests.test_evaluation_pipeline import FakeExtractor, make_dataset

PROTOCOL = ProtocolConfig(dev_fraction=0.2, calibration_fraction=0.3, gallery_shots=2, max_images_per_identity=6)


@pytest.fixture()
def toy(tmp_path):
    return inspect_dataset(make_dataset(tmp_path / "toy"))


def request_for(info, **overrides) -> LookalikeRequest:
    base = dict(dataset=info.name, target=OperatingTarget("fixed_recall", target_recall=0.5), protocol=PROTOCOL,
                top_pairs=10, images_per_pair=2, max_failures=5)
    base.update(overrides)
    return LookalikeRequest(**base)


def factory(base: FakeExtractor, tuned: FakeExtractor | None = None):
    return lambda checkpoint: (tuned if (checkpoint is not None and tuned is not None) else base)


def run(info, tmp_path, request=None, *, tuned=None, **kwargs):
    return run_lookalike(info, request or request_for(info), cache_dir=tmp_path / "cache",
                         make_extractor=factory(FakeExtractor(noise=0.02), tuned), experiment_id="exp-1", **kwargs)


def write_checkpoint(folder, dev_identities, *, dataset="toy", seed=0, name="tuned.pt"):
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"dev_identities": sorted(dev_identities), "config": {"dataset": dataset, "seed": seed}, "training_images": 99, "validated": False}
    torch.save({"state_dict": {}, "meta": meta}, folder / name)
    return folder / name


# ------------------------------------------------------------------------------- exact pair mining
def _mining_set(vectors_by_person: dict[str, np.ndarray], cameras=None):
    records, rows = [], []
    for person, vectors in vectors_by_person.items():
        for k, vector in enumerate(vectors):
            camera = (cameras or {}).get(person, [k + 1] * len(vectors))[k]
            records.append(ImageRecord(path=__import__("pathlib").Path(f"{person}_{k}.jpg"), identity=person, camera=camera))
            rows.append(vector)
    mining = MiningSet.build(records)
    order = {r.path: i for i, r in enumerate(records)}
    matrix = np.stack([rows[order[r.path]] for r in mining.records]).astype(np.float32)
    return mining, matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


def test_pair_scan_equals_a_brute_force_double_loop():
    rng = np.random.default_rng(3)
    people = {name: rng.normal(size=(rng.integers(2, 6), 8)) for name in "ABCDEFG"}
    mining, embeddings = _mining_set(people)
    threshold = 0.2
    scan = scan_identity_pairs(embeddings, mining, threshold, block=4)  # a tiny block exercises the chunking

    best = {}
    above = total = 0
    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            a, b = mining.identity_index[i], mining.identity_index[j]
            if a == b:
                continue
            sim = float(embeddings[i] @ embeddings[j])
            total += 1
            above += sim >= threshold
            key = (min(a, b), max(a, b))
            best[key] = max(best.get(key, -np.inf), sim)
    assert (scan["above"], scan["total"]) == (above, total)
    for (a, b), value in best.items():
        assert scan["pair_max"][a, b] == pytest.approx(value, abs=1e-5)
        assert scan["pair_max"][b, a] == pytest.approx(value, abs=1e-5)
    top = top_identity_pairs(scan["pair_max"], 3)
    assert [round(t[2], 5) for t in top] == sorted((round(v, 5) for v in best.values()), reverse=True)[:3]
    assert all(a < b for a, b, _ in top)  # every pair appears once, never (A, A)


def test_genuine_pairs_only_join_different_cameras():
    people = {"A": np.random.default_rng(0).normal(size=(4, 4)), "B": np.random.default_rng(1).normal(size=(3, 4))}
    mining, _ = _mining_set(people, cameras={"A": [1, 1, 2, 2], "B": [1, 2, 3]})
    first, second = genuine_pairs(mining, limit=1000, seed=0)
    assert len(first) == (4 * 3 // 2 - 2) + 3  # A: six pairs minus the two same-camera ones; B: all three
    for i, j in zip(first, second, strict=True):
        assert mining.records[i].identity == mining.records[j].identity
        assert mining.records[i].camera != mining.records[j].camera


def test_genuine_pairs_are_capped_with_a_reproducible_sample():
    rng = np.random.default_rng(0)
    mining, _ = _mining_set({n: rng.normal(size=(6, 4)) for n in "ABCDE"})
    a = genuine_pairs(mining, limit=20, seed=7)
    b = genuine_pairs(mining, limit=20, seed=7)
    c = genuine_pairs(mining, limit=20, seed=8)
    assert len(a[0]) == 20 and np.array_equal(a[0], b[0]) and not np.array_equal(a[0], c[0])


def test_challenge_measurement_counts_and_labels_the_far_honestly():
    genuine, impostor = np.array([0.9, 0.8, 0.5, 0.3]), np.array([0.85, 0.7, 0.4, 0.2, 0.1])
    out = challenge_measurement(genuine, impostor, 0.6, {"above": 3, "total": 1000})
    assert (out["true_accepts"], out["false_rejects"], out["false_accepts"], out["true_rejects"]) == (2, 2, 2, 3)
    assert out["tar"] == 0.5 and out["far_on_challenge_set"] == 0.4 and out["far_all_pairs_reference"] == 0.003
    assert out["far_on_challenge_set_upper_bound_95"] > 0.4 and "chosen BECAUSE they are hard" in out["note"]


def test_pair_curve_far_and_tar_fall_as_the_threshold_rises():
    rng = np.random.default_rng(0)
    curve = pair_curve(rng.uniform(0.5, 1, 200), rng.uniform(0.2, 0.9, 200))
    far, tar = [p["far"] for p in curve], [p["tar"] for p in curve]
    assert far == sorted(far) and tar == sorted(tar)  # thresholds run high -> low, so both rise
    assert pair_curve(np.zeros(0), np.ones(3)) == []


# ------------------------------------------------------------------------------- failure explanations
OBSERVED = dict(outcome="accepted", top1_score=0.81, threshold=0.80, score_minus_threshold=0.01, margin=0.01, min_margin=None,
                true_identity_rank=None, true_identity_score=None, quality_flags=[], sharpness=50.0, clothing_colour_similarity=0.5)


def test_every_hypothesis_is_labelled_unproven_and_tied_to_a_number():
    for category in ("incorrect_acceptance", "wrong_identity_accepted", "genuine_rejected"):
        for hypothesis in explain_failure(category, OBSERVED, colour_cutoff=0.9):
            assert hypothesis["status"] == HYPOTHESIS_STATUS == "hypothesis - not proven"
            assert hypothesis["evidence"] and hypothesis["text"]


def test_a_barely_accepted_stranger_gets_the_threshold_and_ambiguity_hypotheses():
    causes = {h["cause"] for h in explain_failure("incorrect_acceptance", OBSERVED, colour_cutoff=0.9)}
    assert {"threshold_too_permissive", "ambiguous_ranking"} <= causes


def test_similar_clothing_and_quality_are_reported_separately_from_the_score():
    observed = {**OBSERVED, "score_minus_threshold": 0.2, "margin": 0.3, "clothing_colour_similarity": 0.95,
                "quality_flags": ["blurry"]}
    causes = {h["cause"] for h in explain_failure("incorrect_acceptance", observed, colour_cutoff=0.9)}
    assert causes == {"similar_clothing_colours", "insufficient_image_quality"}


def test_an_unexplained_failure_says_so_instead_of_inventing_a_cause():
    observed = {**OBSERVED, "score_minus_threshold": 0.3, "margin": 0.4, "clothing_colour_similarity": 0.1}
    (only,) = explain_failure("incorrect_acceptance", observed, colour_cutoff=0.9)
    assert only["cause"] == "model_or_dataset_limitation" and "No simple cause" in only["text"]


def test_a_narrowly_rejected_enrolled_person_is_flagged_but_a_review_item_is_not_called_too_strict():
    rejected = {**OBSERVED, "outcome": "unknown", "score_minus_threshold": -0.02, "true_identity_rank": 1, "true_identity_score": 0.78}
    assert "threshold_too_strict" in {h["cause"] for h in explain_failure("genuine_rejected", rejected, colour_cutoff=0.9)}
    review = {**OBSERVED, "outcome": "review_required", "score_minus_threshold": 0.05, "margin": 0.01, "min_margin": 0.05,
              "true_identity_rank": 1, "true_identity_score": 0.85}
    causes = {h["cause"] for h in explain_failure("genuine_rejected", review, colour_cutoff=0.9)}
    assert "ambiguous_ranking" in causes and "threshold_too_strict" not in causes


# ------------------------------------------------------------------------------- the whole experiment
def test_a_run_has_every_section_and_labels_what_it_is(toy, tmp_path):
    result = run(toy, tmp_path)
    assert result["kind"] == "lookalike" and result["metadata"]["experiment_id"] == "exp-1"
    assert result["metadata"]["is_benchmark"] is True and result["warnings"] == []
    assert {"challenge_set", "models", "failures", "sandbox", "limitations", "comparison"} <= set(result)
    definition = result["challenge_set"]["definition"]
    assert "similar EMBEDDINGS" in definition["model_vs_clothing"] and definition["identities_searched"] > 0
    counts = result["challenge_set"]["counts"]
    assert 0 < counts["impostor_comparisons"] <= 10 * 2 and counts["genuine_comparisons"] > 0
    assert any("selected by the baseline model" in text for text in result["limitations"])


def test_listed_pairs_are_different_people_ranked_most_alike_first_with_their_decision(toy, tmp_path):
    pairs = run(toy, tmp_path)["challenge_set"]["identity_pairs"]
    assert pairs and [p["similarity"] for p in pairs] == sorted((p["similarity"] for p in pairs), reverse=True)
    for pair in pairs:
        assert pair["identity_a"] != pair["identity_b"] and pair["comparison_type"] == "different_identities"
        assert pair["split"] == "test" and pair["by_model"]["baseline"]["decision"] in ("false_accept", "correct_reject")
        assert isinstance(pair["similar_clothing_proxy"], bool) and 0 <= pair["clothing_colour_similarity"] <= 1.0001


def test_the_challenge_set_is_harder_than_all_pairs(toy, tmp_path):
    challenge = run(toy, tmp_path)["models"]["baseline"]["challenge"]
    assert challenge["far_on_challenge_set"] >= challenge["far_all_pairs_reference"]
    assert challenge["all_pairs_compared"] > challenge["impostor_pairs"]


def test_the_threshold_is_chosen_on_calibration_people_so_the_mined_split_cannot_change_it(toy, tmp_path):
    rules = {split: run(toy, tmp_path / split, request_for(toy, mining_split=split))["models"]["baseline"]["rule"]
             for split in ("dev", "calibration", "test")}
    assert rules["dev"] == rules["calibration"] == rules["test"]


def test_the_mined_split_is_what_the_pairs_come_from(toy, tmp_path):
    protocol = build_protocol(load_records(toy), PROTOCOL)
    for split, expected in (("dev", protocol.dev_ids),
                            ("test", {r.identity for r in protocol.test.gallery + protocol.test.known_queries + protocol.test.unknown_queries})):
        pairs = run(toy, tmp_path / split, request_for(toy, mining_split=split))["challenge_set"]["identity_pairs"]
        assert {p["identity_a"] for p in pairs} | {p["identity_b"] for p in pairs} <= expected


def test_failures_have_observed_facts_and_unproven_hypotheses_and_counts_cover_all(toy, tmp_path):
    result = run(toy, tmp_path, request_for(toy, target=OperatingTarget("fixed_recall", target_recall=0.9)))
    failures = result["failures"]["baseline"]
    counts = failures["counts"]
    assert counts["queries"] > 0 and "hypotheses" in failures["note"]
    listed = failures["listed"]
    assert len(listed) <= 3 * 5
    assert len(listed) == sum(min(counts[c], 5) for c in ("incorrect_acceptance", "wrong_identity_accepted", "genuine_rejected"))
    for item in listed:
        assert item["observed"]["threshold"] == failures["rule"]["threshold"]
        assert item["possible_causes"] and all(c["status"] == HYPOTHESIS_STATUS for c in item["possible_causes"])
        if item["category"] == "incorrect_acceptance":
            assert item["query"]["is_known"] is False and item["observed"]["outcome"] == "accepted"
        if item["category"] == "genuine_rejected":
            assert item["query"]["is_known"] is True and item["observed"]["outcome"] != "accepted"


def test_without_a_checkpoint_the_improved_model_is_reported_unavailable_not_invented(toy, tmp_path):
    result = run(toy, tmp_path)
    improved = result["models"]["improved"]
    assert improved["status"] == "unavailable" and "No fine-tuned checkpoint" in improved["reason"]
    assert result["comparison"] is None
    assert any("no claim that any training method improves" in text for text in result["limitations"])


def test_a_checkpoint_trained_on_the_evaluated_people_is_refused(toy, tmp_path):
    protocol = build_protocol(load_records(toy), PROTOCOL)
    everyone = {r.identity for r in load_records(toy)}
    checkpoint = write_checkpoint(tmp_path / "ft", everyone)
    result = run(toy, tmp_path, request_for(toy, finetuned_checkpoint=checkpoint), tuned=FakeExtractor(seed=3))
    assert result["models"]["improved"]["status"] == "unavailable" and "LEAKAGE" in result["models"]["improved"]["reason"]
    assert protocol.dev_ids  # (the dev people exist; the guard looked at calibration/test people)


def test_the_dev_split_never_compares_a_fine_tuned_model_on_its_own_training_people(toy, tmp_path):
    protocol = build_protocol(load_records(toy), PROTOCOL)
    checkpoint = write_checkpoint(tmp_path / "ft", protocol.dev_ids)
    result = run(toy, tmp_path, request_for(toy, finetuned_checkpoint=checkpoint, mining_split="dev"), tuned=FakeExtractor(seed=3))
    assert result["models"]["improved"]["status"] == "unavailable" and "memorisation" in result["models"]["improved"]["reason"]


def test_a_clean_checkpoint_is_compared_on_the_very_same_pairs_each_at_its_own_threshold(toy, tmp_path):
    protocol = build_protocol(load_records(toy), PROTOCOL)
    checkpoint = write_checkpoint(tmp_path / "ft", protocol.dev_ids)
    tuned = FakeExtractor(noise=0.05, seed=3)
    tuned.weights_sha256 = "1" * 64  # a real fine-tuned model hashes its own checkpoint, so it gets its own embedding cache
    result = run(toy, tmp_path, request_for(toy, finetuned_checkpoint=checkpoint), tuned=tuned)
    baseline, improved = result["models"]["baseline"], result["models"]["improved"]
    assert improved["status"] == "ok"
    assert baseline["challenge"]["impostor_pairs"] == improved["challenge"]["impostor_pairs"]  # identical examples
    assert baseline["challenge"]["genuine_pairs"] == improved["challenge"]["genuine_pairs"]
    rows = {row["model"]: row for row in result["comparison"]}
    assert set(rows) == {"baseline", "improved"} and rows["baseline"]["threshold"] != rows["improved"]["threshold"]
    for pair in result["challenge_set"]["identity_pairs"]:
        assert set(pair["by_model"]) == {"baseline", "improved"}


def test_same_seed_gives_the_same_experiment(toy, tmp_path):
    def stable(result):
        text = json.dumps(result, sort_keys=True, default=str)
        data = json.loads(text)
        data["metadata"].pop("started_at"), data["metadata"].pop("duration_seconds"), data["metadata"].pop("software")
        for model in data["models"].values():
            model.pop("latency", None), model.pop("model", None)
        return data

    first, second = run(toy, tmp_path / "a"), run(toy, tmp_path / "b")
    assert stable(first) == stable(second)


def test_the_experiment_can_be_cancelled(toy, tmp_path):
    with pytest.raises(EvaluationCancelled):
        run(toy, tmp_path, cancelled=lambda: True)


def test_an_unknown_mining_split_is_refused(toy, tmp_path):
    with pytest.raises(ValueError, match="mining_split"):
        run(toy, tmp_path, replace(request_for(toy), mining_split="validation"))


def test_smoke_datasets_are_never_presented_as_benchmarks(tmp_path):
    info = inspect_dataset(make_dataset(tmp_path / "smoke", kind="smoke_test"))
    result = run(info, tmp_path)
    assert result["metadata"]["is_benchmark"] is False
    assert "NOT benchmark results" in result["warnings"][0]
    assert any("not a public benchmark" in text for text in result["limitations"])


def test_an_unreachable_target_is_warned_about_not_hidden(toy, tmp_path):
    noisy = FakeExtractor(noise=5.0)  # pure noise: nothing separable
    result = run_lookalike(toy, request_for(toy, target=OperatingTarget("fixed_recall", target_recall=0.99)), cache_dir=tmp_path / "c",
                           make_extractor=factory(noisy))
    assert any("could not reach the requested operating point" in w for w in result["warnings"])
    assert result["models"]["baseline"]["calibration"]["target_achieved"] is False
