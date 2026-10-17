from __future__ import annotations

from collections.abc import Callable

import pytest

from testzede.domain.models import CodeUnit, CoverageReport, RunStats, TestCase
from testzede.execution.coverage_runner import ExecutionResult
from testzede.mutation import engine as engine_module
from testzede.mutation.engine import MutationEngine, MutationError, MutationRun
from testzede.mutation.operators import generate_all
from testzede.services.mutation_service import MutationService

ORIGINAL = "def f(a):\n    return a + 1"
MANY = "def f(a):\n    x = a + 1\n    y = a - 1\n    z = a * 2\n    w = a / 2\n    return x + y + z + w"


def _t(name: str) -> TestCase:
    return TestCase(name=name, code=f"def test_{name}():\n    pass", origin="user")


TESTS = [_t("t1"), _t("t2")]


def _result(outcomes: dict[str, str], seconds: float) -> ExecutionResult:
    compiled = sum(1 for o in outcomes.values() if o != "error")
    return ExecutionResult(
        coverage=CoverageReport(0, 0, 0, 0),
        stats=RunStats(generated=len(outcomes), compiled=compiled, execution_time_s=seconds),
        covered_lines=frozenset(),
        covered_branches=frozenset(),
        all_lines=frozenset(),
        all_branches=frozenset(),
        test_outcomes=dict(outcomes),  # type: ignore[arg-type]
    )


class FakeRunTests:
    """``run_tests`` yerine geçer: çağrıları kaydeder, sonucu kaynak koduna göre üretir."""

    def __init__(
        self,
        behavior: Callable[[str], dict[str, str]],
        baseline_seconds: float = 0.1,
    ) -> None:
        self.behavior = behavior
        self.baseline_seconds = baseline_seconds
        self.calls: list[tuple[str, float]] = []

    def __call__(self, unit: CodeUnit, tests, *, timeout: float) -> ExecutionResult:
        self.calls.append((unit.source, timeout))
        seconds = self.baseline_seconds if len(self.calls) == 1 else 0.0
        return _result(self.behavior(unit.source), seconds)

    @property
    def mutant_calls(self) -> list[tuple[str, float]]:
        return self.calls[1:]


def _install(monkeypatch, behavior, baseline_seconds: float = 0.1) -> FakeRunTests:
    fake = FakeRunTests(behavior, baseline_seconds)
    monkeypatch.setattr(engine_module, "run_tests", fake)
    return fake


def _all(outcome: str) -> dict[str, str]:
    return {"t1": outcome, "t2": outcome}


def _kill_all_but(survivor_sources: set[str]):
    def behavior(source: str) -> dict[str, str]:
        if source == ORIGINAL or source in survivor_sources:
            return _all("passed")
        return _all("failed")

    return behavior


# --- sonuçlar ----------------------------------------------------------------------------------


def test_strong_suite_kills_every_mutant(monkeypatch):
    _install(monkeypatch, _kill_all_but(set()))
    report, stats = MutationEngine().run(ORIGINAL, TESTS)
    assert (report.total, report.killed, report.survived, report.timeout) == (3, 3, 0, 0)
    assert report.score == 1.0
    assert stats.generated == 2


def test_weak_suite_reports_survivors(monkeypatch):
    survivor = "def f(a):\n    return a + 0"
    _install(monkeypatch, _kill_all_but({survivor}))
    run = MutationEngine().run_detailed(ORIGINAL, TESTS)
    assert isinstance(run, MutationRun)
    assert (run.report.total, run.report.killed, run.report.survived) == (3, 2, 1)
    assert [m.source for m in run.survivors] == [survivor]
    assert (run.survivors[0].operator, run.survivors[0].line) == ("CONST", 2)
    assert run.report.score == pytest.approx(2 / 3)


def test_run_matches_run_detailed(monkeypatch):
    _install(monkeypatch, _kill_all_but(set()))
    run = MutationEngine().run_detailed(ORIGINAL, TESTS)
    _install(monkeypatch, _kill_all_but(set()))  # yeni sahte: "ilk çağrı = baseline" sıfırlanır
    assert MutationEngine().run(ORIGINAL, TESTS) == (run.report, run.stats)


def test_stats_come_from_baseline_run(monkeypatch):
    _install(monkeypatch, _kill_all_but(set()), baseline_seconds=0.7)
    run = MutationEngine().run_detailed(ORIGINAL, TESTS)
    assert run.stats.execution_time_s == 0.7
    assert (run.stats.generated, run.stats.compiled) == (2, 2)


