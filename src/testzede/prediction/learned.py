"""Öğrenilmiş tahmin (US-7, opsiyonel): kod metriklerinden scikit-learn regresyonu.

Geliştirme setinde her birim için iki hedef toplanır: RL coverage eğrisinin doygunluğa
ulaştığı test sayısı (diz noktası) ve hayatta kalan mutant sayısı (hata vekili). Girdi
metrikleri (hacim, karmaşıklık, SLOC, zorluk) log ölçeğinde standartlaştırılır ve iki
ayrı Ridge regresyonu eğitilir. Eğitim verisi ``batch`` sonuçlarından :func:`training_row`
ile üretilir.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from testzede.domain.models import MetricSet, MutationReport, Prediction
from testzede.prediction.baseline import knee_point
from testzede.rl.trainer import EpisodeResult

FEATURES: tuple[str, ...] = (
    "Halstead Hacim",
    "Çevrimsel Karmaşıklık",
    "SLOC",
    "Halstead Zorluk",
)
MIN_ROWS = 5


@dataclass(frozen=True)
class TrainingRow:
    """Bir kod biriminin metrikleri ve ölçülen hedefleri."""

    metrics: MetricSet
    optimum_tests: int  # RL coverage eğrisinin diz noktası
    bugs: float  # hayatta kalan mutant sayısı (hata vekili)


def training_row(
    metrics: MetricSet, episode: EpisodeResult, mutation: MutationReport
) -> TrainingRow:
    """Bir birimin batch sonucundan eğitim satırı üretir."""
    return TrainingRow(metrics, knee_point(episode.curve), float(mutation.survived))


def _features(metrics: MetricSet) -> list[float]:
    return [math.log1p(max(metrics.values[name], 0.0)) for name in FEATURES]


class LearnedPredictor:
    """Metriklerden hata ve optimum test sayısını öğrenen iki regresyon."""

    def __init__(self, alpha: float = 1.0) -> None:
        self._alpha = alpha
        self._bugs: Pipeline | None = None
        self._tests: Pipeline | None = None
        self.rows = 0

    @property
    def fitted(self) -> bool:
        return self._bugs is not None

    def _model(self) -> Pipeline:
        return Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=self._alpha))])

    def fit(self, rows: Sequence[TrainingRow]) -> LearnedPredictor:
        """Eğitim satırlarıyla iki modeli eğitir.

        Raises:
            ValueError: ``MIN_ROWS``'tan az satır verilirse.
        """
        if len(rows) < MIN_ROWS:
            raise ValueError(f"En az {MIN_ROWS} eğitim satırı gerekir ({len(rows)} verildi).")
        x = np.array([_features(r.metrics) for r in rows])
        self._bugs = self._model().fit(x, [r.bugs for r in rows])
        self._tests = self._model().fit(x, [r.optimum_tests for r in rows])
        self.rows = len(rows)
        return self

    def predict(self, metrics: MetricSet) -> Prediction:
        """Tahmini hata sayısı (>= 0) ve optimum test sayısı (>= 1).

        Raises:
            RuntimeError: Model henüz eğitilmediyse.
        """
        if self._bugs is None or self._tests is None:
            raise RuntimeError("Model eğitilmemiş: önce fit() çağrılmalı.")
        x = np.array([_features(metrics)])
        return Prediction(
            estimated_bugs=max(0.0, float(self._bugs.predict(x)[0])),
            optimum_test_count=max(1, round(float(self._tests.predict(x)[0]))),
            method=f"Ridge regresyonu (n={self.rows})",
        )
