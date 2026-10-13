"""
Metric-learning code, batch-norm folding, the fine-tune leakage guard, and the REAL pretrained model.

The first groups use tiny synthetic data (fast, deterministic). The last group loads the real OSNet-AIN
weights from backend/weights/ and is skipped automatically when they have not been downloaded.
"""

from __future__ import annotations

import copy

import numpy as np
import pytest
import torch

from app.core.config import Settings
from app.core.errors import ModelUnavailable
from app.cv.embedding.extractor import OSNetExtractor
from app.cv.embedding.optimize import fold_batch_norm
from app.cv.embedding.osnet_ain import OSNetAIN
from app.cv.embedding.registry import EMBEDDING_MODELS, get_spec
from app.cv.embedding.weights import load_state_dict, read_checkpoint_metadata
from app.evaluation.datasets import inspect_dataset, load_records
from app.evaluation.protocol import ProtocolConfig, build_protocol
from app.evaluation.runner import EvaluationRequest, _finetuned_problem
from app.training.finetune import FineTuneConfig, finetune, select_training_records
from app.training.triplet import PKBatchSampler, batch_hard_triplet_loss
from tests.test_evaluation_pipeline import make_dataset


# ------------------------------------------------------------------------ triplet loss
def test_batch_hard_loss_picks_the_hardest_positive_and_hardest_negative():
    # Person A: a1=(1,0), a2=(0.8,0.6) -> distance 0.2.  Person B: b1=(0.9,0.436) is very close to a1.
    embeddings = torch.tensor([[1.0, 0.0], [0.8, 0.6], [0.9, 0.436]])
    labels = torch.tensor([0, 0, 1])
    loss, stats = batch_hard_triplet_loss(embeddings, labels, margin=0.3)
    # The only anchors with a positive are the two photos of person A.
    # For a1: hardest positive = a2 (dist 0.2); hardest negative = b1 (dist ~ 0.0)  -> violates the margin.
    assert stats.active_fraction == 1.0
    assert stats.mean_positive_distance == pytest.approx(0.2, abs=1e-3)
    assert float(loss) > 0.3  # positive was farther than the negative: loss exceeds the margin itself


def test_loss_is_zero_when_people_are_well_separated():
    embeddings = torch.tensor([[1.0, 0.0], [0.99, 0.01], [-1.0, 0.0], [-0.99, 0.01]])
    labels = torch.tensor([0, 0, 1, 1])
    loss, stats = batch_hard_triplet_loss(embeddings, labels, margin=0.3)
    assert float(loss) == pytest.approx(0.0, abs=1e-6) and stats.active_fraction == 0.0


def test_loss_has_gradients_and_rejects_batches_without_triplets():
    embeddings = torch.randn(8, 16, requires_grad=True)
    loss, _ = batch_hard_triplet_loss(embeddings, torch.tensor([0, 0, 1, 1, 2, 2, 3, 3]))
    loss.backward()
    assert torch.isfinite(embeddings.grad).all() and embeddings.grad.abs().sum() > 0
    with pytest.raises(ValueError, match="no valid triplets"):
        batch_hard_triplet_loss(torch.randn(4, 8), torch.tensor([0, 1, 2, 3]))  # nobody has a positive


