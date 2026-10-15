"""Modüller arası ortak veri modelleri (sözleşme).

Bu dosyadaki değişiklikler PR'da üç kişinin de onayını gerektirir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class CodeUnit:
    """Test edilecek kod birimi."""

    uid: str  # "HumanEval/12", "small67/5", "<repo>::<modül>.<fonk>"
    source: str
    entry_point: str | None = None  # test edilecek fonksiyon adı
    dataset: str | None = None
    seed_examples: tuple[str, ...] = ()  # docstring'deki >>> örnekleri


@dataclass
class TestCase:
    """Tek bir pytest fonksiyonu."""

    __test__ = False  # pytest bu sınıfı test olarak toplamasın

    name: str
    code: str
    origin: Literal["user", "rl"]


@dataclass
class CoverageReport:
    covered_lines: int
    total_lines: int
    covered_branches: int
    total_branches: int
    per_function: dict[str, float] = field(default_factory=dict)

    @property
    def line_rate(self) -> float:
        return self.covered_lines / self.total_lines if self.total_lines else 0.0


@dataclass
class MetricSet:
    values: dict[str, float]  # anahtarlar metrics.METRIC_NAMES


@dataclass
class MutationReport:
    total: int
    killed: int
    survived: int
    timeout: int

    @property
    def score(self) -> float:
        return (self.killed + self.timeout) / self.total if self.total else 0.0


@dataclass
class RunStats:
    generated: int
    compiled: int
    execution_time_s: float

    @property
    def compilation_rate(self) -> float:
        return self.compiled / self.generated if self.generated else 0.0


@dataclass
class Prediction:
    estimated_bugs: float
    optimum_test_count: int
    method: str
