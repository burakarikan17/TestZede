from testzede.domain.models import CodeUnit
from testzede.execution.sandbox import call_function


def _unit(source: str, entry: str | None = "f") -> CodeUnit:
    return CodeUnit(uid="t/0", source=source, entry_point=entry, dataset=None)


def test_ok_returns_repr_even_if_target_prints():
    r = call_function(_unit("def f(a, b):\n    print('x')\n    return a + b"), "(1, 2)")
    assert (r.status, r.value_repr) == ("ok", "3")


def test_raised_reports_exception_type():
    r = call_function(_unit("def f(a):\n    return 1 / a"), "(0,)")
    assert (r.status, r.exc_type) == ("raised", "ZeroDivisionError")


def test_timeout():
    r = call_function(_unit("def f():\n    while True:\n        pass"), "()", timeout=1.0)
    assert r.status == "timeout"


def test_process_crash_is_error():
    r = call_function(_unit("import os\ndef f():\n    os._exit(3)"), "()")
    assert r.status == "error"


def test_syntax_error_in_source_is_error():
    assert call_function(_unit("def f(:"), "()").status == "error"


def test_bad_args_or_missing_entry_is_error():
    assert call_function(_unit("def f(a): return a"), "not a tuple").status == "error"
    assert call_function(_unit("def f(a): return a", entry=None), "(1,)").status == "error"
    assert call_function(_unit("def g(): pass"), "()").status == "error"


def test_huge_int_repr_error_is_ok_without_value():
    r = call_function(_unit("def f():\n    return 10 ** 5000"), "()")
    assert (r.status, r.value_repr) == ("ok", None)


def test_oversized_repr_is_dropped_not_truncated():
    r = call_function(_unit("def f():\n    return 'a' * 20000"), "()")
    assert (r.status, r.value_repr) == ("ok", None)