# --------------------------------------------------------------------------- P x K sampler
def test_sampler_builds_p_by_k_batches_and_is_reproducible():
    labels = [i // 6 for i in range(60)]  # 10 people x 6 photos
    batches = list(PKBatchSampler(labels, 4, 3, batches_per_epoch=5, seed=1))
    assert len(batches) == 5
    for batch in batches:
        assert len(batch) == 12 and len({labels[i] for i in batch}) == 4
        assert all(sum(labels[i] == p for i in batch) == 3 for p in {labels[i] for i in batch})
    assert batches == list(PKBatchSampler(labels, 4, 3, batches_per_epoch=5, seed=1))
    assert batches != list(PKBatchSampler(labels, 4, 3, batches_per_epoch=5, seed=2))


def test_sampler_handles_people_with_few_photos_and_too_few_people():
    labels = [0, 0, 1, 1, 2, 2, 3]  # person 3 has a single photo
    for batch in PKBatchSampler(labels, 4, 2, batches_per_epoch=3, seed=0):
        assert len(batch) == 8  # still full batches (photos repeat for the person with one)
    with pytest.raises(ValueError):
        PKBatchSampler(labels, 6, 2, batches_per_epoch=1)


# ---------------------------------------------------------------- batch-norm folding
def random_osnet(name="osnet_ain_x0_25", seed=0) -> OSNetAIN:
    torch.manual_seed(seed)
    spec = get_spec(name)
    model = OSNetAIN(spec.channels, spec.feature_dim)
    for module in model.modules():  # give batch-norm non-trivial statistics so folding is actually tested
        if isinstance(module, (torch.nn.BatchNorm2d, torch.nn.BatchNorm1d)):
            module.running_mean.normal_(0, 0.3)
            module.running_var.uniform_(0.5, 2.0)
            module.weight.data.uniform_(0.5, 1.5)
            module.bias.data.normal_(0, 0.2)
    return model.eval()


def test_folding_batch_norm_does_not_change_the_embedding():
    model = random_osnet()
    folded = copy.deepcopy(model)
    pairs = fold_batch_norm(folded)
    assert pairs > 30
    x = torch.randn(4, 3, 256, 128)
    with torch.inference_mode():
        before, after = model(x), folded(x)
    assert torch.allclose(before, after, atol=1e-3, rtol=1e-3)
    assert torch.nn.functional.cosine_similarity(before, after).min() > 0.99999


def test_folding_needs_eval_mode():
    with pytest.raises(RuntimeError):
        fold_batch_norm(random_osnet().train())


# --------------------------------------------------------- fine-tuning and its leakage guard
@pytest.fixture()
def toy(tmp_path):
    info = inspect_dataset(make_dataset(tmp_path / "toy", identities=40, images=6))
    return info, load_records(info)


def test_finetune_trains_only_the_chosen_layers_and_records_who_it_saw(toy, tmp_path):
    info, records = toy
    spec = get_spec("osnet_ain_x0_25")
    base = random_osnet(seed=3)
    base_state = {k: v.clone() for k, v in base.state_dict().items()}
    protocol = build_protocol(records, ProtocolConfig(seed=0, dev_fraction=0.5, calibration_fraction=0.2))
    config = FineTuneConfig(dataset=info.name, seed=0, epochs=1, batches_per_epoch=2, people_per_batch=4, photos_per_person=2, trainable="head")
    output = tmp_path / "ft" / "toy.pt"
    meta = finetune(spec, tmp_path, records, protocol.dev_ids, config, output, base_state=base_state)

    assert output.is_file() and output.with_suffix(".json").is_file()
    assert set(meta["dev_identities"]) <= protocol.dev_ids  # trained on development people ONLY
    assert not set(meta["dev_identities"]) & {r.identity for r in protocol.test.gallery + protocol.test.known_queries}
    assert meta["validated"] is False and "training loss only" in meta["note"].lower()

    saved = load_state_dict(output)  # the standard safe loader accepts our checkpoint format
    changed = {k for k in saved if not torch.equal(saved[k], base_state[k])}
    assert changed and all(k.startswith(("conv4.", "conv5.", "fc.")) for k in changed)  # earlier layers untouched
    assert read_checkpoint_metadata(output)["dev_identities"] == meta["dev_identities"]


def test_finetune_refuses_a_dataset_with_too_few_people(toy, tmp_path):
    info, records = toy
    config = FineTuneConfig(dataset=info.name, people_per_batch=4, max_identities=5)
    with pytest.raises(Exception, match="development identities"):
        finetune(get_spec("osnet_ain_x0_25"), tmp_path, records, {r.identity for r in records}, config, tmp_path / "x.pt", base_state=random_osnet().state_dict())


def test_training_photos_are_restricted_to_development_people(toy):
    info, records = toy
    dev = {r.identity for r in records[:60]}
    chosen = select_training_records(records, dev, FineTuneConfig(dataset=info.name, max_images_per_identity=3))
    assert {r.identity for r in chosen} <= dev
    assert max(sum(1 for r in chosen if r.identity == p) for p in dev) <= 3


def checkpoint_with(tmp_path, dev_identities, dataset="toy", name="ck.pt"):
    path = tmp_path / name
    torch.save({"state_dict": {}, "meta": {"dev_identities": list(dev_identities), "config": {"dataset": dataset}}}, path)
    return path


def test_evaluation_refuses_a_checkpoint_trained_on_its_test_people(toy, tmp_path):
    info, records = toy
    protocol = build_protocol(records, ProtocolConfig(seed=0))
    leaked = sorted({r.identity for r in protocol.test.known_queries})[:3]
    request = EvaluationRequest(dataset=info.name, finetuned_checkpoint=checkpoint_with(tmp_path, protocol.dev_ids | set(leaked)))
    problem = _finetuned_problem(request, info, {0: protocol})
    assert problem and problem.startswith("LEAKAGE") and leaked[0] in problem


def test_evaluation_accepts_a_checkpoint_trained_only_on_development_people(toy, tmp_path):
    info, records = toy
    protocol = build_protocol(records, ProtocolConfig(seed=0))
    request = EvaluationRequest(dataset=info.name, finetuned_checkpoint=checkpoint_with(tmp_path, protocol.dev_ids))
    assert _finetuned_problem(request, info, {0: protocol}) is None


def test_checkpoint_from_another_seed_is_refused_because_its_people_overlap(toy, tmp_path):
    info, records = toy
    seed0, seed1 = (build_protocol(records, ProtocolConfig(seed=s)) for s in (0, 1))
    request = EvaluationRequest(dataset=info.name, seeds=(1,), finetuned_checkpoint=checkpoint_with(tmp_path, seed0.dev_ids))
    assert "LEAKAGE" in (_finetuned_problem(request, info, {1: seed1}) or "")


@pytest.mark.parametrize("meta,fragment", [({}, "does not record"), ({"dev_identities": ["x"], "config": {"dataset": "other"}}, "trained on dataset")])
def test_checkpoints_without_provenance_or_from_another_dataset_are_refused(toy, tmp_path, meta, fragment):
    info, records = toy
    path = tmp_path / "meta.pt"
    torch.save({"state_dict": {}, "meta": meta}, path)
    protocol = build_protocol(records, ProtocolConfig(seed=0))
    problem = _finetuned_problem(EvaluationRequest(dataset=info.name, finetuned_checkpoint=path), info, {0: protocol})
    assert problem and fragment in problem


def test_missing_or_absent_checkpoint_is_reported(toy, tmp_path):
    info, records = toy
    protocol = build_protocol(records, ProtocolConfig(seed=0))
    assert "No fine-tuned checkpoint" in _finetuned_problem(EvaluationRequest(dataset=info.name), info, {0: protocol})
    assert "does not exist" in _finetuned_problem(EvaluationRequest(dataset=info.name, finetuned_checkpoint=tmp_path / "nope.pt"), info, {0: protocol})


# ---------------------------------------------------- incompatible weights / registry
def test_weights_that_do_not_fit_the_architecture_are_rejected(tmp_path):
    wrong = tmp_path / "wrong.pt"
    torch.save({"conv1.conv.weight": torch.zeros(3, 3)}, wrong)
    with pytest.raises(ModelUnavailable, match="do not fit"):
        OSNetExtractor.load(get_spec("osnet_ain_x0_25"), tmp_path, torch.device("cpu"), checkpoint=wrong)


def test_every_registered_model_has_a_pinned_hash_and_one_embedding_size():
    for spec in EMBEDDING_MODELS.values():
        assert len(spec.weights.sha256) == 64 and spec.weights.url.startswith("https://")
        assert spec.feature_dim == 512  # one place defines the embedding dimension
        assert OSNetAIN(spec.channels, spec.feature_dim).eval()(torch.zeros(1, 3, 256, 128)).shape == (1, 512)


# -------------------------------------------------- the REAL pretrained model (skipped without weights)
WEIGHTS_PRESENT = (Settings(_env_file=None).weights_dir / get_spec("osnet_ain_x1_0").weights.filename).is_file()
real = pytest.mark.skipif(not WEIGHTS_PRESENT, reason="official weights not downloaded (run scripts/download_weights.py)")


@pytest.fixture(scope="module")
def real_extractor():
    settings = Settings(_env_file=None)
    return OSNetExtractor.load(get_spec("osnet_ain_x1_0"), settings.weights_dir, torch.device("cpu"), batch_size=8)


def random_crops(n=4, seed=0):
    rng = np.random.default_rng(seed)
    return [rng.integers(0, 255, (160 + 10 * i, 70, 3), dtype=np.uint8) for i in range(n)]


@real
def test_real_model_produces_512_dim_unit_length_deterministic_embeddings(real_extractor):
    crops = random_crops()
    first, second = real_extractor.embed(crops), real_extractor.embed(crops)
    assert first.shape == (4, 512) and first.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(first, axis=1), 1.0, atol=1e-4)
    np.testing.assert_array_equal(first, second)
    assert np.isfinite(first).all()
    assert float(first[0] @ first[1]) < 0.9999  # different inputs give different embeddings


