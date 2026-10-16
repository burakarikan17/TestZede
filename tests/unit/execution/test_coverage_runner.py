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


def test_failed_and_syntax_error_do_not_break_other_tests():
    r = run_tests(
        _unit(),
        [
            _t("ok", "def test_ok():\n    assert f(-1) == 2"),
            _t("bad", "def test_bad():\n    assert f(1) == 99"),
            _t("syn", "def test_syn(:\n    pass"),
        ],
    )
    assert r.test_outcomes == {"ok": "passed", "bad": "failed", "syn": "error"}
    assert r.stats.compilation_rate == 2 / 3
    assert r.covered_branches == {(2, 3), (2, 4)}


def test_import_error_in_test_is_error_not_crash():
    r = run_tests(
        _unit(),
        [
            _t("imp", "import no_such_module\ndef test_imp():\n    pass"),
            _t("ok", "def test_ok():\n    f(1)"),
        ],
    )
    assert r.test_outcomes == {"imp": "error", "ok": "passed"}


def test_timeout_marks_tests_timeout():
    loop = _t("loop", "def test_loop():\n    while True:\n        pass")
    r = run_tests(_unit(), [loop], timeout=2.0)
    assert r.test_outcomes == {"loop": "timeout"}
    assert r.covered_lines == frozenset()


def test_broken_source_and_empty_suite_never_raise():
    r = run_tests(_unit("def f(:"), [_t("a", "def test_a():\n    pass")])
    assert r.test_outcomes == {"a": "error"}
    assert run_tests(_unit(), []).test_outcomes == {}
