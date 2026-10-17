"""Coverage sayfasının Qt'siz mantığı: satır durumları, tablo satırları ve özet metinleri."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from testzede.domain.models import TestCase

if TYPE_CHECKING:  # yalnızca tip ipucu: GUI çekirdek modülleri çalışma zamanında import etmez
    from testzede.execution.coverage_runner import ExecutionResult

LineStatus = Literal["covered", "partial", "missed"]

_NEWLINE = re.compile(r"\r\n|\r|\n")
_NO_DATA = "—"


def source_lines(source: str) -> list[str]:
    """Kaynağı Python'un satır numaralandırmasıyla satırlara böler (sondaki boş satır atılır)."""
    lines = _NEWLINE.split(source)
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def line_statuses(result: ExecutionResult) -> dict[int, LineStatus]:
    """Çalıştırılabilir her satır için ``covered`` / ``partial`` / ``missed`` döndürür.

    Dalı olmayan satır: ``covered_lines``'ta ise covered, değilse missed. Dallı satırda
    (``all_branches`` içinde kaynağı bu satır olan arc'lar; çıkış arc'ları, yani negatif
    hedefler de dahil): satır hiç çalışmadıysa missed, tüm dalları kapsandıysa covered,
    aksi halde partial. Satır çalışmış ama hiçbir dalı kapsanmamışsa da partial sayılır.
    """
    branches_from: dict[int, set[tuple[int, int]]] = {}
    for arc in result.all_branches:
        branches_from.setdefault(arc[0], set()).add(arc)

    statuses: dict[int, LineStatus] = {}
    for line in sorted(result.all_lines):
        if line not in result.covered_lines:
            statuses[line] = "missed"
            continue
        arcs = branches_from.get(line, set())
        statuses[line] = "covered" if arcs <= result.covered_branches else "partial"
    return statuses


def function_rows(result: ExecutionResult) -> list[tuple[str, float]]:
    """``(fonksiyon adı, kapsama yüzdesi 0-100)`` satırlarını ada göre sıralı döndürür."""
    return sorted((name, rate * 100) for name, rate in result.coverage.per_function.items())


def outcome_rows(tests: list[TestCase], result: ExecutionResult) -> list[tuple[str, str]]:
    """Her test için ``(test adı, sonuç)`` döndürür; sonucu olmayan test "error" sayılır.

    ``ExecutionResult.test_outcomes`` test *adıyla* anahtarlıdır (indeksle değil).
    """
    return [(test.name, result.test_outcomes.get(test.name, "error")) for test in tests]


def _percent(covered: int, total: int) -> str:
    """``"75.0% (3/4)"`` biçimi; toplam sıfırsa veri yok işareti."""
    if total == 0:
        return _NO_DATA
    return f"{covered / total * 100:.1f}% ({covered}/{total})"


@dataclass(frozen=True)
class CoverageSummary:
    """Özet etiketlerinde gösterilecek biçimlenmiş metinler."""

    lines: str
    branches: str
    compilation: str
    time: str


def summary(result: ExecutionResult) -> CoverageSummary:
    """Satır %, dal %, derleme oranı ve süre için biçimlenmiş metinleri üretir."""
    coverage, stats = result.coverage, result.stats
    return CoverageSummary(
        lines=_percent(coverage.covered_lines, coverage.total_lines),
        branches=_percent(coverage.covered_branches, coverage.total_branches),
        compilation=_percent(stats.compiled, stats.generated),
        time=f"{stats.execution_time_s:.2f} sn",
    )


def empty_summary() -> CoverageSummary:
    """Henüz sonuç yokken gösterilen özet."""
    return CoverageSummary(_NO_DATA, _NO_DATA, _NO_DATA, _NO_DATA)