@real
def test_real_model_is_verified_and_reports_its_provenance(real_extractor):
    info = real_extractor.info()
    assert info["weights_verified_against_pinned_hash"] is True
    assert info["embedding_dim"] == 512 and info["input_size"] == [256, 128]
    assert "MIT" in info["weights_license"] and info["weights_source"].startswith("https://huggingface.co/")
    assert info["optimisations"] == []  # batch-norm folding is opt-in: the default model is the plain, verified network
    assert info["warmup_seconds"] >= 0 and info["load_seconds"] > 0  # measured separately from request time


@real
def test_folded_real_model_matches_the_unfolded_one():
    settings = Settings(_env_file=None)
    spec = get_spec("osnet_ain_x1_0")
    folded = OSNetExtractor.load(spec, settings.weights_dir, torch.device("cpu"), fold_bn=True)
    plain = OSNetExtractor.load(spec, settings.weights_dir, torch.device("cpu"), fold_bn=False)
    crops = random_crops(3, seed=5)
    similarity = (folded.embed(crops) * plain.embed(crops)).sum(axis=1)
    assert similarity.min() > 0.99999
    assert not plain.info()["optimisations"] and folded.info()["optimisations"]


@real
def test_flip_augmentation_changes_the_embedding_but_keeps_it_normalised():
    settings = Settings(_env_file=None)
    spec = get_spec("osnet_ain_x1_0")
    normal = OSNetExtractor.load(spec, settings.weights_dir, torch.device("cpu"), use_flip_tta=False)
    flipped = OSNetExtractor.load(spec, settings.weights_dir, torch.device("cpu"), use_flip_tta=True)
    crops = random_crops(2, seed=9)
    a, b = normal.embed(crops), flipped.embed(crops)
    np.testing.assert_allclose(np.linalg.norm(b, axis=1), 1.0, atol=1e-4)
    assert not np.allclose(a, b, atol=1e-4)
    assert normal.fingerprint != flipped.fingerprint  # so cached embeddings are never mixed


@real
def test_real_model_rejects_unusable_crops(real_extractor):
    from app.core.errors import ProcessingFailed

    with pytest.raises(ProcessingFailed):
        real_extractor.embed([np.zeros((1, 1, 3), dtype=np.uint8)])
    assert real_extractor.embed([]).shape == (0, 512)
