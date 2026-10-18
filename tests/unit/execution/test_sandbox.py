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


def test_entry_point_none_is_error():
    r = call_function(_unit("def f(): return 1", entry=None), "()")
    assert (r.status, r.value_repr, r.exc_type) == ("error", None, None)


def test_valid_literal_that_is_not_a_tuple_is_error():
    assert call_function(_unit("def f(a): return a"), "5").status == "error"
    assert call_function(_unit("def f(a): return a"), "[1, 2]").status == "error"


def test_function_raising_custom_exception_reports_type():
    src = "class MyErr(Exception):\n    pass\ndef f():\n    raise MyErr('x')"
    r = call_function(_unit(src), "()")
    assert (r.status, r.exc_type) == ("raised", "MyErr")


def test_sys_exit_in_target_is_raised_not_crash():
    r = call_function(_unit("import sys\ndef f():\n    sys.exit(2)"), "()")
    assert (r.status, r.exc_type) == ("raised", "SystemExit")


def test_infinite_loop_times_out_quickly():
    r = call_function(_unit("def f():\n    while True:\n        pass"), "()", timeout=0.5)
    assert r.status == "timeout"
    assert r.duration_s < 5


def test_oversized_output_gives_none_value_repr():
    r = call_function(_unit("def f():\n    return [0] * 100000"), "()")
    assert (r.status, r.value_repr) == ("ok", None)


def test_value_repr_at_limit_is_kept():
    r = call_function(_unit("def f():\n    return 'a' * 100"), "()")
    assert r.status == "ok"
    assert r.value_repr == repr("a" * 100)


def test_module_level_exception_in_target_is_error():
    r = call_function(_unit("raise RuntimeError('x')\ndef f(): pass"), "()")
    assert r.status == "error"


def test_generator_function_is_consumed_up_to_the_limit():
    from testzede.execution.sandbox import GENERATOR_LIMIT
    from testzede.rl.executor import GENERATOR_LIMIT as RL_LIMIT

    assert GENERATOR_LIMIT == RL_LIMIT
    r = call_function(
        _unit("import itertools\ndef f(n):\n    yield from itertools.count(n)"), "(0,)"
    )
    assert r.status == "ok"
    assert r.value_repr == repr(list(range(GENERATOR_LIMIT)))


def test_exception_inside_generator_is_raised():
    r = call_function(_unit("def f(n):\n    yield 1\n    raise ValueError(n)"), "(0,)")
    assert (r.status, r.exc_type) == ("raised", "ValueError")


def test_returned_generator_object_is_not_consumed():
    r = call_function(_unit("def f(n):\n    return (i for i in range(n))"), "(2,)")
    assert r.status == "ok" and r.value_repr.startswith("<generator")
