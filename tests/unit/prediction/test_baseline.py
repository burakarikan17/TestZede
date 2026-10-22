import pytest

from testzede.analysis.metrics import compute_metrics
from testzede.domain.models import MetricSet
from testzede.prediction.baseline import (
    COMPLEXITY,
    HALSTEAD_DIVISOR,
    METHOD,
    VOLUME,
    knee_point,
    predict_baseline,
)
from testzede.rl.env import CurvePoint

SOURCE = "def f(x):\n    if x > 0:\n        return 1\n    return 0\n"


def _curve(*rates: float) -> list[CurvePoint]:
    return [
        CurvePoint(step=i + 1, tests=i + 1, line_rate=r, branch_rate=r) for i, r in enumerate(rates)
    ]


def test_estimated_bugs_is_halstead_volume_over_3000():
    metrics = MetricSet({VOLUME: 6000.0, COMPLEXITY: 4.0})
    prediction = predict_baseline(metrics)
    assert prediction.estimated_bugs == pytest.approx(6000.0 / HALSTEAD_DIVISOR)
    assert prediction.estimated_bugs == pytest.approx(2.0)
    assert prediction.method == METHOD


def test_optimum_test_count_is_the_mccabe_complexity():
    assert predict_baseline(MetricSet({VOLUME: 10.0, COMPLEXITY: 5.0})).optimum_test_count == 5


def test_optimum_test_count_is_at_least_one():
    assert predict_baseline(MetricSet({VOLUME: 0.0, COMPLEXITY: 0.0})).optimum_test_count == 1


def test_prediction_from_real_metrics():
    metrics = compute_metrics(SOURCE)
    prediction = predict_baseline(metrics)
    assert prediction.optimum_test_count == 2  # tek if: iki bağımsız yol
    assert prediction.estimated_bugs == pytest.approx(metrics.values[VOLUME] / 3000.0)


def test_missing_metric_raises_key_error():
    with pytest.raises(KeyError):
        predict_baseline(MetricSet({VOLUME: 1.0}))


def test_knee_point_is_the_first_test_count_that_saturates():
    assert knee_point(_curve(0.2, 0.6, 0.9, 0.9, 0.9)) == 3


def test_knee_point_tolerates_a_tiny_final_gain():
    assert knee_point(_curve(0.2, 0.9, 0.905)) == 2


def test_knee_point_of_a_flat_or_empty_curve():
    assert knee_point(_curve(0.5, 0.5, 0.5)) == 1
    assert knee_point([]) == 0
