import pytest

from testzede.analysis.metrics import (
    METRIC_DESCRIPTIONS,
    METRIC_NAMES,
    MetricsError,
    compute_metrics,
    maintainability_rank,
)

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


def test_every_metric_has_a_description():
    assert set(METRIC_DESCRIPTIONS) == set(METRIC_NAMES)
    assert all(text.strip() for text in METRIC_DESCRIPTIONS.values())


@pytest.mark.parametrize(
    ("score", "rank"),
    [(100.0, "A"), (19.01, "A"), (19.0, "B"), (10.0, "B"), (9.01, "B"), (9.0, "C"), (0.0, "C")],
)
def test_maintainability_rank_thresholds(score, rank):
    assert maintainability_rank(score) == rank


def test_null_bytes_are_a_metrics_error_not_a_raw_value_error():
    with pytest.raises(MetricsError, match="null"):
        compute_metrics("x = 1\x00")


def test_syntax_error_message_has_the_line_number():
    with pytest.raises(MetricsError, match=r"satır 2"):
        compute_metrics("x = 1\ndef broken(:\n")


def test_invalid_escape_sequences_do_not_emit_warnings(recwarn):
    compute_metrics('def f(x):\n    return "\\d" + x\n')
    assert not [w for w in recwarn if issubclass(w.category, (SyntaxWarning, DeprecationWarning))]
