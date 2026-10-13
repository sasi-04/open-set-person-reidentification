"""
A broken fingerprint is an ERROR, never an "unknown person".

The brief asks for explicit tests of invalid, wrong-size and zero-length embeddings. They are checked at the door of the
search (``cv/retrieval/validation.py``), end to end through the API (a PROCESSING ERROR for that person, others unaffected),
for video frames, and for reference embeddings that were damaged in storage.
"""

from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy import select

from app.cv.retrieval.gallery_index import GalleryIndex, IndexEntry
from app.cv.retrieval.validation import InvalidEmbedding, check_embedding
from app.db.models import ReferenceImage
from tests.fakes import BLUE, RED, detection, scene_png

DIM = 16


def unit(seed: int = 0) -> np.ndarray:
    vector = np.random.default_rng(seed).normal(size=DIM).astype(np.float32)
    return vector / np.linalg.norm(vector)


# ---------------------------------------------------------------------------- the check itself
def test_a_proper_embedding_passes_unchanged():
    vector = unit()
    assert np.array_equal(check_embedding(vector, DIM), vector)


@pytest.mark.parametrize("vector, fragment", [
    (np.array([np.nan] + [0.0] * (DIM - 1), dtype=np.float32), "NaN or infinite"),
    (np.array([np.inf] + [0.0] * (DIM - 1), dtype=np.float32), "NaN or infinite"),
    (np.zeros(DIM, dtype=np.float32), "zero length"),
    (unit() * 3.0, "not normalised"),
    (unit() * 0.5, "not normalised"),
    (np.ones(DIM + 1, dtype=np.float32) / np.sqrt(DIM + 1), "different model"),
    (np.ones(3, dtype=np.float32) / np.sqrt(3), "different model"),
    (np.stack([unit(1), unit(2)]), "single vector"),
    (np.array(["a"] * DIM), "not numbers"),
])
def test_each_kind_of_broken_embedding_is_refused_with_its_own_reason(vector, fragment):
    with pytest.raises(InvalidEmbedding) as raised:
        check_embedding(vector, DIM)
    assert fragment in raised.value.message and raised.value.code == "invalid_embedding"


def test_the_search_refuses_a_broken_query_even_when_the_gallery_is_empty():
    index = GalleryIndex(dim=DIM)
    for bad in (np.zeros(DIM, dtype=np.float32), np.full(DIM, np.nan, dtype=np.float32), np.ones(DIM + 4, dtype=np.float32) / 4):
        with pytest.raises(InvalidEmbedding):
            index.search(bad, 3)
    assert index.search(unit(), 3) == []  # a GOOD query against nobody is simply an empty ranking


def test_the_search_still_ranks_good_queries():
    index = GalleryIndex(dim=DIM)
    index.replace([IndexEntry("a", "u1", unit(1)), IndexEntry("b", "u2", unit(2))])
    ranked = index.search(unit(1), 2)
    assert [c.reference_id for c in ranked] == ["a", "b"] and ranked[0].score == pytest.approx(1.0, abs=1e-5)


# ---------------------------------------------------------------------------- through the API
def test_a_broken_embedding_is_a_processing_error_for_that_person_not_an_unknown(env):
    env.enroll("p-red", RED)
    env.extractor.embed = lambda crops: np.zeros((len(crops), DIM), dtype=np.float32)  # the "model" returns nothing useful
    env.detector.boxes = [detection(80, 40, 220, 360)]
    response = env.predict(scene_png(RED), mode="all")
    assert response.status_code == 200
    person = response.json()["people"][0]
    assert person["decision"]["outcome"] == "processing_error" and person["decision"]["reason_code"] == "invalid_embedding"
    assert "zero length" in person["decision"]["reason"] and person["candidates"] == []
    assert person["decision"]["accepted_reference_id"] is None


def test_one_broken_person_does_not_spoil_the_others_in_the_same_photo(env):
    env.enroll("p-red", RED)
    real = env.extractor.embed

    def half_broken(crops):
        vectors = real(crops)
        vectors[1] = 0.0  # only the second person's fingerprint is broken
        return vectors

    env.extractor.embed = half_broken
    env.detector.boxes = [detection(10, 40, 140, 360), detection(160, 40, 290, 360)]
    people = env.predict(scene_png(RED), mode="all").json()["people"]
    assert [p["decision"]["outcome"] for p in people] == ["accepted", "processing_error"]
    history = env.get("/api/reid/history").json()["items"][0]
    assert history["outcomes"] == {"accepted": 1, "processing_error": 1}  # recorded honestly, not as "unknown"


