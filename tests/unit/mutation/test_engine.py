from __future__ import annotations

import ast
import threading
import time
import zlib
from collections.abc import Callable, Iterable

import pytest

from testzede.domain.models import CodeUnit, CoverageReport, RunStats, TestCase
from testzede.execution.coverage_runner import ExecutionResult
from testzede.mutation import engine as engine_module
from testzede.mutation.engine import (
    MutationEngine,
    MutationError,
    MutationRun,
    _statement_start,
)
from testzede.mutation.operators import generate_all
from testzede.services.mutation_service import MutationService

ORIGINAL = "def f(a):\n    return a + 1"
COND = "def f(a):\n    if a > 0:\n        return 1\n    return 2"
MULTI = "def f(a):\n    if a:\n        return 1\n    return (a +\n            1)"
MANY = "def f(a):\n    x = a + 1\n    y = a - 1\n    z = a * 2\n    w = a / 2\n    return x + y + z + w"


def _t(name: str) -> TestCase:
    return TestCase(name=name, code=f"def test_{name}():\n    pass", origin="user")


TESTS = [_t("t1"), _t("t2")]


def _result(
    outcomes: dict[str, str],
    seconds: float,
    all_lines: Iterable[int] = (),
    covered_lines: Iterable[int] = (),
) -> ExecutionResult:
    compiled = sum(1 for o in outcomes.values() if o != "error")
    return ExecutionResult(
        coverage=CoverageReport(0, 0, 0, 0),
        stats=RunStats(generated=len(outcomes), compiled=compiled, execution_time_s=seconds),
        covered_lines=frozenset(covered_lines),
        covered_branches=frozenset(),
        all_lines=frozenset(all_lines),
        all_branches=frozenset(),
        test_outcomes=dict(outcomes),  # type: ignore[arg-type]
    )


class Fakes:
    """``run_tests`` (baseline) ve ``run_outcomes`` (mutantlar) yerine geçen sahteler."""

    def __init__(
        self,
        behavior: Callable[[str], dict[str, str]],
        baseline_seconds: float = 0.1,
        all_lines: Iterable[int] = (),
        covered_lines: Iterable[int] = (),
        delay: float = 0.0,
    ) -> None:
        self.behavior = behavior
        self.baseline_seconds = baseline_seconds
        self.all_lines = tuple(all_lines)
        self.covered_lines = tuple(covered_lines)
        self.delay = delay
        self.baseline_calls: list[tuple[str, float]] = []
        self.mutant_calls: list[tuple[str, float]] = []
        self._lock = threading.Lock()
        self._active = 0
        self.max_active = 0

    def run_tests(self, unit: CodeUnit, tests, *, timeout: float) -> ExecutionResult:
        self.baseline_calls.append((unit.source, timeout))
        return _result(
            self.behavior(unit.source), self.baseline_seconds, self.all_lines, self.covered_lines
        )

    def run_outcomes(self, unit: CodeUnit, tests, *, timeout: float) -> dict[str, str]:
        self.mutant_calls.append((unit.source, timeout))
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        try:
            if self.delay:
                time.sleep(self.delay)
            return dict(self.behavior(unit.source))
        finally:
            with self._lock:
                self._active -= 1


def _install(monkeypatch, behavior, baseline_seconds: float = 0.1, **kwargs) -> Fakes:
    fakes = Fakes(behavior, baseline_seconds, **kwargs)
    monkeypatch.setattr(engine_module, "run_tests", fakes.run_tests)
    monkeypatch.setattr(engine_module, "run_outcomes", fakes.run_outcomes)
    return fakes


def _all(outcome: str) -> dict[str, str]:
    return {"t1": outcome, "t2": outcome}


def _kill_all_but(survivor_sources: set[str], original: str = ORIGINAL):
    def behavior(source: str) -> dict[str, str]:
        if source == original or source in survivor_sources:
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
    assert run.skipped_uncovered == 0


def test_baseline_uses_run_tests_and_mutants_use_run_outcomes(monkeypatch):
    fakes = _install(monkeypatch, _kill_all_but(set()))
    MutationEngine().run(ORIGINAL, TESTS)
    assert [s for s, _ in fakes.baseline_calls] == [ORIGINAL]
    assert len(fakes.mutant_calls) == 3
    assert ORIGINAL not in [s for s, _ in fakes.mutant_calls]


