"""Mutasyon sayfası için cephe (Facade)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from testzede.domain.models import MutationReport, RunStats, TestCase
from testzede.mutation.engine import MutationError, MutationRun
from testzede.services.errors import ServiceError

ProgressCallback = Callable[[int, int], None]
CancelCallback = Callable[[], bool]


class MutationEngine(Protocol):
    """Mutasyon motoru arayüzü (gerçek motor: ``mutation.engine.MutationEngine``)."""

    def run(
        self,
        source: str,
        tests: list[TestCase],
        progress_callback: ProgressCallback | None = None,
        should_cancel: CancelCallback | None = None,
    ) -> tuple[MutationReport, RunStats]:
        """Mutantları testlere karşı koşturur; ilerlemeyi ``(biten, toplam)`` olarak bildirir."""
        ...

    def run_detailed(
        self,
        source: str,
        tests: list[TestCase],
        progress_callback: ProgressCallback | None = None,
        should_cancel: CancelCallback | None = None,
    ) -> MutationRun:
        """``run`` gibi çalışır; hayatta kalan mutantları da döndürür."""
        ...


class MutationService:
    """Mutasyon analizini GUI'ye sunar."""

    def __init__(self, engine: MutationEngine | None = None) -> None:
        self._engine = engine

    def _require_engine(self) -> MutationEngine:
        """Motoru döndürür; bağlı değilse ``ServiceError`` fırlatır."""
        if self._engine is None:
            raise ServiceError("Mutasyon motoru henüz bağlı değil")
        return self._engine

    def run(
        self,
        source: str,
        tests: list[TestCase],
        progress_callback: ProgressCallback | None = None,
        should_cancel: CancelCallback | None = None,
    ) -> tuple[MutationReport, RunStats]:
        """Motoru çağırır; motor yoksa ya da ``MutationError`` verirse ``ServiceError`` fırlatır."""
        engine = self._require_engine()
        try:
            return engine.run(source, tests, progress_callback, should_cancel)
        except MutationError as exc:
            raise ServiceError(str(exc)) from exc

    def run_detailed(
        self,
        source: str,
        tests: list[TestCase],
        progress_callback: ProgressCallback | None = None,
        should_cancel: CancelCallback | None = None,
    ) -> MutationRun:
        """``run`` gibi çalışır; hayatta kalan mutantlarla birlikte ``MutationRun`` döndürür."""
        engine = self._require_engine()
        try:
            return engine.run_detailed(source, tests, progress_callback, should_cancel)
        except MutationError as exc:
            raise ServiceError(str(exc)) from exc


def create_mutation_service(max_mutants: int = 100) -> MutationService:
    """Gerçek mutasyon motoruyla (en fazla ``max_mutants`` mutant) bir ``MutationService`` kurar."""
    from testzede.mutation.engine import MutationEngine as CoreMutationEngine

    return MutationService(CoreMutationEngine(max_mutants=max_mutants))
