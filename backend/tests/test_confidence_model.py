"""Calibrated-confidence (logistic) model on controlled synthetic data."""

import numpy as np
import pytest

from app.cv.open_set.confidence import ConfidenceModel


def synthetic(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    correct = rng.random(n) < 0.5
    similarity = np.where(correct, rng.normal(0.8, 0.07, n), rng.normal(0.55, 0.10, n))
    margin = np.where(correct, rng.normal(0.25, 0.08, n), rng.normal(0.05, 0.05, n)).clip(0, 1)
    return similarity, margin, correct


def test_fitted_confidence_is_higher_for_clearly_correct_matches():
    similarity, margin, correct = synthetic()
    model = ConfidenceModel.fit(similarity, margin, correct, fitted_on="synthetic")
    assert model.predict(0.9, 0.3) > 0.9
    assert model.predict(0.45, 0.02) < 0.1
    assert 0.0 < model.predict(0.7, 0.1) < 1.0


def test_confidence_is_roughly_calibrated_on_its_own_training_data():
    similarity, margin, correct = synthetic(seed=1)
    model = ConfidenceModel.fit(similarity, margin, correct, fitted_on="synthetic")
    p = model.predict_many(similarity, margin)
    # Mean predicted probability should match the observed positive rate.
    assert abs(p.mean() - correct.mean()) < 0.02


def test_margin_unavailable_means_no_confidence():
    similarity, margin, correct = synthetic()
    model = ConfidenceModel.fit(similarity, margin, correct, fitted_on="synthetic")
    assert model.predict(0.9, None) is None


def test_fit_refuses_degenerate_data():
    with pytest.raises(ValueError):
        ConfidenceModel.fit(np.linspace(0, 1, 50), np.linspace(0, 1, 50), np.ones(50, dtype=bool), fitted_on="x")
    with pytest.raises(ValueError):
        ConfidenceModel.fit(np.array([0.5]), np.array([0.1]), np.array([True]), fitted_on="x")


def test_round_trip_serialisation():
    similarity, margin, correct = synthetic(500)
    model = ConfidenceModel.fit(similarity, margin, correct, fitted_on="synthetic")
    clone = ConfidenceModel.from_dict(model.to_dict())
    assert clone == model
    assert clone.predict(0.7, 0.1) == model.predict(0.7, 0.1)