def test_run_matches_run_detailed(monkeypatch):
    _install(monkeypatch, _kill_all_but(set()))
    run = MutationEngine().run_detailed(ORIGINAL, TESTS)
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
    ("baseline_seconds", "expected"), [(0.1, 3.0), (0.5, 3.0), (1.0, 5.0), (3.0, 15.0)]
)
def test_mutant_timeout_is_max_of_floor_and_five_times_baseline(
    monkeypatch, baseline_seconds, expected
):
    fakes = _install(monkeypatch, _kill_all_but(set()), baseline_seconds)
    MutationEngine().run(ORIGINAL, TESTS)
    assert fakes.baseline_calls[0][1] == 10.0
    assert {t for _, t in fakes.mutant_calls} == {expected}


def test_error_mutant_counts_as_killed(monkeypatch):
    def behavior(source: str) -> dict[str, str]:
        return _all("passed") if source == ORIGINAL else _all("error")

    _install(monkeypatch, behavior)
    report, _ = MutationEngine().run(ORIGINAL, TESTS)
    assert (report.killed, report.survived) == (3, 0)


def test_baseline_error_test_is_excluded_from_decision(monkeypatch):
    # "broken" orijinalde de "error": mutantlarda "error" olması mutantı öldürmemeli.
    _install(monkeypatch, lambda source: {"ok": "passed", "broken": "error"})
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
    fakes = _install(monkeypatch, lambda source: {"t1": "passed", "t2": bad})
    with pytest.raises(MutationError, match="orijinal kodda geçmiyor") as info:
        MutationEngine().run(ORIGINAL, TESTS)
    assert "t2" in str(info.value)
    assert fakes.mutant_calls == []


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
    fakes = _install(monkeypatch, lambda source: _all("passed"))
    with pytest.raises(MutationError, match="geçerli bir Python"):
        MutationEngine().run(bad, TESTS)
    assert fakes.baseline_calls == []


def test_generate_all_value_error_becomes_mutation_error(monkeypatch):
    def boom(source: str):
        raise ValueError("kötü")

    _install(monkeypatch, lambda source: _all("passed"))
    monkeypatch.setattr(engine_module, "generate_all", boom)
    with pytest.raises(MutationError, match="Mutant üretilemedi"):
        MutationEngine().run(ORIGINAL, TESTS)


# --- mutantsız kod, örnekleme ------------------------------------------------------------------


def test_source_without_mutation_points_gives_empty_report(monkeypatch):
    fakes = _install(monkeypatch, lambda source: _all("passed"))
    run = MutationEngine().run_detailed("def f(a):\n    pass", TESTS)
    assert (run.report.total, run.report.killed, run.report.survived, run.report.timeout) == (
        0,
        0,
        0,
        0,
    )
    assert run.report.score == 0.0
    assert run.stats.generated == 2
    assert run.survivors == [] and run.skipped_uncovered == 0
    assert fakes.mutant_calls == []


def _executed_sources(monkeypatch, **kwargs) -> tuple[list[str], int]:
    fakes = _install(monkeypatch, lambda source: _all("passed"))
    report, _ = MutationEngine(workers=1, **kwargs).run(MANY, TESTS)
    return [s for s, _ in fakes.mutant_calls], report.total


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


# --- paralellik --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cpus", "expected"), [(12, 6), (8, 6), (4, 2), (3, 1), (2, 1), (1, 1), (None, 1)]
)
def test_default_worker_count(monkeypatch, cpus, expected):
    monkeypatch.setattr(engine_module.os, "cpu_count", lambda: cpus)
    assert MutationEngine()._workers == expected


def test_explicit_worker_count_is_clamped_to_at_least_one():
    assert MutationEngine(workers=3)._workers == 3
    assert MutationEngine(workers=0)._workers == 1


def _mixed_behavior(source: str) -> dict[str, str]:
    if source == MANY:
        return _all("passed")
    return _all(("timeout", "failed", "passed")[zlib.crc32(source.encode()) % 3])


