"""White-box testler: ``_coverage_json`` ve ``_build_result`` (+ ``_arcs``) karar noktaları.

``_coverage_json(tmp_dir)``
- ``if not out.exists(): return None`` -> BRANCH coverage: coverage.json üretilmediğinde
  ``None`` (gerçek ``coverage json`` çağrısı, veri dosyası olmayan dizinde) ve üretildiğinde
  devam yolu (alt süreç mock'lanıp JSON elle yazılır).
- ``files.get("target.py")``           -> BRANCH coverage: hedef dosya JSON'da var / yok.

``_build_result(data, names, generated, compiled, elapsed)``
- ``data or {}``                        -> BRANCH coverage: ``None`` (boş sözlüğe düşer) ve dolu.
- ``if func`` (comprehension filtresi)  -> BRANCH coverage: ``""`` (modül düzeyi) anahtarı elenir,
  adlı fonksiyon tutulur.
- ``d.get(..., ())`` varsayılanları     -> PATH coverage: anahtarlar tamamen eksik, kısmen eksik
  ve tam dolu olmak üzere üç yol.
- ``_arcs``                             -> STATEMENT coverage: ``[a, b]`` listeleri ``(a, b)``
  tuple'larına çevrilir (negatif çıkış arc'ları dahil).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from testzede.execution import coverage_runner
from testzede.execution.coverage_runner import _arcs, _build_result, _coverage_json


def _fake_json_run(payload: dict | None):
    def fake_run(cmd, **_kwargs):
        if payload is not None:
            out = Path(cmd[cmd.index("-o") + 1])
            out.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    return fake_run


def test_coverage_json_returns_none_when_no_data_file(tmp_path):
    assert _coverage_json(tmp_path) is None  # gerçek coverage: .coverage yok -> çıktı yok


def test_coverage_json_returns_target_entry(tmp_path, monkeypatch):
    payload = {"files": {"target.py": {"executed_lines": [1]}, "other.py": {}}}
    monkeypatch.setattr(coverage_runner.subprocess, "run", _fake_json_run(payload))
    assert _coverage_json(tmp_path) == {"executed_lines": [1]}


def test_coverage_json_returns_none_when_target_not_in_files(tmp_path, monkeypatch):
    monkeypatch.setattr(
        coverage_runner.subprocess, "run", _fake_json_run({"files": {"other.py": {}}})
    )
    assert _coverage_json(tmp_path) is None


def test_coverage_json_without_files_key(tmp_path, monkeypatch):
    monkeypatch.setattr(coverage_runner.subprocess, "run", _fake_json_run({}))
    assert _coverage_json(tmp_path) is None


def test_arcs_converts_lists_to_int_tuples():
    assert _arcs([[1, 2], [3, -4]]) == frozenset({(1, 2), (3, -4)})
    assert _arcs([]) == frozenset()


def test_build_result_with_none_data_gives_empty_report():
    r = _build_result(None, {"a": "error"}, generated=3, compiled=1, elapsed=0.5)
    assert r.coverage.covered_lines == 0
    assert r.coverage.total_lines == 0
    assert r.coverage.total_branches == 0
    assert r.coverage.per_function == {}
    assert r.coverage.line_rate == 0.0
    assert r.covered_lines == frozenset() and r.all_branches == frozenset()
    assert r.test_outcomes == {"a": "error"}
    assert (r.stats.generated, r.stats.compiled, r.stats.execution_time_s) == (3, 1, 0.5)
    assert r.stats.compilation_rate == 1 / 3


def test_build_result_with_empty_dict_behaves_like_none():
    assert _build_result({}, {}, 0, 0, 0.0).coverage.total_lines == 0


def test_build_result_with_partial_data_uses_defaults():
    r = _build_result({"executed_lines": [1, 2]}, {}, 1, 1, 0.1)
    assert r.covered_lines == {1, 2}
    assert r.all_lines == {1, 2}  # missing_lines varsayılanı ()
    assert r.all_branches == frozenset()
    assert r.coverage.per_function == {}


def test_build_result_full_data_filters_module_level_function():
    data = {
        "executed_lines": [1, 2, 3],
        "missing_lines": [4],
        "executed_branches": [[2, 3]],
        "missing_branches": [[2, 4]],
        "functions": {
            "": {"summary": {"percent_covered": 50.0}},
            "f": {"summary": {"percent_covered": 75.0}},
        },
    }
    r = _build_result(data, {"a": "passed"}, 1, 1, 0.2)
    assert r.covered_lines == {1, 2, 3}
    assert r.all_lines == {1, 2, 3, 4}
    assert r.covered_branches == {(2, 3)}
    assert r.all_branches == {(2, 3), (2, 4)}
    assert r.coverage.per_function == {"f": 0.75}  # "" elenir, yüzde 0-1'e çevrilir
    assert r.coverage.line_rate == 0.75
