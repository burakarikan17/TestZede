import pytest

from testzede.domain.models import CodeUnit
from testzede.rl.signature import (
    ANY,
    SignatureError,
    TypeSpec,
    extract_params,
    is_generator,
    parse_seed_inputs,
)

HUMANEVAL_0 = '''\
from typing import List


def has_close_elements(numbers: List[float], threshold: float) -> bool:
    """
    >>> has_close_elements([1.0, 2.0, 3.0], 0.5)
    False
    """
    return False
'''


def _unit(source: str, entry: str = "f", examples: tuple[str, ...] = ()) -> CodeUnit:
    return CodeUnit(uid="t/0", source=source, entry_point=entry, seed_examples=examples)


def test_types_from_typing_annotations():
    params = extract_params(_unit(HUMANEVAL_0, "has_close_elements"))
    assert [p.name for p in params] == ["numbers", "threshold"]
    assert params[0].type == TypeSpec("list", (TypeSpec("float"),))
    assert params[1].type == TypeSpec("float")


def test_builtin_generic_and_dict_annotations():
    params = extract_params(_unit("def f(a: dict[str, int], b: tuple[int, ...]): ..."))
    assert params[0].type == TypeSpec("dict", (TypeSpec("str"), TypeSpec("int")))
    assert params[1].type == TypeSpec("tuple", (TypeSpec("int"),))


def test_type_from_default_value():
    params = extract_params(_unit("def f(a, b=3, c='x'): ..."))
    assert [p.type.kind for p in params] == ["any", "int", "str"]


def test_type_from_docstring_examples_when_no_annotation():
    unit = _unit("def f(s, n): ...", examples=(">>> f('abc', [1, 2])",))
    params = extract_params(unit)
    assert params[0].type == TypeSpec("str")
    assert params[1].type == TypeSpec("list", (TypeSpec("int"),))


def test_method_skips_self():
    params = extract_params(_unit("class A:\n    def f(self, x: int): ..."))
    assert [p.name for p in params] == ["x"]


def test_unknown_annotation_is_any():
    assert extract_params(_unit("def f(x: MyClass): ..."))[0].type == ANY


def test_missing_entry_point_raises():
    with pytest.raises(SignatureError):
        extract_params(_unit("def g(): ...", "f"))


def test_invalid_syntax_raises():
    with pytest.raises(SignatureError):
        extract_params(_unit("def f(:"))


def test_parse_seed_inputs_skips_non_literal_and_other_calls():
    unit = _unit(
        "def f(x): ...",
        examples=(">>> f([1, 2], 'a')", ">>> f(x)", ">>> g(1)", ">>> f(1)\n", "garbage("),
    )
    assert parse_seed_inputs(unit) == (([1, 2], "a"), (1,))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def g(n):\n    for i in range(n):\n        yield i\n", True),
        ("def g(xs):\n    yield from xs\n", True),
        ("def g(n):\n    return (i for i in range(n))\n", False),
        ("def g(n):\n    def inner():\n        yield n\n    return inner\n", False),
        ("def g(n):\n    return n\n", False),
        ("def g(:\n", False),
    ],
)
def test_is_generator(source, expected):
    assert is_generator(CodeUnit("t/0", source, entry_point="g")) is expected


def test_parse_seed_inputs_unwraps_consumers():
    unit = CodeUnit(
        "t/0",
        "def g(xs, d=1):\n    yield xs\n",
        entry_point="g",
        seed_examples=(
            ">>> list(g([1, 2, 3]))",
            ">>> sorted(g([3], -1))",
            ">>> len(g([1]))",
            ">>> list(other([1]))",
        ),
    )
    assert parse_seed_inputs(unit) == (([1, 2, 3],), ([3], -1))
