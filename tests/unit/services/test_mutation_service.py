from __future__ import annotations

from collections.abc import Callable

import pytest

from testzede.domain.models import MutationReport, RunStats, TestCase
from testzede.mutation.engine import MutationError, MutationRun
from testzede.mutation.operators import Mutant
from testzede.services.errors import ServiceError
from testzede.services.mutation_service import MutationService

TESTS = [TestCase(name="t", code="def test_t():\n    pass", origin="user")]
REPORT = MutationReport(total=4, killed=3, survived=1, timeout=0)
STATS = RunStats(generated=1, compiled=1, execution_time_s=0.5)
SURVIVOR = Mutant("AOR", 2, "+ -> -", "def f(a):\n    return a - 1")
RUN = MutationRun(report=REPORT, stats=STATS, survivors=[SURVIVOR])


class FakeEngine:
    """Çağrıları kaydeden sahte motor."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.detailed_calls: list[tuple] = []

    def run(
        self,
        source: str,
        tests: list[TestCase],
        progress_callback: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[MutationReport, RunStats]:
        self.calls.append((source, tests, progress_callback, should_cancel))
        if progress_callback is not None:
            progress_callback(1, 1)
        return REPORT, STATS

    def run_detailed(
        self,
        source: str,
        tests: list[TestCase],
        progress_callback: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> MutationRun:
        self.detailed_calls.append((source, tests, progress_callback, should_cancel))
        if progress_callback is not None:
            progress_callback(1, 1)
        return RUN


class FailingEngine:
    """İki yolda da ``MutationError`` fırlatan sahte motor."""

    def run(self, source, tests, progress_callback=None, should_cancel=None):
        raise MutationError("Testler orijinal kodda geçmiyor")

    def run_detailed(self, source, tests, progress_callback=None, should_cancel=None):
        raise MutationError("Testler orijinal kodda geçmiyor")


# --- run ---------------------------------------------------------------------------------------


def test_no_engine_raises_service_error():
    with pytest.raises(ServiceError, match="Mutasyon motoru henüz bağlı değil"):
        MutationService().run("x = 1", TESTS)


def test_explicit_none_engine_raises_service_error():
    with pytest.raises(ServiceError):
        MutationService(engine=None).run("x = 1", TESTS)


def test_run_delegates_to_engine_and_returns_its_result():
    engine = FakeEngine()
    result = MutationService(engine).run("x = 1", TESTS)
    assert result == (REPORT, STATS)
    assert engine.calls == [("x = 1", TESTS, None, None)]
    assert engine.detailed_calls == []


def test_progress_callback_is_forwarded():
    engine = FakeEngine()
    seen: list[tuple[int, int]] = []
    MutationService(engine).run("x = 1", TESTS, progress_callback=lambda d, t: seen.append((d, t)))
    assert seen == [(1, 1)]


def test_should_cancel_is_forwarded_to_run():
    engine = FakeEngine()

    def cancel() -> bool:
        return False

    MutationService(engine).run("x = 1", TESTS, should_cancel=cancel)
    assert engine.calls[0][3] is cancel


def test_mutation_error_is_converted_to_service_error():
    with pytest.raises(ServiceError, match="Testler orijinal kodda geçmiyor") as info:
        MutationService(FailingEngine()).run("x = 1", TESTS)
    assert info.value.message == "Testler orijinal kodda geçmiyor"
    assert isinstance(info.value.__cause__, MutationError)


# --- run_detailed ------------------------------------------------------------------------------


def test_run_detailed_without_engine_raises_service_error():
    with pytest.raises(ServiceError, match="Mutasyon motoru henüz bağlı değil"):
        MutationService().run_detailed("x = 1", TESTS)


def test_run_detailed_returns_engine_result():
    engine = FakeEngine()
    result = MutationService(engine).run_detailed("x = 1", TESTS)
    assert result is RUN
    assert result.survivors == [SURVIVOR]
    assert engine.detailed_calls == [("x = 1", TESTS, None, None)]
    assert engine.calls == []


def test_run_detailed_forwards_progress_and_cancel():
    engine = FakeEngine()
    seen: list[tuple[int, int]] = []

    def cancel() -> bool:
        return False

    MutationService(engine).run_detailed(
        "x = 1", TESTS, progress_callback=lambda d, t: seen.append((d, t)), should_cancel=cancel
    )
    assert seen == [(1, 1)]
    assert engine.detailed_calls[0][3] is cancel


def test_run_detailed_converts_mutation_error():
    with pytest.raises(ServiceError, match="Testler orijinal kodda geçmiyor") as info:
        MutationService(FailingEngine()).run_detailed("x = 1", TESTS)
    assert info.value.message == "Testler orijinal kodda geçmiyor"
    assert isinstance(info.value.__cause__, MutationError)