def test_parallel_results_equal_sequential_results(monkeypatch):
    _install(monkeypatch, _mixed_behavior)
    sequential = MutationEngine(workers=1).run_detailed(MANY, TESTS)
    _install(monkeypatch, _mixed_behavior, delay=0.01)
    parallel = MutationEngine(workers=4).run_detailed(MANY, TESTS)
    assert sequential == parallel
    assert sequential.report.survived and sequential.report.killed and sequential.report.timeout
    full = [m.source for m in generate_all(MANY)]
    positions = [full.index(m.source) for m in parallel.survivors]
    assert positions == sorted(positions)  # survivors kaynak sırasında


def test_mutants_really_run_concurrently(monkeypatch):
    fakes = _install(monkeypatch, _kill_all_but(set()), delay=0.15)
    MutationEngine(workers=2).run(ORIGINAL, TESTS)
    assert fakes.max_active == 2
    fakes = _install(monkeypatch, _kill_all_but(set()), delay=0.02)
    MutationEngine(workers=1).run(ORIGINAL, TESTS)
    assert fakes.max_active == 1


def test_progress_callback_called_once_per_mutant_from_calling_thread(monkeypatch):
    _install(monkeypatch, _kill_all_but(set()), delay=0.01)
    seen: list[tuple[int, int]] = []
    threads: set[int] = set()

    def progress(done: int, total: int) -> None:
        seen.append((done, total))
        threads.add(threading.get_ident())

    MutationEngine(workers=3).run(ORIGINAL, TESTS, progress_callback=progress)
    assert seen == [(1, 3), (2, 3), (3, 3)]
    assert threads == {threading.get_ident()}


# --- iptal ve süre sınırı ----------------------------------------------------------------------


def test_should_cancel_stops_loop_and_reports_partial_result(monkeypatch):
    fakes = _install(monkeypatch, _kill_all_but(set()))
    seen: list[tuple[int, int]] = []
    report, _ = MutationEngine(workers=1).run(
        ORIGINAL,
        TESTS,
        progress_callback=lambda d, t: seen.append((d, t)),
        should_cancel=lambda: len(fakes.mutant_calls) >= 2,
    )
    assert (report.total, report.killed) == (2, 2)  # total = gerçekten işlenenler
    assert len(fakes.mutant_calls) == 2
    assert seen == [(1, 3), (2, 3)]


def test_cancel_with_parallel_workers_waits_for_running_and_drops_rest(monkeypatch):
    fakes = _install(monkeypatch, _kill_all_but(set(), MANY), delay=0.1)
    run = MutationEngine(workers=2).run_detailed(
        MANY, TESTS, should_cancel=lambda: len(fakes.mutant_calls) >= 1
    )
    assert 1 <= run.report.total <= 2
    assert run.report.total == len(fakes.mutant_calls) == run.report.killed
    assert run.report.total < len(generate_all(MANY))


def test_cancel_before_first_mutant_gives_empty_report(monkeypatch):
    fakes = _install(monkeypatch, _kill_all_but(set()))
    report, _ = MutationEngine().run(ORIGINAL, TESTS, should_cancel=lambda: True)
    assert report.total == 0
    assert fakes.mutant_calls == []


def test_max_total_seconds_stops_loop(monkeypatch):
    fakes = _install(monkeypatch, _kill_all_but(set()))
    # Negatif süre sınırı, geçen süreden (>= 0) her zaman küçüktür: döngü hemen durur.
    report, stats = MutationEngine(max_total_seconds=-1.0).run(ORIGINAL, TESTS)
    assert report.total == 0
    assert stats.generated == 2
    assert fakes.mutant_calls == []


def test_max_total_seconds_also_stops_skipped_mutants(monkeypatch):
    _install(monkeypatch, _kill_all_but(set(), COND), all_lines={1, 2, 3, 4}, covered_lines={1, 2})
    run = MutationEngine(max_total_seconds=-1.0).run_detailed(COND, TESTS)
    assert run.report.total == 0 and run.skipped_uncovered == 0


# --- kapsanmayan satırdaki mutantlar -----------------------------------------------------------


