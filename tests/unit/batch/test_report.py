from datetime import datetime

import pandas as pd
import pytest

from testzede.batch.report import (
    ReportMeta,
    UnitResult,
    file_sha256,
    report_dir,
    summarize,
    to_frame,
    write_report,
)
from testzede.domain.models import CoverageReport, MetricSet, MutationReport, Prediction, RunStats

META = ReportMeta(
    "humaneval", split="external", split_hash="abc123", created_at=datetime(2026, 10, 16, 9, 30)
)


def _results():
    return [
        UnitResult(
            "HumanEval/0",
            "humaneval",
            test_count=4,
            metrics=MetricSet({"LOC": 10.0, "Çevrimsel Karmaşıklık": 3.0}),
            coverage=CoverageReport(8, 10, 3, 4),
            mutation=MutationReport(total=10, killed=7, survived=2, timeout=1),
            stats=RunStats(generated=5, compiled=4, execution_time_s=1.5),
            prediction=Prediction(0.02, 3, "halstead"),
        ),
        UnitResult(
            "HumanEval/1",
            "humaneval",
            test_count=2,
            coverage=CoverageReport(5, 5, 0, 0),
            stats=RunStats(generated=2, compiled=2, execution_time_s=0.5),
        ),
        UnitResult("HumanEval/2", "humaneval", error="Kod ayrıştırılamadı (satır 3): <b>x</b>"),
    ]


def test_frame_has_one_row_per_unit_with_rates():
    frame = to_frame(_results())
    first = frame.iloc[0]
    assert len(frame) == 3
    assert first["line_coverage"] == pytest.approx(0.8)
    assert first["branch_coverage"] == pytest.approx(0.75)
    assert first["mutation_score"] == pytest.approx(0.8)
    assert first["compilation_rate"] == pytest.approx(0.8)
    assert first["Çevrimsel Karmaşıklık"] == 3.0
    assert pd.isna(frame.iloc[1]["branch_coverage"])  # branch'siz kod oranı uydurulmaz
    assert list(frame["status"]) == ["ok", "ok", "error"]


def test_summary_averages_only_available_values():
    summary = summarize(to_frame(_results())).iloc[0]
    assert summary["units"] == 3
    assert summary["failed"] == 1
    assert summary["tests_total"] == 6
    assert summary["line_coverage_mean"] == pytest.approx(0.9)
    assert summary["branch_coverage_mean"] == pytest.approx(0.75)
    assert summary["execution_time_total_s"] == pytest.approx(2.0)


def test_empty_results_do_not_crash(tmp_path):
    assert summarize(to_frame([])).empty
    paths = write_report([], tmp_path, META)
    assert {p.name for p in paths} == {
        "results.csv",
        "summary.csv",
        "meta.csv",
        "report.xlsx",
        "report.html",
    }


def test_write_all_formats(tmp_path):
    paths = write_report(_results(), tmp_path / "out", META)
    assert all(p.exists() for p in paths)

    csv = pd.read_csv(tmp_path / "out" / "results.csv", encoding="utf-8-sig")
    assert "Çevrimsel Karmaşıklık" in csv.columns

    sheets = pd.read_excel(tmp_path / "out" / "report.xlsx", sheet_name=None)
    assert set(sheets) == {"Özet", "Sonuçlar", "Bilgi"}
    assert "abc123" in sheets["Bilgi"]["değer"].tolist()

    html = (tmp_path / "out" / "report.html").read_text(encoding="utf-8")
    assert "abc123" in html and "HumanEval/1" in html
    assert "<b>x</b>" not in html  # hata mesajları kaçışlanır
    assert "&lt;b&gt;x&lt;/b&gt;" in html


def test_selected_formats_and_unknown_format(tmp_path):
    paths = write_report(_results(), tmp_path, META, formats=["html", "html"])
    assert [p.name for p in paths] == ["report.html"]
    with pytest.raises(ValueError, match="pdf"):
        write_report(_results(), tmp_path, META, formats=["pdf"])


def test_report_dir_and_split_hash(tmp_path):
    when = datetime(2026, 10, 16)
    assert report_dir(tmp_path, "testgeneval/lite", when) == tmp_path / "2026-10-16" / (
        "testgeneval_lite"
    )
    split = tmp_path / "split.json"
    split.write_text('["a"]', encoding="utf-8")
    assert len(file_sha256(split)) == 64
