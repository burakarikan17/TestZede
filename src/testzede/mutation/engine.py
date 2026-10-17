"""Mutasyon motoru: mutantları coverage'sız hızlı yolla, paralel olarak testlere karşı koşturur."""

from __future__ import annotations

import ast
import os
import random
import time
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace

from testzede.domain.models import CodeUnit, MutationReport, RunStats, TestCase
from testzede.execution.coverage_runner import ExecutionResult, run_outcomes, run_tests
from testzede.mutation.operators import Mutant, generate_all

BASELINE_TIMEOUT = 10.0
_MIN_MUTANT_TIMEOUT = 3.0
_TIMEOUT_FACTOR = 5.0
_POLL_SECONDS = 0.1


class MutationError(Exception):
    """Kullanıcıya gösterilebilecek anlaşılır (Türkçe) bir mutasyon hatası."""


@dataclass(frozen=True)
class MutationRun:
    """Mutasyon çalıştırmasının ayrıntılı sonucu."""

    report: MutationReport
    stats: RunStats
    survivors: list[Mutant]
    skipped_uncovered: int = 0  # testlerin hiç çalıştırmadığı satırda olduğu için koşulmayanlar


def _first_function_name(tree: ast.Module) -> str | None:
    """Kaynaktaki ilk üst düzey fonksiyonun adını döndürür; yoksa ``None``."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    return None


def _statement_start(tree: ast.Module, line: int) -> int | None:
    """``line``'ı kapsayan en iç ifadenin (``ast.stmt``) başlangıç satırını döndürür."""
    best: ast.stmt | None = None
    best_span = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt):
            continue
        end = node.end_lineno or node.lineno
        if node.lineno <= line <= end and (best is None or end - node.lineno < best_span):
            best, best_span = node, end - node.lineno
    return best.lineno if best is not None else None


def _default_workers() -> int:
    """Varsayılan paralel işçi sayısı: çekirdek sayısı - 2, en az 1, en çok 6."""
    return max(1, min(6, (os.cpu_count() or 2) - 2))


def _classify(
    unit: CodeUnit,
    mutant: Mutant,
    tests: Sequence[TestCase],
    timeout: float,
    ignored: set[str],
) -> str:
    """Mutantı koşturur: ``timeout`` / ``killed`` / ``survived``. Karar dışı testler sayılmaz."""
    outcomes = run_outcomes(replace(unit, source=mutant.source), tests, timeout=timeout)
    decisive = [o for name, o in outcomes.items() if name not in ignored]
    if "timeout" in decisive:
        return "timeout"
    if any(o in ("failed", "error") for o in decisive):
        return "killed"
    return "survived"


