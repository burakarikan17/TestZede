"""Mutasyon motoru: mutantları mevcut ``run_tests`` ile testlere karşı koşturur."""

from __future__ import annotations

import ast
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from testzede.domain.models import CodeUnit, MutationReport, RunStats, TestCase
from testzede.execution.coverage_runner import run_tests
from testzede.mutation.operators import Mutant, generate_all

BASELINE_TIMEOUT = 10.0
_MIN_MUTANT_TIMEOUT = 2.0
_TIMEOUT_FACTOR = 5.0


class MutationError(Exception):
    """Kullanıcıya gösterilebilecek anlaşılır (Türkçe) bir mutasyon hatası."""


@dataclass(frozen=True)
class MutationRun:
    """Mutasyon çalıştırmasının ayrıntılı sonucu."""

    report: MutationReport
    stats: RunStats
    survivors: list[Mutant]


def _first_function_name(tree: ast.Module) -> str | None:
    """Kaynaktaki ilk üst düzey fonksiyonun adını döndürür; yoksa ``None``."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    return None


class MutationEngine:
    """Mutant üretir, her birini testlere karşı koşturur ve öldürülen/hayatta kalanları sayar."""

    def __init__(
        self,
        max_mutants: int | None = 100,
        seed: int = 0,
        max_total_seconds: float = 120.0,
    ) -> None:
        self._max_mutants = max_mutants
        self._seed = seed
        self._max_total_seconds = max_total_seconds

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
        İptal ya da toplam süre aşımında o ana kadarki sonuç döner.
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
        outcomes = baseline.test_outcomes
        bad = sorted(n for n, o in outcomes.items() if o in ("failed", "timeout"))
        if bad:
            raise MutationError(
                "Testler orijinal kodda geçmiyor, mutasyon analizi yapılamaz. "
                f"Başarısız testler: {', '.join(bad)}"
            )
        # Orijinalde derlenemeyen testler karar dışı: yoksa her mutant öldü sayılırdı.
        ignored = {n for n, o in outcomes.items() if o == "error"}
        if not any(o == "passed" for o in outcomes.values()):
            raise MutationError("Orijinal kodda geçen hiçbir test yok, mutasyon analizi yapılamaz.")

        try:
            mutants = generate_all(source)
        except ValueError as exc:
            raise MutationError(f"Mutant üretilemedi: {exc}") from exc
        mutants = self._sample(mutants)

        timeout = max(_MIN_MUTANT_TIMEOUT, baseline.stats.execution_time_s * _TIMEOUT_FACTOR)
        total = len(mutants)
        killed = survived = timed_out = 0
        survivors: list[Mutant] = []
        for done, mutant in enumerate(mutants, start=1):
            if should_cancel is not None and should_cancel():
                break
            if time.monotonic() - started > self._max_total_seconds:
                break
            result = run_tests(replace(unit, source=mutant.source), tests, timeout=timeout)
            decisive = [o for n, o in result.test_outcomes.items() if n not in ignored]
            if "timeout" in decisive:
                timed_out += 1
            elif any(o in ("failed", "error") for o in decisive):
                killed += 1
            else:
                survived += 1
                survivors.append(mutant)
            if progress_callback is not None:
                progress_callback(done, total)

        executed = killed + survived + timed_out
        report = MutationReport(total=executed, killed=killed, survived=survived, timeout=timed_out)
        return MutationRun(report=report, stats=baseline.stats, survivors=survivors)

    def _sample(self, mutants: list[Mutant]) -> list[Mutant]:
        """Fazla mutantı tohumlu örnekler; sonuç kaynak sırasında kalır."""
        if self._max_mutants is None or len(mutants) <= self._max_mutants:
            return mutants
        rng = random.Random(self._seed)
        picked = sorted(rng.sample(range(len(mutants)), self._max_mutants))
        return [mutants[i] for i in picked]
