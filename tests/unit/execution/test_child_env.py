"""Alt süreç ortamı: COVERAGE_* ve COV_CORE_* üst sürecin coverage verisine sızmamalı."""

from __future__ import annotations

import os
import subprocess

import pytest

from testzede.domain.models import CodeUnit, TestCase
from testzede.execution import coverage_runner, sandbox
from testzede.execution.coverage_runner import _pytest_env, run_outcomes, run_tests
from testzede.execution.sandbox import call_function, child_env

SOURCE = "def f(a):\n    if a > 0:\n        return 1\n    return 2\n"
PASS = TestCase("t", "def test_t():\n    assert f(1) == 1", "rl")
SENTINEL = b"ust-surecin-coverage-verisi"
LEAKING = {
    "COVERAGE_FILE": "x.cov",
    "COVERAGE_PROCESS_START": "x.rc",
    "COVERAGE_RCFILE": "x.rc",
    "COV_CORE_SOURCE": "src",
    "COV_CORE_DATAFILE": "x.cov",
    "COV_CORE_CONFIG": "x.rc",
}


def _unit() -> CodeUnit:
    return CodeUnit(uid="t/0", source=SOURCE, entry_point="f", dataset=None)


@pytest.fixture
def parent_cov(tmp_path, monkeypatch):
    """Üst sürecin coverage verisini taklit eden dosya; COVERAGE_* değişkenleri ayarlı."""
    path = tmp_path / "parent.cov"
    path.write_bytes(SENTINEL)
    monkeypatch.setenv("COVERAGE_FILE", str(path))
    monkeypatch.setenv("COVERAGE_PROCESS_START", str(tmp_path / "rc"))
    monkeypatch.setenv("COV_CORE_SOURCE", "src")
    monkeypatch.setenv("COV_CORE_DATAFILE", str(path))
    return path


# --- saf birim testleri ------------------------------------------------------------------------


def test_child_env_drops_coverage_prefixes_and_keeps_everything_else(monkeypatch):
    for name, value in LEAKING.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("MY_VAR", "1")
    monkeypatch.setenv("MY_COVERAGE_FILE", "kalmalı")  # önek değil, içerir
    monkeypatch.setenv("COVERAGE", "kalmalı")  # alt çizgisiz: önek değil
    monkeypatch.setenv("COV_COREX", "kalmalı")
    env = child_env()
    assert not any(k.upper().startswith(("COVERAGE_", "COV_CORE_")) for k in env)
    assert env["MY_VAR"] == "1"
    assert env["MY_COVERAGE_FILE"] == env["COVERAGE"] == env["COV_COREX"] == "kalmalı"
    kept = {k for k in os.environ if not k.upper().startswith(("COVERAGE_", "COV_CORE_"))}
    assert set(env) == kept


def test_child_env_is_case_insensitive_for_prefixes(monkeypatch):
    monkeypatch.setenv("coverage_file", "x")
    monkeypatch.setenv("Cov_Core_Source", "x")
    assert not any(k.lower().startswith(("coverage_", "cov_core_")) for k in child_env())


def test_child_env_does_not_modify_os_environ(monkeypatch):
    monkeypatch.setenv("COVERAGE_FILE", "x.cov")
    child_env()
    assert os.environ["COVERAGE_FILE"] == "x.cov"


def test_pytest_env_keeps_plugin_autoload_flag_and_drops_coverage_vars(monkeypatch):
    for name, value in LEAKING.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("MY_VAR", "1")
    env = _pytest_env()
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert env["MY_VAR"] == "1"
    assert not set(LEAKING) & set(env)


# --- tüm alt süreç çağrıları temiz ortamla gider -----------------------------------------------


class _Recorder:
    def __init__(self) -> None:
        self.envs: list[dict[str, str]] = []
        self.cmds: list[list[str]] = []

    def __call__(self, cmd, **kwargs):
        self.cmds.append(cmd)
        self.envs.append(kwargs.get("env"))
        return subprocess.CompletedProcess(cmd, 0)


def test_run_tests_passes_clean_env_to_pytest_and_coverage_json(monkeypatch, parent_cov):
    rec = _Recorder()
    monkeypatch.setattr(coverage_runner.subprocess, "run", rec)
    run_tests(_unit(), [PASS])
    assert len(rec.cmds) == 2  # coverage run + coverage json
    for env in rec.envs:
        assert env is not None and not set(LEAKING) & set(env)
    assert rec.envs[0]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"


def test_run_outcomes_passes_clean_env(monkeypatch, parent_cov):
    rec = _Recorder()
    monkeypatch.setattr(coverage_runner.subprocess, "run", rec)
    run_outcomes(_unit(), [PASS])
    assert len(rec.envs) == 1
    assert not set(LEAKING) & set(rec.envs[0])
    assert rec.envs[0]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"


def test_call_function_passes_clean_env(monkeypatch, parent_cov):
    rec = _Recorder()
    monkeypatch.setattr(sandbox.subprocess, "run", rec)
    call_function(_unit(), "(1,)")
    assert len(rec.envs) == 1
    assert rec.envs[0] is not None and not set(LEAKING) & set(rec.envs[0])


# --- gerçek alt süreçler: üst sürecin verisi bozulmaz, sonuç doğru ------------------------------


def test_real_run_tests_ignores_parent_coverage_environment(parent_cov):
    result = run_tests(_unit(), [PASS])
    assert result.test_outcomes == {"t": "passed"}
    assert result.covered_lines == {1, 2, 3}
    assert result.all_lines == {1, 2, 3, 4}
    assert result.covered_branches == {(2, 3)}
    assert parent_cov.read_bytes() == SENTINEL  # iç `coverage run` bu dosyaya yazmadı


def test_real_run_outcomes_ignores_parent_coverage_environment(parent_cov):
    tests = [PASS, TestCase("bad", "def test_bad():\n    assert f(1) == 99", "rl")]
    assert run_outcomes(_unit(), tests) == {"t": "passed", "bad": "failed"}
    assert parent_cov.read_bytes() == SENTINEL


def test_real_call_function_ignores_parent_coverage_environment(parent_cov):
    result = call_function(_unit(), "(1,)")
    assert (result.status, result.value_repr) == ("ok", "1")
    assert parent_cov.read_bytes() == SENTINEL
