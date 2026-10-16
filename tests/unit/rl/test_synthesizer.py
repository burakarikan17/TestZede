import pytest
from conftest import FakeCall

from testzede.rl.synthesizer import format_call, output_class, synthesize


def _body(test):
    return test.code.split("():\n", 1)[1]


def test_ok_value_becomes_equality_assert():
    test = synthesize("f", (1, [2, 3]), FakeCall("ok", "5"), step=7)
    assert test.name == "test_step_007"
    assert test.origin == "rl"
    assert "from target import f" in test.code
    assert _body(test) == "    assert f(1, [2, 3]) == 5\n"


@pytest.mark.parametrize(
    ("value_repr", "expected"),
    [
        ("None", "    assert f(0) is None\n"),
        ("True", "    assert f(0) is True\n"),
        ("0.30000000000000004", "    assert f(0) == pytest.approx(0.30000000000000004)\n"),
        ("<object at 0x1>", "    f(0)\n"),
        ("nan", "    f(0)\n"),
        ("{'a': [1]}", "    assert f(0) == {'a': [1]}\n"),
    ],
)
def test_assertion_forms(value_repr, expected):
    assert _body(synthesize("f", (0,), FakeCall("ok", value_repr), step=1)) == expected


def test_builtin_exception_becomes_pytest_raises():
    test = synthesize("f", ("",), FakeCall("raised", exc_type="ValueError"), step=1)
    assert _body(test) == "    with pytest.raises(ValueError):\n        f('')\n"


def test_custom_exception_falls_back_to_exception():
    test = synthesize("f", (1,), FakeCall("raised", exc_type="target.MyError"), step=1)
    assert "pytest.raises(Exception)" in test.code


@pytest.mark.parametrize("status", ["timeout", "error"])
def test_invalid_outcomes_produce_no_test(status):
    assert synthesize("f", (1,), FakeCall(status), step=1) is None


def test_generated_code_runs_against_reference(sign_unit, sign_executor):
    tests = [
        synthesize("sign", args, sign_executor.call_function(sign_unit, repr(args)), step=i)
        for i, args in enumerate([(3,), (-2,), (0,)])
    ]
    result = sign_executor.run_tests(sign_unit, tests)
    assert set(result.test_outcomes.values()) == {"passed"}
    assert result.covered_branches == sign_executor.all_branches


def test_format_call_round_trips_special_values():
    assert format_call("g", (set(), "a'b", -0.0)) == 'g(set(), "a\'b", -0.0)'


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (FakeCall("ok", "-3"), "ok:int:-"),
        (FakeCall("ok", "0"), "ok:int:0"),
        (FakeCall("ok", "[]"), "ok:list:empty"),
        (FakeCall("ok", "False"), "ok:bool:False"),
        (FakeCall("ok", "<obj>"), "ok:object"),
        (FakeCall("raised", exc_type="pkg.KeyError"), "raised:KeyError"),
        (FakeCall("timeout"), "timeout"),
    ],
)
def test_output_class(call, expected):
    assert output_class(call) == expected
