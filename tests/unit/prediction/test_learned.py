import pytest

from testzede.domain.models import CoverageReport, MetricSet, MutationReport, RunStats
from testzede.prediction.learned import (
    FEATURES,
    MIN_ROWS,
    LearnedPredictor,
    TrainingRow,
    training_row,
)
from testzede.prediction.stage import prediction_stage
from testzede.rl.env import CurvePoint
from testzede.rl.trainer import EpisodeResult


def _metrics(scale: float) -> MetricSet:
    return MetricSet({name: scale * (i + 1) for i, name in enumerate(FEATURES)})


def _rows(count: int = 12) -> list[TrainingRow]:
    return [
        TrainingRow(_metrics(float(n)), optimum_tests=n + 1, bugs=0.5 * n)
        for n in range(1, count + 1)
    ]


def test_predictor_learns_a_monotonic_relation():
    predictor = LearnedPredictor().fit(_rows())
    small, large = predictor.predict(_metrics(2.0)), predictor.predict(_metrics(11.0))
    assert small.estimated_bugs < large.estimated_bugs
    assert small.optimum_test_count < large.optimum_test_count
    assert small.method == "Ridge regresyonu (n=12)"


def test_predictions_are_never_below_their_minimum():
    predictor = LearnedPredictor().fit(_rows())
    tiny = predictor.predict(_metrics(0.0))
    assert tiny.estimated_bugs >= 0.0 and tiny.optimum_test_count >= 1


def test_fit_needs_enough_rows():
    with pytest.raises(ValueError, match=str(MIN_ROWS)):
        LearnedPredictor().fit(_rows(MIN_ROWS - 1))


def test_predict_before_fit_fails():
    with pytest.raises(RuntimeError):
        LearnedPredictor().predict(_metrics(1.0))


def test_training_row_uses_knee_point_and_surviving_mutants():
    curve = [CurvePoint(1, 1, 0.5, 0.5), CurvePoint(2, 2, 0.9, 0.8), CurvePoint(3, 3, 0.9, 0.8)]
    episode = EpisodeResult([], CoverageReport(9, 10, 4, 5), RunStats(3, 3, 0.1), curve, 1.0, 3)
    row = training_row(
        _metrics(3.0), episode, MutationReport(total=10, killed=6, survived=3, timeout=1)
    )
    assert row.optimum_tests == 2 and row.bugs == 3.0


def test_stage_without_metrics_fails():
    with pytest.raises(ValueError):
        prediction_stage()(None, None, None)  # type: ignore[arg-type]


def test_stage_uses_the_fitted_predictor_else_the_baseline():
    metrics = _metrics(4.0)
    baseline = prediction_stage()(None, metrics, None)  # type: ignore[arg-type]
    assert baseline.method.startswith("Halstead")
    predictor = LearnedPredictor().fit(_rows())
    learned = prediction_stage(predictor)(None, metrics, None)  # type: ignore[arg-type]
    assert learned.method.startswith("Ridge")
    unfitted = prediction_stage(LearnedPredictor())(None, metrics, None)  # type: ignore[arg-type]
    assert unfitted.method.startswith("Halstead")
