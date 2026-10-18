from __future__ import annotations

import pytest

from testzede.domain.models import TestCase
from testzede.execution.coverage_runner import ExecutionResult
from testzede.services import coverage_service
from testzede.services.coverage_service import CoverageService
from testzede.services.errors import ServiceError

SOURCE = "def f(a):\n    if a > 0:\n        return 1\n    return 2\n"
TEST = TestCase(name="t", code="def test_t():\n    assert f(1) == 1", origin="user")


def test_service_error_carries_message():
    err = ServiceError("hata")
    assert str(err) == "hata"
    assert err.message == "hata"


@pytest.mark.parametrize("source", ["", "   \n\t"])
def test_empty_source_raises(source):
    with pytest.raises(ServiceError, match="boş"):
        CoverageService().run(source, [TEST])


def test_invalid_source_raises():
    with pytest.raises(ServiceError, match="geçerli bir Python"):
        CoverageService().run("def f(:", [TEST])


def test_null_byte_source_raises_service_error():
    with pytest.raises(ServiceError):
        CoverageService().run("x = 1\x00", [TEST])


def test_empty_test_list_raises():
    with pytest.raises(ServiceError, match="Test listesi boş"):
        CoverageService().run(SOURCE, [])


def test_normal_path_with_real_run_tests():
    result = CoverageService().run(SOURCE, [TEST])
    assert isinstance(result, ExecutionResult)
    assert result.test_outcomes == {"t": "passed"}
    assert result.coverage.covered_lines == 3
    assert result.coverage.total_lines == 4
    assert result.stats.generated == 1


def _capture(monkeypatch):
    captured: dict = {}

    def fake_run_tests(unit, tests, *, timeout):
        captured.update(unit=unit, tests=tests, timeout=timeout)
        return "sonuç"

    monkeypatch.setattr(coverage_service, "run_tests", fake_run_tests)
    return captured


def test_unit_is_built_and_result_returned_unchanged(monkeypatch):
    captured = _capture(monkeypatch)
    assert CoverageService().run(SOURCE, [TEST]) == "sonuç"
    unit = captured["unit"]
    assert (unit.uid, unit.dataset, unit.source) == ("user/0", None, SOURCE)
    assert captured["tests"] == [TEST]
    assert captured["timeout"] == 10.0


def test_custom_timeout_is_forwarded(monkeypatch):
    captured = _capture(monkeypatch)
    CoverageService().run(SOURCE, [TEST], timeout=2.5)
    assert captured["timeout"] == 2.5


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def first(): pass\ndef second(): pass", "first"),
        ("import os\nX = 1\ndef later(): pass", "later"),
        ("class A:\n    def method(self): pass\ndef top(): pass", "top"),
        ("class A:\n    def method(self): pass", None),
        ("X = 1", None),
        ("if True:\n    def nested(): pass", None),
    ],
)
def test_entry_point_detection(monkeypatch, source, expected):
    captured = _capture(monkeypatch)
    CoverageService().run(source, [TEST])
    assert captured["unit"].entry_point == expected