def test_mutants_on_uncovered_lines_are_skipped_but_counted_as_survived(monkeypatch):
    fakes = _install(
        monkeypatch, _kill_all_but(set(), COND), all_lines={1, 2, 3, 4}, covered_lines={1, 2, 3}
    )
    seen: list[tuple[int, int]] = []
    run = MutationEngine(workers=1).run_detailed(
        COND, TESTS, progress_callback=lambda d, t: seen.append((d, t))
    )
    assert run.skipped_uncovered == 1
    assert (run.report.total, run.report.killed, run.report.survived) == (5, 4, 1)
    assert [(m.operator, m.line) for m in run.survivors] == [("RETURN_NONE", 4)]
    assert len(fakes.mutant_calls) == 4  # satır 4'teki mutant hiç koşturulmadı
    assert seen[0] == (1, 5) and seen[-1] == (5, 5) and len(seen) == 5


def test_header_mutants_run_even_if_body_is_uncovered(monkeypatch):
    fakes = _install(
        monkeypatch, _kill_all_but(set(), COND), all_lines={1, 2, 3, 4}, covered_lines={1, 2}
    )
    run = MutationEngine(workers=1).run_detailed(COND, TESTS)
    assert run.skipped_uncovered == 3  # satır 3 (x2) ve 4
    assert len(fakes.mutant_calls) == 2  # satır 2'deki ROR ve CONST koşturuldu
    assert {(m.operator, m.line) for m in run.survivors} == {
        ("CONST", 3),
        ("RETURN_NONE", 3),
        ("RETURN_NONE", 4),
    }


def test_line_missing_from_all_lines_is_never_skipped(monkeypatch):
    fakes = _install(
        monkeypatch, _kill_all_but(set(), COND), all_lines={1, 2, 3}, covered_lines={1, 2, 3}
    )
    run = MutationEngine(workers=1).run_detailed(COND, TESTS)
    assert run.skipped_uncovered == 0
    assert len(fakes.mutant_calls) == 5


def test_no_coverage_data_means_nothing_is_skipped(monkeypatch):
    fakes = _install(monkeypatch, _kill_all_but(set(), COND))  # all_lines boş
    run = MutationEngine(workers=1).run_detailed(COND, TESTS)
    assert run.skipped_uncovered == 0 and len(fakes.mutant_calls) == 5


def test_multiline_statement_covered_is_not_skipped(monkeypatch):
    # Satır 5 devam satırıdır; ifade satır 4'te başlar ve kapsanmıştır.
    fakes = _install(
        monkeypatch, _kill_all_but(set(), MULTI), all_lines={1, 2, 3, 4}, covered_lines={1, 2, 3, 4}
    )
    run = MutationEngine(workers=1).run_detailed(MULTI, TESTS)
    assert run.skipped_uncovered == 0
    assert len(fakes.mutant_calls) == 5


def test_multiline_statement_uncovered_is_skipped_by_its_start_line(monkeypatch):
    fakes = _install(
        monkeypatch, _kill_all_but(set(), MULTI), all_lines={1, 2, 3, 4}, covered_lines={1, 2, 3}
    )
    run = MutationEngine(workers=1).run_detailed(MULTI, TESTS)
    # Satır 4'teki AOR/RETURN_NONE ve devam satırı 5'teki CONST atlanır; satır 3'tekiler koşar.
    assert run.skipped_uncovered == 3
    assert len(fakes.mutant_calls) == 2
    assert {(m.operator, m.line) for m in run.survivors} == {
        ("AOR", 4),
        ("RETURN_NONE", 4),
        ("CONST", 5),
    }


def test_statement_start_picks_innermost_statement():
    tree = ast.parse(MULTI)
    assert _statement_start(tree, 1) == 1  # def satırı
    assert _statement_start(tree, 2) == 2  # if başlığı (gövde satır 3'te)
    assert _statement_start(tree, 3) == 3  # iç içe return, if'i değil kendisini verir
    assert _statement_start(tree, 4) == 4
    assert _statement_start(tree, 5) == 4  # çok satırlı ifadenin devam satırı
    assert _statement_start(tree, 99) is None


def test_statement_start_multiline_condition_maps_to_compound_header():
    src = "def f(a, b):\n    if (a >\n            b and a):\n        return 1"
    tree = ast.parse(src)
    assert _statement_start(tree, 3) == 2
    assert _statement_start(tree, 4) == 4


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
    assert run.skipped_uncovered == 1  # `return 2` testlerce hiç çalıştırılmıyor
    assert run.stats.generated == 1 and run.stats.compilation_rate == 1.0
