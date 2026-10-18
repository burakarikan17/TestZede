from testzede.domain.models import CodeUnit, TestCase
from testzede.execution.coverage_runner import run_tests

SOURCE = "def f(a):\n    if a > 0:\n        return 1\n    return 2\n"


def _unit(source: str = SOURCE) -> CodeUnit:
    return CodeUnit(uid="t/0", source=source, entry_point="f", dataset=None)


def _t(name: str, code: str) -> TestCase:
    return TestCase(name=name, code=code, origin="rl")


def test_single_test_reports_line_and_branch_sets():
    r = run_tests(_unit(), [_t("a", "def test_a():\n    assert f(1) == 1")])
    assert r.test_outcomes == {"a": "passed"}
    assert r.all_lines == {1, 2, 3, 4}
    assert r.covered_lines == {1, 2, 3}
    assert r.all_branches == {(2, 3), (2, 4)}
    assert r.covered_branches == {(2, 3)}
    assert r.coverage.covered_lines == 3
    assert r.coverage.total_branches == 2
    assert 0 < r.coverage.per_function["f"] < 1
    assert r.stats.generated == 1
    assert r.stats.compilation_rate == 1.0


def test_mixed_suite_classifies_every_test_independently():
    """Tek koşuda: geçen, başarısız, syntax/import hatalı, istisna, test yok, aynı isimler."""
    pass_1 = "def test_p():\n    assert f(1) == 1"
    fail_1 = "def test_p():\n    assert f(1) == 99"
    tests = [
        _t("ok", "def test_ok():\n    assert f(-1) == 2"),
        _t("bad", "def test_bad():\n    assert f(1) == 99"),  # başarısız, ama derlendi
        _t("syn", "def test_syn(:\n    pass"),
        _t("imp", "import no_such_module\ndef test_imp():\n    pass"),
        _t("boom", "def test_boom():\n    raise RuntimeError('x')"),
        _t("none", "VALUE = 1"),  # test fonksiyonu yok
        _t("x", pass_1),  # aynı isim: en kötü sonuç kazanır
        _t("x", fail_1),
        _t("y", fail_1),
        _t("y", "def test_y(:"),
        _t("w", fail_1),  # sıra önemli değil
        _t("w", pass_1),
    ]
    r = run_tests(_unit(), tests)
    assert r.test_outcomes == {
        "ok": "passed",
        "bad": "failed",
        "syn": "error",
        "imp": "error",
        "boom": "failed",
        "none": "error",
        "x": "failed",
        "y": "error",
        "w": "failed",
    }
    assert r.stats.generated == 12
    assert r.stats.compiled == 8  # syn, imp, none ve ikinci y derlenmedi
    assert r.stats.compilation_rate == 8 / 12
    assert r.covered_branches == {(2, 3), (2, 4)}  # başarısız testler de kodu çalıştırdı


def test_timeout_marks_every_test_timeout_even_the_fast_ones():
    # Mevcut davranış: zaman aşımında tek tek ayrım yapılmaz, tüm testler "timeout" olur.
    r = run_tests(
        _unit(),
        [
            _t("fast", "def test_fast():\n    assert f(1) == 1"),
            _t("loop", "def test_loop():\n    while True:\n        pass"),
        ],
        timeout=1.0,
    )
    assert r.test_outcomes == {"fast": "timeout", "loop": "timeout"}
    assert r.stats.compiled == 2
    assert r.covered_lines == frozenset()
    assert r.coverage.total_lines == 0
    assert r.stats.execution_time_s < 10


def test_broken_source_collapses_every_test_to_error():
    r = run_tests(
        _unit("def f(:"),
        [_t("a", "def test_a():\n    pass"), _t("b", "def test_b():\n    assert True")],
    )
    assert r.test_outcomes == {"a": "error", "b": "error"}


def test_unit_without_entry_point_still_runs():
    unit = CodeUnit(uid="t/1", source=SOURCE, entry_point=None, dataset=None)
    r = run_tests(unit, [_t("a", "def test_a():\n    assert target.f(1) == 1")])
    assert r.test_outcomes == {"a": "passed"}


def test_all_syntax_errors_skip_subprocess():
    r = run_tests(_unit(), [_t("a", "def test_a(:"), _t("b", "x = = 1")])
    assert r.test_outcomes == {"a": "error", "b": "error"}
    assert r.stats.generated == 2
    assert r.stats.compiled == 0
    assert r.stats.compilation_rate == 0.0
    assert r.coverage.total_lines == 0


def test_empty_suite_has_zero_stats():
    r = run_tests(_unit(), [])
    assert r.test_outcomes == {}
    assert r.stats.generated == 0
    assert r.stats.compilation_rate == 0.0
    assert r.coverage.covered_lines == 0


def test_internal_failure_never_raises(monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("disk")

    monkeypatch.setattr("testzede.execution.coverage_runner._run", boom)
    r = run_tests(_unit(), [_t("a", "def test_a():\n    pass")])
    assert r.test_outcomes == {"a": "error"}
    assert r.stats.compiled == 0
