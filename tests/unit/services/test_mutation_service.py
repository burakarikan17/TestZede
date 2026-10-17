from __future__ import annotations

from collections.abc import Callable

import pytest

from testzede.domain.models import MutationReport, RunStats, TestCase
from testzede.mutation.engine import MutationError
from testzede.services.errors import ServiceError
from testzede.services.mutation_service import MutationService

TESTS = [TestCase(name="t", code="def test_t():\n    pass", origin="user")]
REPORT = MutationReport(total=4, killed=3, survived=1, timeout=0)
STATS = RunStats(generated=1, compiled=1, execution_time_s=0.5)


class FakeEngine:
    """Çağrıları kaydeden sahte motor."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def run(
        self,
        source: str,
        tests: list[TestCase],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> tuple[MutationReport, RunStats]:
        self.calls.append((source, tests, progress_callback))
        if progress_callback is not None:
            progress_callback(1, 1)
        return REPORT, STATS


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
    assert engine.calls == [("x = 1", TESTS, None)]


def test_progress_callback_is_forwarded():
    engine = FakeEngine()
    seen: list[tuple[int, int]] = []
    MutationService(engine).run("x = 1", TESTS, progress_callback=lambda d, t: seen.append((d, t)))
    assert seen == [(1, 1)]


def test_mutation_error_is_converted_to_service_error():
    class FailingEngine:
        def run(self, source, tests, progress_callback=None):
            raise MutationError("Testler orijinal kodda geçmiyor")

    with pytest.raises(ServiceError, match="Testler orijinal kodda geçmiyor") as info:
        MutationService(FailingEngine()).run("x = 1", TESTS)
    assert info.value.message == "Testler orijinal kodda geçmiyor"
    assert isinstance(info.value.__cause__, MutationError)
