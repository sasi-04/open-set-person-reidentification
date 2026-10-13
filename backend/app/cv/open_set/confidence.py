"""
Turning similarity scores into a calibrated confidence.

In plain words: a cosine similarity of 0.78 is not "78% sure". To say anything
probabilistic we must MEASURE how often matches with such scores were really
correct. This module fits a tiny logistic-regression model on held-out
calibration data:

    confidence = P( the top-1 candidate is the right enrolled person | top-1 similarity, margin )

(Platt-style calibration with two inputs.) Two honest caveats that the UI and
docs repeat:

  * the value depends on the mix of known/unknown queries in the calibration
    data (the "base rate"), which may differ from real deployment;
  * it is only meaningful for the embedding model it was fitted with.

It is a separate number from the retrieval score and is never used unless a
calibration run produced and applied it.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class ConfidenceModel:
    weight_similarity: float
    weight_margin: float
    bias: float
    similarity_mean: float
    similarity_std: float
    margin_mean: float
    margin_std: float
    n_fit: int
    n_correct: int
    fitted_on: str  # e.g. "dataset 'market1501', calibration split, seed 0"

    def predict(self, similarity: float, margin: float | None) -> float | None:
        """Probability in (0, 1), or None when the margin is unavailable (single-identity gallery)."""
        if margin is None:
            return None
        z = (
            self.weight_similarity * (similarity - self.similarity_mean) / self.similarity_std
            + self.weight_margin * (margin - self.margin_mean) / self.margin_std
            + self.bias
        )
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))

    def predict_many(self, similarity: np.ndarray, margin: np.ndarray) -> np.ndarray:
        z = (
            self.weight_similarity * (similarity - self.similarity_mean) / self.similarity_std
            + self.weight_margin * (margin - self.margin_mean) / self.margin_std
            + self.bias
        )
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ConfidenceModel:
        return cls(**data)

    @classmethod
    def fit(
        cls,
        similarity: np.ndarray,
        margin: np.ndarray,
        correct: np.ndarray,
        *,
        fitted_on: str,
        l2: float = 1e-2,
        max_iter: int = 100,
    ) -> ConfidenceModel:
        """Fit by Newton's method (iteratively re-weighted least squares) with a small ridge penalty."""
        y = np.asarray(correct, dtype=np.float64)
        if y.size < 20 or y.min() == y.max():
            raise ValueError("Need at least 20 samples containing both correct and incorrect matches.")

        s_mean, s_std = float(similarity.mean()), float(similarity.std()) or 1.0
        m_mean, m_std = float(margin.mean()), float(margin.std()) or 1.0
        features = np.column_stack(
            [np.ones_like(y), (similarity - s_mean) / s_std, (margin - m_mean) / m_std]
        ).astype(np.float64)

        beta = np.zeros(3)
        penalty = np.diag([0.0, l2, l2])  # do not penalise the intercept
        for _ in range(max_iter):
            p = 1.0 / (1.0 + np.exp(-np.clip(features @ beta, -30, 30)))
            gradient = features.T @ (p - y) + penalty @ beta
            hessian = (features.T * (p * (1 - p))) @ features + penalty + 1e-9 * np.eye(3)
            step = np.linalg.solve(hessian, gradient)
            beta -= step
            if np.max(np.abs(step)) < 1e-8:
                break

        return cls(
            weight_similarity=float(beta[1]),
            weight_margin=float(beta[2]),
            bias=float(beta[0]),
            similarity_mean=s_mean,
            similarity_std=s_std,
            margin_mean=m_mean,
            margin_std=m_std,
            n_fit=int(y.size),
            n_correct=int(y.sum()),
            fitted_on=fitted_on,
        )
