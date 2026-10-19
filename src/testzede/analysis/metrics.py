"""Kaynak koddan 14 kod metriği üretir (US-2).

Metrikler radon ile hesaplanır: ``raw`` (satır sayıları), ``metrics.h_visit``
(Halstead), ``complexity.cc_visit`` (McCabe) ve ``metrics.mi_visit``
(Sürdürülebilirlik İndeksi).
"""

from __future__ import annotations

from radon.complexity import cc_visit
from radon.metrics import h_visit, mi_rank, mi_visit
from radon.raw import analyze
from radon.visitors import Function

from testzede.analysis.parsing import SourceError, parse_python, quiet_warnings
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


# Arayüzde (Metrikler sayfası) metriğin yanında gösterilen kısa açıklamalar.
METRIC_DESCRIPTIONS: dict[str, str] = {
    "LOC": "Toplam satır sayısı (boş ve yorum satırları dahil).",
    "LLOC": "Mantıksal satır sayısı (deyim sayısı).",
    "SLOC": "Kaynak satır sayısı (boş ve yorum satırları hariç).",
    "Yorum": "'#' ile başlayan yorum satırı sayısı.",
    "Çoklu Satır": "Çok satırlı metin (örn. docstring) satırı sayısı.",
    "Boş Satır": "Boş satır sayısı.",
    "Halstead Zorluk": "Kodu yazmanın ve anlamanın zorluğu: (benzersiz işleç / 2) × "
    "(toplam işlenen / benzersiz işlenen).",
    "Halstead Çaba": "Zorluk × Hacim: kodu yazmak için gereken zihinsel çaba.",
    "Halstead Uzunluk": "Toplam işleç ve işlenen sayısı.",
    "Halstead Zaman": "Tahmini geliştirme süresi (saniye): Çaba / 18.",
    "Halstead Kelime Haznesi": "Benzersiz işleç ve işlenen sayısı.",
    "Halstead Hacim": "Uzunluk × log2(Kelime Haznesi): programın bilgi miktarı.",
    "Çevrimsel Karmaşıklık": "McCabe: tüm fonksiyonların karar noktası + 1 toplamı "
    "(bağımsız yol sayısı); fonksiyon yoksa 1.",
    "Sürdürülebilirlik İndeksi": "0-100 arası; yüksek değer bakımı kolay kod demektir "
    "(A: > 19, B: 10-19, C: <= 9).",
}


class MetricsError(ValueError):
    """Kaynak kod ayrıştırılamadığı için metrik hesaplanamadı."""


def maintainability_rank(score: float) -> str:
    """Sürdürülebilirlik indeksinin harf derecesi: ``A`` (iyi), ``B`` (orta), ``C`` (düşük)."""
    return str(mi_rank(score))


def compute_metrics(source: str) -> MetricSet:
    """Verilen Python kaynak kodu için 14 metriği hesaplar.

    Çevrimsel karmaşıklık, koddaki tüm fonksiyon ve metotların McCabe
    karmaşıklıklarının toplamıdır; fonksiyon yoksa 1'dir (tek yol).
    ``Yorum`` yalnızca ``#`` ile başlayan yorum satırlarını sayar.

    Raises:
        MetricsError: Kaynak ayrıştırılamıyorsa (söz dizimi hatası, null bayt vb.).
    """
    try:
        parse_python(source)  # radon'un söz dizimi hataları satır numarası taşımaz
    except SourceError as exc:
        raise MetricsError(str(exc)) from exc
    try:
        with quiet_warnings():
            raw = analyze(source)
            halstead = h_visit(source).total
            blocks = cc_visit(source)
            maintainability = mi_visit(source, multi=True)
    except SyntaxError as exc:
        raise MetricsError(f"Kod ayrıştırılamadı: {exc}") from exc

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