def test_timeout_mutant_is_counted_as_timeout(monkeypatch):
    hang = "def f(a):\n    return a - 1"

    def behavior(source: str) -> dict[str, str]:
        if source == ORIGINAL:
            return _all("passed")
        return _all("timeout") if source == hang else _all("failed")

    _install(monkeypatch, behavior)
    report, _ = MutationEngine().run(ORIGINAL, TESTS)
    assert (report.total, report.killed, report.timeout, report.survived) == (3, 2, 1, 0)


def test_timeout_wins_over_failed_within_one_mutant(monkeypatch):
    def behavior(source: str) -> dict[str, str]:
        if source == ORIGINAL:
            return _all("passed")
        return {"t1": "failed", "t2": "timeout"}

    _install(monkeypatch, behavior)
    report, _ = MutationEngine().run(ORIGINAL, TESTS)
    assert (report.killed, report.timeout) == (0, 3)


@pytest.mark.parametrize(
    ("baseline_seconds", "expected"), [(0.1, 2.0), (0.4, 2.0), (1.0, 5.0), (3.0, 15.0)]
)
def test_mutant_timeout_is_max_of_floor_and_five_times_baseline(
    monkeypatch, baseline_seconds, expected
):
    fake = _install(monkeypatch, _kill_all_but(set()), baseline_seconds)
    MutationEngine().run(ORIGINAL, TESTS)
    assert fake.calls[0][1] == 10.0  # baseline
    assert {t for _, t in fake.mutant_calls} == {expected}


def test_error_mutant_counts_as_killed(monkeypatch):
    def behavior(source: str) -> dict[str, str]:
        return _all("passed") if source == ORIGINAL else _all("error")

    _install(monkeypatch, behavior)
    report, _ = MutationEngine().run(ORIGINAL, TESTS)
    assert (report.killed, report.survived) == (3, 0)


def test_baseline_error_test_is_excluded_from_decision(monkeypatch):
    # "broken" orijinalde de "error": mutantlarda "error" olması mutantı öldürmemeli.
    def behavior(source: str) -> dict[str, str]:
        return {"ok": "passed", "broken": "error"}

    _install(monkeypatch, behavior)
    run = MutationEngine().run_detailed(ORIGINAL, [_t("ok"), _t("broken")])
    assert (run.report.killed, run.report.survived) == (0, 3)
    assert len(run.survivors) == 3


def test_baseline_error_test_does_not_hide_a_real_kill(monkeypatch):
    def behavior(source: str) -> dict[str, str]:
        if source == ORIGINAL:
            return {"ok": "passed", "broken": "error"}
        return {"ok": "failed", "broken": "error"}

    _install(monkeypatch, behavior)
    report, _ = MutationEngine().run(ORIGINAL, [_t("ok"), _t("broken")])
    assert (report.killed, report.survived) == (3, 0)


# --- baseline hataları -------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["failed", "timeout"])
def test_failing_baseline_raises_mutation_error(monkeypatch, bad):
    fake = _install(monkeypatch, lambda source: {"t1": "passed", "t2": bad})
    with pytest.raises(MutationError, match="orijinal kodda geçmiyor") as info:
        MutationEngine().run(ORIGINAL, TESTS)
    assert "t2" in str(info.value)
    assert len(fake.calls) == 1  # mutant koşturulmadı


def test_no_passing_test_in_baseline_raises(monkeypatch):
    _install(monkeypatch, lambda source: _all("error"))
    with pytest.raises(MutationError, match="geçen hiçbir test yok"):
        MutationEngine().run(ORIGINAL, TESTS)


def test_empty_test_list_raises(monkeypatch):
    _install(monkeypatch, lambda source: {})
    with pytest.raises(MutationError):
        MutationEngine().run(ORIGINAL, [])


@pytest.mark.parametrize("bad", ["def f(:", "x = 1\x00"])
def test_invalid_source_raises_mutation_error(monkeypatch, bad):
    fake = _install(monkeypatch, lambda source: _all("passed"))
    with pytest.raises(MutationError, match="geçerli bir Python"):
        MutationEngine().run(bad, TESTS)
    assert fake.calls == []


def test_generate_all_value_error_becomes_mutation_error(monkeypatch):
    def boom(source: str):
        raise ValueError("kötü")

    _install(monkeypatch, lambda source: _all("passed"))
    monkeypatch.setattr(engine_module, "generate_all", boom)
    with pytest.raises(MutationError, match="Mutant üretilemedi"):
        MutationEngine().run(ORIGINAL, TESTS)


# --- mutantsız kod, örnekleme, iptal, ilerleme -------------------------------------------------