class MutationEngine:
    """Mutant üretir, her birini testlere karşı koşturur ve öldürülen/hayatta kalanları sayar."""

    def __init__(
        self,
        max_mutants: int | None = 100,
        seed: int = 0,
        max_total_seconds: float = 120.0,
        workers: int | None = None,
    ) -> None:
        self._max_mutants = max_mutants
        self._seed = seed
        self._max_total_seconds = max_total_seconds
        self._workers = max(1, workers) if workers is not None else _default_workers()

    def run(
        self,
        source: str,
        tests: list[TestCase],
        progress_callback: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[MutationReport, RunStats]:
        """:meth:`run_detailed` sonucunun ``(report, stats)`` kısmını döndürür."""
        run = self.run_detailed(source, tests, progress_callback, should_cancel)
        return run.report, run.stats

    def run_detailed(
        self,
        source: str,
        tests: list[TestCase],
        progress_callback: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> MutationRun:
        """Mutasyon analizini çalıştırır; hayatta kalan mutantları da döndürür.

        Baseline başarısızsa ya da kaynak geçersizse ``MutationError`` fırlatır.
        İptal ya da toplam süre aşımında o ana kadarki sonuç döner. ``progress_callback``
        yalnızca çağıran iş parçacığından, tamamlanma sırasıyla çağrılır.
        """
        started = time.monotonic()
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError) as exc:
            raise MutationError(f"Kaynak kod geçerli bir Python kodu değil: {exc}") from exc
        unit = CodeUnit(
            uid="user/0", source=source, entry_point=_first_function_name(tree), dataset=None
        )

        baseline = run_tests(unit, tests, timeout=BASELINE_TIMEOUT)
        ignored = self._check_baseline(baseline)

        try:
            mutants = generate_all(source)
        except ValueError as exc:
            raise MutationError(f"Mutant üretilemedi: {exc}") from exc
        mutants = self._sample(mutants)

        total = len(mutants)
        timeout = max(_MIN_MUTANT_TIMEOUT, baseline.stats.execution_time_s * _TIMEOUT_FACTOR)
        status: dict[int, str] = {}
        stopped = False

        def stop() -> bool:
            nonlocal stopped
            stopped = stopped or bool(
                (should_cancel is not None and should_cancel())
                or time.monotonic() - started > self._max_total_seconds
            )
            return stopped

        def record(index: int, result: str) -> None:
            status[index] = result
            if progress_callback is not None:
                progress_callback(len(status), total)

        # Testlerin hiç çalıştırmadığı satırdaki mutantlar koşturulmadan "survived" sayılır.
        skipped, to_run = [], []
        for index, mutant in enumerate(mutants):
            start = _statement_start(tree, mutant.line)
            uncovered = (
                start is not None
                and start in baseline.all_lines
                and start not in baseline.covered_lines
            )
            (skipped if uncovered else to_run).append(index)
        skipped_count = 0
        for index in skipped:
            if stop():
                break
            skipped_count += 1
            record(index, "survived")

        if not stopped:
            self._run_parallel(mutants, to_run, unit, tests, timeout, ignored, stop, record)

        survivors = [mutants[i] for i in sorted(status) if status[i] == "survived"]
        results = list(status.values())
        report = MutationReport(
            total=len(results),
            killed=results.count("killed"),
            survived=results.count("survived"),
            timeout=results.count("timeout"),
        )
        return MutationRun(
            report=report,
            stats=baseline.stats,
            survivors=survivors,
            skipped_uncovered=skipped_count,
        )

    def _run_parallel(
        self,
        mutants: list[Mutant],
        to_run: list[int],
        unit: CodeUnit,
        tests: Sequence[TestCase],
        timeout: float,
        ignored: set[str],
        stop: Callable[[], bool],
        record: Callable[[int, str], None],
    ) -> None:
        """Mutantları en fazla ``workers`` tanesi aynı anda koşacak şekilde işler.

        İptal/süre aşımında yeni iş verilmez, başlamamış işler iptal edilir ve çalışanların
        bitmesi beklenir.
        """
        pending: dict[Future[str], int] = {}
        cursor = 0
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            while True:
                halted = stop()
                if halted:
                    for future in pending:
                        future.cancel()
                while not halted and cursor < len(to_run) and len(pending) < self._workers:
                    index = to_run[cursor]
                    cursor += 1
                    future = pool.submit(_classify, unit, mutants[index], tests, timeout, ignored)
                    pending[future] = index
                if not pending:
                    break
                finished, _ = wait(pending, timeout=_POLL_SECONDS, return_when=FIRST_COMPLETED)
                for future in finished:
                    index = pending.pop(future)
                    if not future.cancelled():
                        record(index, future.result())

    @staticmethod
    def _check_baseline(baseline: ExecutionResult) -> set[str]:
        """Baseline'ı doğrular; karar dışı bırakılacak ("error") test adlarını döndürür."""
        outcomes = baseline.test_outcomes
        bad = sorted(n for n, o in outcomes.items() if o in ("failed", "timeout"))
        if bad:
            raise MutationError(
                "Testler orijinal kodda geçmiyor, mutasyon analizi yapılamaz. "
                f"Başarısız testler: {', '.join(bad)}"
            )
        if not any(o == "passed" for o in outcomes.values()):
            raise MutationError("Orijinal kodda geçen hiçbir test yok, mutasyon analizi yapılamaz.")
        # Orijinalde derlenemeyen testler karar dışı: yoksa her mutant öldü sayılırdı.
        return {n for n, o in outcomes.items() if o == "error"}

    def _sample(self, mutants: list[Mutant]) -> list[Mutant]:
        """Fazla mutantı tohumlu örnekler; sonuç kaynak sırasında kalır."""
        if self._max_mutants is None or len(mutants) <= self._max_mutants:
            return mutants
        rng = random.Random(self._seed)
        picked = sorted(rng.sample(range(len(mutants)), self._max_mutants))
        return [mutants[i] for i in picked]
