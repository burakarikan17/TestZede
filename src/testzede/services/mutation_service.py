"""Mutasyon sayfası için cephe (Facade)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from testzede.domain.models import MutationReport, RunStats, TestCase
from testzede.mutation.engine import MutationError
from testzede.services.errors import ServiceError


class MutationEngine(Protocol):
    """Mutasyon motoru arayüzü; gerçek motor ``mutation/`` altında yazılacak."""

    def run(
        self,
        source: str,
        tests: list[TestCase],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> tuple[MutationReport, RunStats]:
        """Mutantları testlere karşı koşturur; ilerlemeyi ``(biten, toplam)`` olarak bildirir."""
        ...


class MutationService:
    """Mutasyon analizini GUI'ye sunar."""

    def __init__(self, engine: MutationEngine | None = None) -> None:
        self._engine = engine

    def run(
        self,
        source: str,
        tests: list[TestCase],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> tuple[MutationReport, RunStats]:
        """Motoru çağırır; motor yoksa ya da ``MutationError`` verirse ``ServiceError`` fırlatır."""
        if self._engine is None:
            raise ServiceError("Mutasyon motoru henüz bağlı değil")
        try:
            return self._engine.run(source, tests, progress_callback)
        except MutationError as exc:
            raise ServiceError(str(exc)) from exc
