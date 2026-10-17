"""Sayfalar arasında paylaşılan uygulama durumu."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from testzede.domain.models import TestCase

if TYPE_CHECKING:  # yalnızca tip ipucu: GUI çekirdek modülleri çalışma zamanında import etmez
    from testzede.execution.coverage_runner import ExecutionResult
    from testzede.mutation.engine import MutationRun


@dataclass
class AppState:
    """Yüklenen kod, testler ve son analiz sonuçları."""

    source: str = ""
    tests: list[TestCase] = field(default_factory=list)
    execution_result: ExecutionResult | None = None
    mutation_run: MutationRun | None = None
    module_name: str | None = None  # kaynak dosyanın adı (uzantısız); yapıştırılan kodda None

    def reset(self) -> None:
        """Tüm alanları başlangıç değerlerine döndürür."""
        self.source = ""
        self.module_name = None
        self.tests = []
        self.execution_result = None
        self.mutation_run = None
