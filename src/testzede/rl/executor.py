"""RL'nin çalıştırma katmanından beklediği sözleşme.

``execution`` modülündeki ``sandbox.call_function`` ve
``coverage_runner.run_tests`` bu protokolleri yapısal olarak karşılar. RL kodu
somut sınıflara değil bu protokollere bağlıdır; böylece testlerde sahte bir
çalıştırıcı kullanılabilir.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, Protocol

from testzede.domain.models import CodeUnit, RunStats, TestCase

TARGET_MODULE = "target"
"""Üretilen testlerin kaynağı import ettiği modül adı (``execution.sandbox.TARGET_MODULE``)."""


class CallOutcome(Protocol):
    """Girdinin referans çözümde tek seferlik çalıştırılmasının sonucu (oracle)."""

    @property
    def status(self) -> Literal["ok", "raised", "timeout", "error"]: ...
    @property
    def value_repr(self) -> str | None: ...
    @property
    def exc_type(self) -> str | None: ...
    @property
    def duration_s(self) -> float: ...


class TestRunOutcome(Protocol):
    """Test(ler)in coverage ile çalıştırılmasının sonucu."""

    __test__ = False  # pytest bu sınıfı test olarak toplamasın

    @property
    def stats(self) -> RunStats: ...
    @property
    def covered_lines(self) -> frozenset[int]: ...
    @property
    def covered_branches(self) -> frozenset[tuple[int, int]]: ...
    @property
    def all_lines(self) -> frozenset[int]: ...
    @property
    def all_branches(self) -> frozenset[tuple[int, int]]: ...
    @property
    def test_outcomes(self) -> Mapping[str, Literal["passed", "failed", "error", "timeout"]]: ...


class Executor(Protocol):
    """Kodu sandbox'ta çalıştıran nesne. Hiçbir metot istisna fırlatmamalıdır."""

    def call_function(
        self, unit: CodeUnit, args_repr: str, *, timeout: float = 2.0
    ) -> CallOutcome: ...

    def run_tests(
        self, unit: CodeUnit, tests: Sequence[TestCase], *, timeout: float = 10.0
    ) -> TestRunOutcome: ...