def test_a_good_query_with_an_empty_gallery_is_still_just_unknown(env):
    env.detector.boxes = [detection(80, 40, 220, 360)]
    person = env.predict(scene_png(RED), mode="all").json()["people"][0]
    assert person["decision"]["outcome"] == "unknown" and person["decision"]["reason_code"] == "empty_gallery"


# ---------------------------------------------------------------------------- damaged storage
def _damage(env, reference_id: str, blob: bytes) -> None:
    with env.runtime.session_factory() as session:
        for image in session.scalars(select(ReferenceImage)):
            image.embedding = blob
        session.commit()


@pytest.mark.parametrize("blob", [np.full(DIM, np.nan, dtype=np.float32).tobytes(), np.zeros(DIM, dtype=np.float32).tobytes(),
                                  b"\x01\x02\x03", np.ones(DIM + 3, dtype=np.float32).tobytes()],
                         ids=["nan", "zero-norm", "truncated", "wrong-size"])
def test_a_damaged_stored_reference_is_set_aside_and_marked_failed_instead_of_poisoning_the_search(env, blob):
    env.enroll("p-red", RED)
    env.enroll("p-blue", BLUE)
    with env.runtime.session_factory() as session:
        red = session.scalars(select(ReferenceImage).join(ReferenceImage.identity).where(ReferenceImage.identity.has(reference_id="p-red"))).all()
        for image in red:
            image.embedding = blob
        session.commit()

    with env.runtime.session_factory() as session:
        env.runtime.sync_gallery(session)  # what start-up and "Rebuild embeddings" do
        session.commit()
        statuses = {i.identity.reference_id: i.embedding_status for i in session.scalars(select(ReferenceImage))}
    assert statuses["p-red"] == "failed" and statuses["p-blue"] == "ready"
    assert env.runtime.index.snapshot.reference_ids == ("p-blue",)  # the damaged one is not searched; the healthy one still is

    env.detector.boxes = [detection(80, 40, 220, 360)]
    person = env.predict(scene_png(BLUE), mode="all").json()["people"][0]
    assert person["decision"]["outcome"] == "accepted" and person["decision"]["accepted_reference_id"] == "p-blue"
    detail = env.get("/api/gallery").json()
    assert {i["reference_id"]: i["embedding_status"] for i in detail["items"]}["p-red"] == "failed"


def test_a_failed_reference_can_be_repaired_by_rebuilding_its_embeddings(env):
    env.enroll("p-red", RED)
    _damage(env, "p-red", np.zeros(DIM, dtype=np.float32).tobytes())
    with env.runtime.session_factory() as session:
        env.runtime.sync_gallery(session)
        session.commit()
    assert env.runtime.index.snapshot.n_identities == 0
    assert env.post("/api/gallery/rebuild", role="operator").status_code == 200
    assert env.runtime.index.snapshot.reference_ids == ("p-red",)  # re-embedded from the stored crop


# ---------------------------------------------------------------------------- video frames
def test_a_broken_embedding_in_a_video_frame_is_a_processing_error_not_unknown(env, tmp_path):
    from tests.test_api_lab_and_video import upload, wait_for, write_avi

    env.enroll("p-red", RED)
    env.extractor.embed = lambda crops: np.full((len(crops), DIM), np.nan, dtype=np.float32)
    env.detector.boxes = [detection(110, 20, 210, 220)]
    clip = write_avi(tmp_path / "c.avi", [RED] * 10)
    job = wait_for(env, f"/api/video/jobs/{upload(env, clip).json()['run_id']}")
    assert job["status"] == "succeeded"
    person = job["result"]["frames"][0]["people"][0]
    assert person["outcome"] == "processing_error" and person["reason_code"] == "invalid_embedding"
    assert job["result"]["summary"]["outcomes"] == {"processing_error": 2}  # two sampled frames, both honestly errors
    assert job["result"]["summary"]["identities_seen"] == []