def test_source_without_mutation_points_gives_empty_report(monkeypatch):
    fake = _install(monkeypatch, lambda source: _all("passed"))
    report, stats = MutationEngine().run("def f(a):\n    pass", TESTS)
    assert (report.total, report.killed, report.survived, report.timeout) == (0, 0, 0, 0)
    assert report.score == 0.0
    assert stats.generated == 2
    assert len(fake.calls) == 1  # yalnızca baseline


def _executed_sources(monkeypatch, **kwargs) -> tuple[list[str], int]:
    fake = _install(monkeypatch, lambda source: _all("passed"))
    report, _ = MutationEngine(**kwargs).run(MANY, TESTS)
    return [s for s, _ in fake.mutant_calls], report.total


def test_max_mutants_samples_deterministically_in_source_order(monkeypatch):
    full = [m.source for m in generate_all(MANY)]
    assert len(full) > 5
    first, total = _executed_sources(monkeypatch, max_mutants=3, seed=7)
    second, _ = _executed_sources(monkeypatch, max_mutants=3, seed=7)
    assert first == second
    assert total == 3
    positions = [full.index(s) for s in first]
    assert positions == sorted(positions)
    assert len(set(first)) == 3


def test_different_seed_can_pick_different_mutants(monkeypatch):
    runs = {tuple(_executed_sources(monkeypatch, max_mutants=3, seed=s)[0]) for s in range(5)}
    assert len(runs) > 1


def test_max_mutants_none_or_large_runs_everything(monkeypatch):
    expected = len(generate_all(MANY))
    assert _executed_sources(monkeypatch, max_mutants=None)[1] == expected
    assert _executed_sources(monkeypatch, max_mutants=1000)[1] == expected


def test_progress_callback_called_once_per_mutant(monkeypatch):
    _install(monkeypatch, _kill_all_but(set()))
    seen: list[tuple[int, int]] = []
    MutationEngine().run(ORIGINAL, TESTS, progress_callback=lambda d, t: seen.append((d, t)))
    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_should_cancel_stops_loop_and_reports_partial_result(monkeypatch):
    fake = _install(monkeypatch, _kill_all_but(set()))
    checks = iter([False, False, True])
    seen: list[tuple[int, int]] = []
    report, _ = MutationEngine().run(
        ORIGINAL,
        TESTS,
        progress_callback=lambda d, t: seen.append((d, t)),
        should_cancel=lambda: next(checks),
    )
    assert (report.total, report.killed) == (2, 2)  # total = gerçekten çalıştırılanlar
    assert len(fake.mutant_calls) == 2
    assert seen == [(1, 3), (2, 3)]


def test_cancel_before_first_mutant_gives_empty_report(monkeypatch):
    fake = _install(monkeypatch, _kill_all_but(set()))
    report, _ = MutationEngine().run(ORIGINAL, TESTS, should_cancel=lambda: True)
    assert report.total == 0
    assert fake.mutant_calls == []


def test_max_total_seconds_stops_loop(monkeypatch):
    fake = _install(monkeypatch, _kill_all_but(set()))
    # Negatif süre sınırı, geçen süreden (>= 0) her zaman küçüktür: döngü hemen durur.
    report, stats = MutationEngine(max_total_seconds=-1.0).run(ORIGINAL, TESTS)
    assert report.total == 0
    assert stats.generated == 2
    assert fake.mutant_calls == []


# --- servis entegrasyonu ve gerçek koşu ---------------------------------------------------------


def test_engine_fits_mutation_service_and_errors_become_service_errors(monkeypatch):
    from testzede.services.errors import ServiceError

    _install(monkeypatch, _kill_all_but(set()))
    report, _ = MutationService(MutationEngine()).run(ORIGINAL, TESTS)
    assert report.total == 3

    _install(monkeypatch, lambda source: {"t1": "failed", "t2": "passed"})
    with pytest.raises(ServiceError, match="orijinal kodda geçmiyor"):
        MutationService(MutationEngine()).run(ORIGINAL, TESTS)


def test_real_run_tests_end_to_end_with_survivors():
    source = "def f(a):\n    if a > 0:\n        return 1\n    return 2\n"
    tests = [TestCase("t", "def test_t():\n    assert f(1) == 1", "user")]
    run = MutationEngine().run_detailed(source, tests)
    assert (run.report.total, run.report.killed, run.report.survived) == (5, 3, 2)
    assert {(m.operator, m.line) for m in run.survivors} == {("ROR", 2), ("RETURN_NONE", 4)}
    assert run.stats.generated == 1 and run.stats.compilation_rate == 1.0


def test_real_run_tests_failing_baseline_raises():
    tests = [TestCase("t", "def test_t():\n    assert f(1) == 99", "user")]
    with pytest.raises(MutationError, match="orijinal kodda geçmiyor"):
        MutationEngine().run("def f(a):\n    return a\n", tests)
