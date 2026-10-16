"""Toplu çalıştırma raporları (US-6): veri seti bazında CSV / HTML / XLSX.

Raporlar ``reports/<tarih>/<veri_seti>/`` altına yazılır ve kullanılan split
dosyasının hash değerini içerir (data leakage kuralı 3).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment
from markupsafe import Markup

from testzede.domain.models import (
    CoverageReport,
    MetricSet,
    MutationReport,
    Prediction,
    RunStats,
)

FORMATS: tuple[str, ...] = ("csv", "html", "xlsx")


@dataclass
class UnitResult:
    """Bir kod biriminin hat (metrik → RL → coverage → mutasyon → tahmin) sonucu."""

    uid: str
    dataset: str
    test_count: int = 0
    metrics: MetricSet | None = None
    coverage: CoverageReport | None = None
    mutation: MutationReport | None = None
    stats: RunStats | None = None
    prediction: Prediction | None = None
    error: str | None = None  # hat bu birimde yarıda kaldıysa kullanıcıya gösterilecek mesaj


@dataclass(frozen=True)
class ReportMeta:
    dataset: str
    split: str | None = None  # "external", "main" …
    split_hash: str | None = None
    config: str | None = None  # "configs/frozen.yaml"
    created_at: datetime = field(default_factory=datetime.now)


def file_sha256(path: Path) -> str:
    """Split dosyasının raporlara yazılan hash değeri."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def report_dir(root: Path, dataset: str, when: datetime | None = None) -> Path:
    """``<root>/<YYYY-MM-DD>/<veri_seti>/``; veri seti adı dosya sistemi için güvenli hale getirilir."""
    when = when or datetime.now()
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in dataset) or "dataset"
    return Path(root) / when.strftime("%Y-%m-%d") / safe


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def to_frame(results: Iterable[UnitResult]) -> pd.DataFrame:
    """Birim başına bir satır; eksik aşamalar boş (NaN) kalır."""
    rows = []
    for r in results:
        cov, mut, stats, pred = r.coverage, r.mutation, r.stats, r.prediction
        row: dict[str, object] = {
            "uid": r.uid,
            "dataset": r.dataset,
            "status": "error" if r.error else "ok",
            "tests": r.test_count,
            "line_coverage": cov.line_rate if cov else None,
            "branch_coverage": _rate(cov.covered_branches, cov.total_branches) if cov else None,
            "mutation_score": mut.score if mut and mut.total else None,
            "mutants": mut.total if mut else None,
            "mutants_killed": mut.killed if mut else None,
            "mutants_survived": mut.survived if mut else None,
            "compilation_rate": stats.compilation_rate if stats and stats.generated else None,
            "execution_time_s": stats.execution_time_s if stats else None,
            "estimated_bugs": pred.estimated_bugs if pred else None,
            "optimum_tests": pred.optimum_test_count if pred else None,
        }
        if r.metrics:
            row.update(r.metrics.values)
        row["error"] = r.error or ""
        rows.append(row)
    return pd.DataFrame(rows)


def summarize(frame: pd.DataFrame) -> pd.DataFrame:
    """Veri seti başına özet: ortalama oranlar ve toplam süre/test sayısı."""
    if frame.empty:
        return pd.DataFrame(columns=["dataset", "units", "failed"])
    grouped = frame.groupby("dataset", sort=True)
    summary = pd.DataFrame(
        {
            "units": grouped.size(),
            "failed": grouped["status"].apply(lambda s: int((s == "error").sum())),
            "tests_total": grouped["tests"].sum(),
            "tests_mean": grouped["tests"].mean(),
            "line_coverage_mean": grouped["line_coverage"].mean(),
            "branch_coverage_mean": grouped["branch_coverage"].mean(),
            "mutation_score_mean": grouped["mutation_score"].mean(),
            "compilation_rate_mean": grouped["compilation_rate"].mean(),
            "execution_time_total_s": grouped["execution_time_s"].sum(min_count=1),
        }
    )
    return summary.reset_index()


