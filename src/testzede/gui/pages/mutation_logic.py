"""Mutasyon sayfasının Qt'siz mantığı: özet metinleri, hayatta kalan mutantlar ve fark."""

from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # yalnızca tip ipucu: GUI çekirdek modülleri çalışma zamanında import etmez
    from testzede.mutation.engine import MutationRun
    from testzede.mutation.operators import Mutant

_NO_DATA = "—"
_HUNK_SEPARATOR = "⋯"


@dataclass(frozen=True)
class MutationSummary:
    """Özet etiketlerinde gösterilecek biçimlenmiş metinler."""

    score: str
    killed: str
    survived: str
    timeout: str
    skipped: str
    compilation: str
    time: str


def summary_texts(run: MutationRun) -> MutationSummary:
    """Skoru (%), mutant sayılarını, derleme oranını ve test süresini biçimler."""
    report, stats = run.report, run.stats
    score = f"{report.score * 100:.1f}%" if report.total else _NO_DATA
    compilation = (
        f"{stats.compilation_rate * 100:.1f}% ({stats.compiled}/{stats.generated})"
        if stats.generated
        else _NO_DATA
    )
    return MutationSummary(
        score=score,
        killed=str(report.killed),
        survived=str(report.survived),
        timeout=str(report.timeout),
        skipped=str(run.skipped_uncovered),
        compilation=compilation,
        time=f"{stats.execution_time_s:.2f} sn",
    )


def empty_summary() -> MutationSummary:
    """Henüz sonuç yokken gösterilen özet."""
    return MutationSummary(*([_NO_DATA] * 7))


def sorted_survivors(run: MutationRun) -> list[Mutant]:
    """Hayatta kalan mutantları (satır, operatör, açıklama) sırasıyla döndürür."""
    return sorted(run.survivors, key=lambda m: (m.line, m.operator, m.description))


def survivor_rows(run: MutationRun) -> list[tuple[str, int, str]]:
    """Tablo için ``(operatör, satır, açıklama)`` satırları; satıra göre sıralı."""
    return [(m.operator, m.line, m.description) for m in sorted_survivors(run)]


def mutant_diff(original: str, mutant_source: str) -> str:
    """Orijinal ile mutant arasındaki satır bazlı farkı döndürür (başlıksız, 2 satır bağlam).

    Mutant kaynağı ``ast.unparse`` çıktısıdır; orijinal de aynı biçime getirilir ki fark
    yalnızca mutasyonu göstersin (yorum/biçim farkları görünmesin). Parçalar ``⋯`` ile ayrılır.
    Fark yoksa boş metin döner.
    """
    try:
        normalized = ast.unparse(ast.parse(original))
    except (SyntaxError, ValueError):
        normalized = original
    diff = list(
        difflib.unified_diff(normalized.splitlines(), mutant_source.splitlines(), lineterm="", n=2)
    )
    out: list[str] = []
    for line in diff[2:]:  # ilk iki satır "---"/"+++" başlıklarıdır
        if line.startswith("@@"):
            if out:
                out.append(_HUNK_SEPARATOR)
            continue
        out.append(line)
    return "\n".join(out)
