"""Toplu çalıştırıcının tahmin aşaması (``BatchConfig.prediction``)."""

from __future__ import annotations

from collections.abc import Callable

from testzede.domain.models import CodeUnit, MetricSet, Prediction
from testzede.prediction.baseline import predict_baseline
from testzede.prediction.learned import LearnedPredictor
from testzede.rl.trainer import EpisodeResult

PredictionStage = Callable[[CodeUnit, MetricSet | None, EpisodeResult], Prediction]


def prediction_stage(predictor: LearnedPredictor | None = None) -> PredictionStage:
    """Tahmin aşamasını kurar; eğitilmiş ``predictor`` verilmezse temel tahmin kullanılır."""

    def stage(unit: CodeUnit, metrics: MetricSet | None, episode: EpisodeResult) -> Prediction:
        if metrics is None:
            raise ValueError("metrikler hesaplanamadığı için tahmin yapılamadı")
        if predictor is not None and predictor.fitted:
            return predictor.predict(metrics)
        return predict_baseline(metrics)

    return stage