def _meta_rows(meta: ReportMeta) -> list[tuple[str, str]]:
    return [
        ("Veri seti", meta.dataset),
        ("Split", meta.split or "-"),
        ("Split hash (SHA-256)", meta.split_hash or "-"),
        ("Yapılandırma", meta.config or "-"),
        ("Oluşturulma", meta.created_at.strftime("%Y-%m-%d %H:%M:%S")),
    ]


_HTML = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TestZede raporu: {{ meta.dataset }}</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 24px; color: #1d1d1f; background: #fff; }
  h1 { font-size: 1.4rem; } h2 { font-size: 1.1rem; margin-top: 2rem; }
  table { border-collapse: collapse; font-size: 0.85rem; }
  th, td { border: 1px solid #d0d0d5; padding: 4px 8px; text-align: right; }
  th { background: #f2f2f5; } td:first-child, th:first-child { text-align: left; }
  .wrap { overflow-x: auto; }
  .error { color: #b3261e; }
</style>
</head>
<body>
<h1>TestZede raporu: {{ meta.dataset }}</h1>
<table>
{% for key, value in meta_rows %}<tr><th>{{ key }}</th><td>{{ value }}</td></tr>
{% endfor %}</table>
<h2>Özet</h2>
<div class="wrap">{{ summary_html }}</div>
<h2>Birim sonuçları ({{ unit_count }})</h2>
<div class="wrap">{{ results_html }}</div>
</body>
</html>
"""


def _html(frame: pd.DataFrame, summary: pd.DataFrame, meta: ReportMeta) -> str:
    def table(df: pd.DataFrame) -> str:
        # to_html değerleri kendisi kaçışlar (escape=True); şablonda tekrar kaçışlanmaz.
        return df.to_html(index=False, na_rep="-", float_format=lambda v: f"{v:.3f}", border=0)

    template = Environment(autoescape=True).from_string(_HTML)
    return template.render(
        meta=meta,
        meta_rows=_meta_rows(meta),
        summary_html=Markup(table(summary)),
        results_html=Markup(table(frame)),
        unit_count=len(frame),
    )


def write_report(
    results: Sequence[UnitResult],
    out_dir: Path,
    meta: ReportMeta,
    formats: Iterable[str] = FORMATS,
) -> list[Path]:
    """Raporu ``out_dir`` altına yazar ve oluşturulan dosyaların yollarını döner.

    Raises:
        ValueError: Bilinmeyen bir biçim istenirse.
        OSError: Dosya yazılamazsa (çağıran katman kullanıcıya mesaj olarak gösterir).
    """
    formats = tuple(dict.fromkeys(formats))
    unknown = set(formats) - set(FORMATS)
    if unknown:
        raise ValueError(f"Bilinmeyen rapor biçimi: {', '.join(sorted(unknown))}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frame = to_frame(results)
    summary = summarize(frame)
    meta_frame = pd.DataFrame(_meta_rows(meta), columns=["alan", "değer"])
    written: list[Path] = []

    if "csv" in formats:
        # utf-8-sig: Excel Türkçe karakterleri Windows'ta doğru açsın.
        for name, df in (("results", frame), ("summary", summary), ("meta", meta_frame)):
            path = out_dir / f"{name}.csv"
            df.to_csv(path, index=False, encoding="utf-8-sig")
            written.append(path)
    if "xlsx" in formats:
        path = out_dir / "report.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            summary.to_excel(writer, sheet_name="Özet", index=False)
            frame.to_excel(writer, sheet_name="Sonuçlar", index=False)
            meta_frame.to_excel(writer, sheet_name="Bilgi", index=False)
        written.append(path)
    if "html" in formats:
        path = out_dir / "report.html"
        path.write_text(_html(frame, summary, meta), encoding="utf-8")
        written.append(path)
    return written
