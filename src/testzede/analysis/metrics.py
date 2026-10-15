"""Kaynak koddan 14 kod metriği üretir (US-2).

Metrikler radon ile hesaplanır: ``raw`` (satır sayıları), ``metrics.h_visit``
(Halstead), ``complexity.cc_visit`` (McCabe) ve ``metrics.mi_visit``
(Sürdürülebilirlik İndeksi).
"""

from __future__ import annotations

from radon.complexity import cc_visit
from radon.metrics import h_visit, mi_visit
from radon.raw import analyze
from radon.visitors import Function

from testzede.domain.models import MetricSet

METRIC_NAMES: tuple[str, ...] = (
    "LOC",
    "LLOC",
    "SLOC",
    "Yorum",
    "Çoklu Satır",
    "Boş Satır",
    "Halstead Zorluk",
    "Halstead Çaba",
    "Halstead Uzunluk",
    "Halstead Zaman",
    "Halstead Kelime Haznesi",
    "Halstead Hacim",
    "Çevrimsel Karmaşıklık",
    "Sürdürülebilirlik İndeksi",
)


class MetricsError(ValueError):
    """Kaynak kod ayrıştırılamadığı için metrik hesaplanamadı."""


def compute_metrics(source: str) -> MetricSet:
    """Verilen Python kaynak kodu için 14 metriği hesaplar.

    Çevrimsel karmaşıklık, koddaki tüm fonksiyon ve metotların McCabe
    karmaşıklıklarının toplamıdır; fonksiyon yoksa 1'dir (tek yol).
    ``Yorum`` yalnızca ``#`` ile başlayan yorum satırlarını sayar.

    Raises:
        MetricsError: Kaynak geçerli Python söz dizimi değilse.
    """
    try:
        raw = analyze(source)
        halstead = h_visit(source).total
        blocks = cc_visit(source)
        maintainability = mi_visit(source, multi=True)
    except SyntaxError as exc:
        raise MetricsError(f"Kod ayrıştırılamadı (satır {exc.lineno}): {exc.msg}") from exc

    complexity = sum(b.complexity for b in blocks if isinstance(b, Function)) or 1

    values = {
        "LOC": raw.loc,
        "LLOC": raw.lloc,
        "SLOC": raw.sloc,
        "Yorum": raw.comments,
        "Çoklu Satır": raw.multi,
        "Boş Satır": raw.blank,
        "Halstead Zorluk": halstead.difficulty,
        "Halstead Çaba": halstead.effort,
        "Halstead Uzunluk": halstead.length,
        "Halstead Zaman": halstead.time,
        "Halstead Kelime Haznesi": halstead.vocabulary,
        "Halstead Hacim": halstead.volume,
        "Çevrimsel Karmaşıklık": complexity,
        "Sürdürülebilirlik İndeksi": maintainability,
    }
    return MetricSet(values={name: float(values[name]) for name in METRIC_NAMES})
