"""``coverage run --branch -m pytest`` sarmalayıcısı. Gövde henüz yazılmadı."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from testzede.domain.models import CodeUnit, CoverageReport, RunStats, TestCase


@dataclass
class ExecutionResult:
    coverage: CoverageReport
    stats: RunStats
    covered_lines: frozenset[int]
    # coverage.py arc'ları (çıkış için negatif olabilir)
    covered_branches: frozenset[tuple[int, int]]
    all_lines: frozenset[int]
    all_branches: frozenset[tuple[int, int]]
    # anahtar: TestCase.name
    test_outcomes: dict[str, Literal["passed", "failed", "error", "timeout"]]


def run_tests(
    unit: CodeUnit, tests: Sequence[TestCase], *, timeout: float = 10.0
) -> ExecutionResult:
    """Testleri alt süreçte koşturur; yalnızca ``unit.source`` ölçülür.

    Hiçbir koşulda istisna fırlatmaz; derleme hatası/timeout ``test_outcomes`` içinde döner.
    """
    raise NotImplementedError
