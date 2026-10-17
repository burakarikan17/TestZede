"""White-box testler: ``coverage_runner._run`` karar noktaları.

Hedef: ``_run(unit, tests, timeout)``. Testler kaynak okunarak, her kararın iki yönü
(true/false) çalıştırılacak şekilde tasarlandı. Alt süreç ``subprocess.run`` mock'lanarak
taklit edilir; böylece dallar hızlı ve deterministik tetiklenir.

Karar noktaları ve neden:
- ``try: ast.parse`` / ``except SyntaxError``  -> BRANCH coverage: hem geçerli kod (else,
  ``runnable``'a eklenir) hem de bozuk kod (``outcomes[i] = "error"``) dalı gerekir.
- ``if not runnable``                          -> BRANCH coverage: hiç çalıştırılabilir test
  kalmadığında alt süreç başlatmadan erken dönüş (true) ve devam (false).
- ``if unit.entry_point``                      -> BRANCH coverage: başlıktaki ``from target
  import <fn>`` satırı yalnızca entry_point varsa eklenir.
- ``except subprocess.TimeoutExpired``         -> STATEMENT + BRANCH coverage: zaman aşımında
  tüm çalıştırılabilir testler "timeout" olur ve ``None`` coverage verisi döner.
- ``reported.get(i, "error")``                 -> PATH coverage: junit raporu üretilmediğinde
  (süreç çöktü) rapor edilmeyen her test "error" olur; raporlandığında gerçek sonuç kullanılır.
- ``for i in runnable`` döngüsü                -> LOOP coverage: 0, 1 ve çok sayıda öğe.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from testzede.domain.models import CodeUnit, TestCase
from testzede.execution import coverage_runner
from testzede.execution.coverage_runner import _run

SOURCE = "def f(a):\n    if a > 0:\n        return 1\n    return 2\n"
GOOD = "def test_ok():\n    assert f(1) == 1"
BAD_SYNTAX = "def test_bad(:\n    pass"


def _unit(entry: str | None = "f") -> CodeUnit:
    return CodeUnit(uid="wb/0", source=SOURCE, entry_point=entry, dataset=None)


def _t(name: str, code: str) -> TestCase:
    return TestCase(name=name, code=code, origin="rl")


class _FakeRun:
    """``subprocess.run`` yerine geçer; çağrıları kaydeder, istenirse istisna fırlatır."""

    def __init__(self, raises: BaseException | None = None) -> None:
        self.calls: list[list[str]] = []
        self.raises = raises

    def __call__(self, cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(cmd)
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(cmd, 0)


def test_syntax_error_branch_marks_error_and_valid_code_is_runnable(monkeypatch):
    fake = _FakeRun()
    monkeypatch.setattr(coverage_runner.subprocess, "run", fake)
    outcomes, _ = _run(_unit(), [_t("good", GOOD), _t("bad", BAD_SYNTAX)], timeout=5)
    assert outcomes[1] == "error"  # except SyntaxError dalı
    assert outcomes[0] == "error"  # else dalı: çalıştı ama rapor yok -> reported.get varsayılanı
    assert fake.calls, "geçerli test olduğu için alt süreç başlatılmalı"


def test_no_runnable_tests_returns_early_without_subprocess(monkeypatch):
    fake = _FakeRun()
    monkeypatch.setattr(coverage_runner.subprocess, "run", fake)
    outcomes, data = _run(_unit(), [_t("a", BAD_SYNTAX), _t("b", "x = = 1")], timeout=5)
    assert outcomes == {0: "error", 1: "error"}
    assert data is None
    assert fake.calls == []  # erken dönüş: alt süreç hiç çağrılmadı


def test_empty_test_list_returns_early(monkeypatch):
    fake = _FakeRun()
    monkeypatch.setattr(coverage_runner.subprocess, "run", fake)
    assert _run(_unit(), [], timeout=5) == ({}, None)
    assert fake.calls == []


def test_timeout_branch_marks_every_runnable_test_timeout(monkeypatch):
    fake = _FakeRun(raises=subprocess.TimeoutExpired(cmd="x", timeout=1))
    monkeypatch.setattr(coverage_runner.subprocess, "run", fake)
    outcomes, data = _run(_unit(), [_t("a", GOOD), _t("s", BAD_SYNTAX), _t("b", GOOD)], timeout=1)
    assert outcomes == {0: "timeout", 1: "error", 2: "timeout"}
    assert data is None
    assert len(fake.calls) == 1  # timeout sonrası coverage json adımına geçilmez


def test_missing_junit_report_defaults_every_test_to_error(monkeypatch):
    fake = _FakeRun()  # alt süreç "başarılı" döner ama report.xml yazmaz
    monkeypatch.setattr(coverage_runner.subprocess, "run", fake)
    outcomes, data = _run(_unit(), [_t("a", GOOD), _t("b", GOOD)], timeout=5)
    assert outcomes == {0: "error", 1: "error"}
    assert data is None  # coverage.json da yok
    assert len(fake.calls) == 2  # pytest çağrısı + coverage json çağrısı


@pytest.mark.parametrize("entry", ["f", None])
def test_entry_point_branch_controls_import_header(monkeypatch, entry):
    written: dict[str, str] = {}

    def fake_run(cmd, cwd, **_kwargs):
        written["test"] = (Path(cwd) / "test_0000.py").read_text(encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(coverage_runner.subprocess, "run", fake_run)
    _run(_unit(entry), [_t("a", "def test_a():\n    pass")], timeout=5)
    has_named_import = "from target import f\n" in written["test"]
    assert has_named_import is (entry is not None)
    assert "from target import *" in written["test"]


def test_real_subprocess_full_path_reports_real_outcomes():
    """Mock'suz uçtan uca yol: junit raporlandığında gerçek sonuçlar kullanılır."""
    outcomes, data = _run(
        _unit(),
        [_t("ok", GOOD), _t("bad", "def test_bad():\n    assert f(1) == 99")],
        timeout=30,
    )
    assert outcomes == {0: "passed", 1: "failed"}
    assert data is not None
