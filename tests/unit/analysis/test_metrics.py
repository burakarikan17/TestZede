import pytest

from testzede.analysis.metrics import METRIC_NAMES, MetricsError, compute_metrics

SAMPLE = '''\
def add(a, b):
    """Iki sayiyi toplar."""
    # toplama
    return a + b * 2


def sign(x):
    if x > 0:
        return 1
    elif x < 0:
        return -1
    return 0
'''


def test_returns_all_14_metrics():
    result = compute_metrics(SAMPLE)
    assert len(METRIC_NAMES) == 14
    assert set(result.values) == set(METRIC_NAMES)


def test_line_metrics():
    values = compute_metrics(SAMPLE).values
    assert values["LOC"] == 12
    assert values["Yorum"] == 1
    assert values["Boş Satır"] == 2


def test_cyclomatic_complexity_sums_functions():
    # add -> 1, sign -> 3 (if + elif + taban)
    assert compute_metrics(SAMPLE).values["Çevrimsel Karmaşıklık"] == 4


def test_halstead_values_are_positive_for_arithmetic_code():
    values = compute_metrics(SAMPLE).values
    assert values["Halstead Hacim"] > 0
    assert values["Halstead Kelime Haznesi"] > 0


def test_empty_source_has_baseline_values():
    values = compute_metrics("").values
    assert values["LOC"] == 0
    assert values["Çevrimsel Karmaşıklık"] == 1
    assert values["Sürdürülebilirlik İndeksi"] == 100.0


def test_invalid_syntax_raises_metrics_error():
    with pytest.raises(MetricsError):
        compute_metrics("def broken(:\n    pass")
