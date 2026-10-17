"""``run_outcomes`` (coverage'sız hızlı yol) ve alt süreç ortamı testleri."""

from __future__ import annotations

import os
import subprocess

from testzede.domain.models import CodeUnit, TestCase
from testzede.execution import coverage_runner
from testzede.execution.coverage_runner import run_outcomes, run_tests

SOURCE = "def f(a):\n    if a > 0:\n        return 1\n    return 2\n"
PASS = "def test_x():\n    assert f(1) == 1"
FAIL = "def test_x():\n    assert f(1) == 99"


def _unit(source: str = SOURCE) -> CodeUnit:
    return CodeUnit(uid="t/0", source=source, entry_point="f", dataset=None)


def _t(name: str, code: str) -> TestCase:
    return TestCase(name=name, code=code, origin="rl")


SCENARIOS = {
    "passing": [_t("a", PASS), _t("b", "def test_b():\n    assert f(-1) == 2")],
    "failing": [_t("a", PASS), _t("bad", FAIL)],
    "syntax_error": [_t("a", PASS), _t("syn", "def test_syn(:\n    pass")],
    "import_error": [_t("imp", "import no_such_module\ndef test_i():\n    pass"), _t("a", PASS)],
    "all_syntax_errors": [_t("a", "def test_a(:"), _t("b", "x = = 1")],
    "duplicate_names": [_t("x", PASS), _t("x", FAIL), _t("y", PASS), _t("y", "def test_y(:")],
    "no_test_function": [_t("none", "VALUE = 1")],
    "exception_in_test": [_t("boom", "def test_boom():\n    raise RuntimeError('x')")],
}

# Her senaryonun beklenen sonucu: iki fonksiyon da yanlış ama aynı sonuç vermesin diye.
EXPECTED = {
    "passing": {"a": "passed", "b": "passed"},
    "failing": {"a": "passed", "bad": "failed"},
    "syntax_error": {"a": "passed", "syn": "error"},
    "import_error": {"imp": "error", "a": "passed"},
    "all_syntax_errors": {"a": "error", "b": "error"},
    "duplicate_names": {"x": "failed", "y": "error"},
    "no_test_function": {"none": "error"},
    "exception_in_test": {"boom": "failed"},
}


def test_run_outcomes_matches_run_tests_over_all_scenarios():
    """Tüm senaryolar tek listede (adlar ``senaryo:ad``); her fonksiyon yalnızca bir kez koşar."""
    tests = [
        _t(f"{scenario}:{t.name}", t.code) for scenario, items in SCENARIOS.items() for t in items
    ]
    fast = run_outcomes(_unit(), tests)
    assert fast == run_tests(_unit(), tests).test_outcomes
    for scenario, expected in EXPECTED.items():
        assert {
            name.split(":", 1)[1]: outcome
            for name, outcome in fast.items()
            if name.startswith(f"{scenario}:")
        } == expected


def test_run_outcomes_empty_list_matches_run_tests():
    assert run_outcomes(_unit(), []) == {} == run_tests(_unit(), []).test_outcomes


def test_run_outcomes_timeout_matches_run_tests():
    loop = [_t("loop", "def test_loop():\n    while True:\n        pass")]
    assert run_outcomes(_unit(), loop, timeout=1.0) == {"loop": "timeout"}
    assert run_tests(_unit(), loop, timeout=1.0).test_outcomes == {"loop": "timeout"}


def test_run_outcomes_broken_source_is_error_not_raise():
    tests = [_t("a", "def test_a():\n    pass")]
    assert run_outcomes(_unit("def f(:"), tests) == {"a": "error"}


def test_run_outcomes_internal_failure_never_raises(monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("disk")

    monkeypatch.setattr(coverage_runner, "_run", boom)
    assert run_outcomes(_unit(), [_t("a", PASS)]) == {"a": "error"}


class _Recorder:
    """``subprocess.run`` yerine geçer; komutları ve anahtar argümanları kaydeder."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0)


def test_run_outcomes_makes_single_plain_pytest_call(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(coverage_runner.subprocess, "run", rec)
    run_outcomes(_unit(), [_t("a", PASS)])
    assert len(rec.calls) == 1  # coverage json adımı yok
    cmd, kwargs = rec.calls[0]
    assert "coverage" not in cmd
    assert cmd[1:5] == ["-I", "-m", "pytest", "-q"]
    assert "-x" not in cmd
    assert kwargs["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert kwargs["timeout"] == 10.0
    assert not kwargs.get("shell")


def test_run_tests_pytest_subprocess_disables_plugin_autoload(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(coverage_runner.subprocess, "run", rec)
    run_tests(_unit(), [_t("a", PASS)])
    cmd, kwargs = rec.calls[0]
    assert "coverage" in cmd and "--branch" in cmd
    assert kwargs["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert not kwargs.get("shell")
    assert kwargs["timeout"] == 10.0


def test_env_is_a_copy_and_os_environ_is_untouched(monkeypatch):
    monkeypatch.delenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", raising=False)
    monkeypatch.setenv("TESTZEDE_MARKER", "1")
    env = coverage_runner._pytest_env()
    assert env["TESTZEDE_MARKER"] == "1"
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" not in os.environ
