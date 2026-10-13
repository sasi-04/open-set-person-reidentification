"""Similarity, top-k ranking and the in-memory gallery index (controlled synthetic embeddings)."""

import numpy as np
import pytest

from app.cv.retrieval.gallery_index import GalleryIndex, IndexEntry
from app.cv.retrieval.ranking import best_score_per_identity, cosine_similarity, rank_identities


def unit(*values: float) -> np.ndarray:
    vector = np.asarray(values, dtype=np.float32)
    return vector / np.linalg.norm(vector)


def test_cosine_similarity_known_values():
    q = np.stack([unit(1, 0), unit(1, 1)])
    r = np.stack([unit(1, 0), unit(0, 1), unit(-1, 0)])
    similarity = cosine_similarity(q, r)
    assert similarity.shape == (2, 3)
    np.testing.assert_allclose(similarity[0], [1.0, 0.0, -1.0], atol=1e-6)
    np.testing.assert_allclose(similarity[1], [0.7071, 0.7071, -0.7071], atol=1e-4)


def test_cosine_similarity_rejects_mismatched_dimensions():
    with pytest.raises(ValueError):
        cosine_similarity(np.ones((1, 4), dtype=np.float32), np.ones((2, 5), dtype=np.float32))


def test_identity_score_is_the_best_of_its_images():
    # identity 0 owns columns 0-1, identity 1 owns columns 2-4
    sims = np.array([[0.2, 0.9, 0.5, 0.4, 0.6]])
    scores = best_score_per_identity(sims, np.array([0, 2]))
    np.testing.assert_allclose(scores, [[0.9, 0.6]])


def test_top_k_is_sorted_best_first_and_clamped():
    scores = np.array([[0.1, 0.9, 0.5, 0.7]])
    order, values = rank_identities(scores, k=3)
    assert order.tolist() == [[1, 3, 2]]
    np.testing.assert_allclose(values, [[0.9, 0.7, 0.5]])
    order_all, _ = rank_identities(scores, k=99)  # k larger than gallery -> all identities
    assert order_all.shape == (1, 4)


def test_ties_are_broken_by_gallery_order():
    order, _ = rank_identities(np.array([[0.5, 0.5, 0.5]]), k=3)
    assert order.tolist() == [[0, 1, 2]]


def build_index() -> GalleryIndex:
    index = GalleryIndex(dim=3)
    index.replace(
        [
            IndexEntry("alice", "a1", unit(1, 0, 0)),
            IndexEntry("alice", "a2", unit(0.9, 0.1, 0)),
            IndexEntry("bob", "b1", unit(0, 1, 0)),
            IndexEntry("carol", "c1", unit(0, 0, 1)),
        ]
    )
    return index


def test_index_search_returns_ranked_identities_with_best_reference_image():
    index = build_index()
    results = index.search(unit(1, 0.05, 0), top_k=3)
    assert [c.reference_id for c in results] == ["alice", "bob", "carol"]
    assert results[0].rank == 1 and results[0].n_images == 2
    assert results[0].best_image_uid == "a1"  # a1 is closer to the query than a2
    assert results[0].score > results[1].score > results[2].score - 1e-9


def test_empty_index_returns_no_candidates():
    assert GalleryIndex(dim=3).search(unit(1, 0, 0), top_k=5) == []


def test_replace_bumps_version_so_caches_can_invalidate():
    index = build_index()
    before = index.snapshot.version
    index.replace([IndexEntry("zed", "z1", unit(1, 1, 1))])
    assert index.snapshot.version == before + 1
    assert index.snapshot.reference_ids == ("zed",)


def test_dimension_mismatch_is_rejected():
    index = GalleryIndex(dim=3)
    with pytest.raises(ValueError):
        index.replace([IndexEntry("x", "x1", unit(1, 0))])
