from __future__ import annotations

import pytest

from testzede.mutation.operators import (
    AOR,
    COR,
    OPERATOR_REGISTRY,
    ROR,
    ConstantReplacement,
    Mutant,
    MutationOperator,
    ReturnNone,
    generate_all,
)

ALL_OPERATORS = [AOR(), ROR(), COR(), ConstantReplacement(), ReturnNone()]


def _sources(mutants: list[Mutant]) -> list[str]:
    return [m.source for m in mutants]


# --- AOR ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(("old", "new"), [("+", "-"), ("-", "+"), ("*", "/"), ("/", "*")])
def test_aor_swaps_each_operator(old, new):
    mutants = AOR().generate(f"def f(a, b):\n    return a {old} b")
    assert _sources(mutants) == [f"def f(a, b):\n    return a {new} b"]
    assert (mutants[0].operator, mutants[0].line) == ("AOR", 2)
    assert mutants[0].description == f"{old} -> {new}"


def test_aor_one_mutant_per_site_with_single_change():
    mutants = AOR().generate("def f(a, b, c):\n    x = a + b\n    return x * c")
    assert _sources(mutants) == [
        "def f(a, b, c):\n    x = a - b\n    return x * c",
        "def f(a, b, c):\n    x = a + b\n    return x / c",
    ]
    assert [m.line for m in mutants] == [2, 3]


def test_aor_nested_expression_gives_two_mutants():
    assert len(AOR().generate("x = a + b * c")) == 2


def test_aor_ignores_other_operators():
    assert AOR().generate("x = a // b % c ** d") == []


# --- ROR ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new"),
    [("<", "<="), ("<=", "<"), (">", ">="), (">=", ">"), ("==", "!="), ("!=", "==")],
)
def test_ror_swaps_each_operator(old, new):
    mutants = ROR().generate(f"def f(a, b):\n    return a {old} b")
    assert _sources(mutants) == [f"def f(a, b):\n    return a {new} b"]
    assert (mutants[0].operator, mutants[0].line) == ("ROR", 2)
    assert mutants[0].description == f"{old} -> {new}"


def test_ror_chained_comparison_mutates_each_operator_separately():
    mutants = ROR().generate("ok = a < b <= c")
    assert _sources(mutants) == ["ok = a <= b <= c", "ok = a < b < c"]


def test_ror_ignores_is_in_and_unrelated_code():
    assert ROR().generate("ok = a is b or a in c or a not in c") == []


# --- COR ---------------------------------------------------------------------------------------


def test_cor_and_to_or_and_back():
    assert _sources(COR().generate("ok = a and b")) == ["ok = a or b"]
    assert _sources(COR().generate("ok = a or b")) == ["ok = a and b"]


def test_cor_multi_operand_boolop_is_one_site():
    mutants = COR().generate("ok = a and b and c")
    assert _sources(mutants) == ["ok = a or b or c"]
    assert (mutants[0].operator, mutants[0].line) == ("COR", 1)


def test_cor_nested_gives_two_mutants():
    mutants = COR().generate("ok = a and (b or c)")
    assert sorted(_sources(mutants)) == ["ok = a and (b and c)", "ok = a or (b or c)"]


# --- ConstantReplacement -----------------------------------------------------------------------


def test_constant_zero_and_one_swap():
    assert _sources(ConstantReplacement().generate("x = 0")) == ["x = 1"]
    assert _sources(ConstantReplacement().generate("x = 1")) == ["x = 0"]


def test_constant_bool_is_separate_from_int():
    assert _sources(ConstantReplacement().generate("x = True")) == ["x = False"]
    assert _sources(ConstantReplacement().generate("x = False")) == ["x = True"]


def test_constant_bool_does_not_become_int():
    # True == 1 olsa da True için yalnızca bool mutantı üretilir (``x = 0`` değil).
    mutants = ConstantReplacement().generate("x = True")
    assert len(mutants) == 1
    assert mutants[0].description == "True -> False"


def test_constant_mixed_sites_each_mutate_once():
    mutants = ConstantReplacement().generate("x = [0, 1, True]")
    assert _sources(mutants) == ["x = [1, 1, True]", "x = [0, 0, True]", "x = [0, 1, False]"]
    assert [m.operator for m in mutants] == ["CONST"] * 3


@pytest.mark.parametrize("value", ["2", "-5", "0.0", "1.0", "'0'", "None", "b'1'", "0j"])
def test_constant_other_values_are_not_mutated(value):
    assert ConstantReplacement().generate(f"x = {value}") == []


def test_constant_negative_one_mutates_inner_literal():
    assert _sources(ConstantReplacement().generate("x = -1")) == ["x = -0"]


def test_constant_line_numbers():
    mutants = ConstantReplacement().generate("a = 5\nb = 0\nc = 7\nd = True")
    assert [m.line for m in mutants] == [2, 4]


# --- ReturnNone --------------------------------------------------------------------------------


def test_return_none_replaces_expression():
    mutants = ReturnNone().generate("def f(a):\n    return a + 1")
    assert _sources(mutants) == ["def f(a):\n    return None"]
    assert (mutants[0].operator, mutants[0].line) == ("RETURN_NONE", 2)
    assert mutants[0].description == "return a + 1 -> return None"


def test_return_none_skips_bare_return_and_return_none():
    assert ReturnNone().generate("def f():\n    return") == []
    assert ReturnNone().generate("def f():\n    return None") == []


def test_return_none_one_mutant_per_return():
    src = "def f(a):\n    if a:\n        return 1\n    return 2"
    mutants = ReturnNone().generate(src)
    assert [m.line for m in mutants] == [3, 4]
    assert _sources(mutants) == [
        "def f(a):\n    if a:\n        return None\n    return 2",
        "def f(a):\n    if a:\n        return 1\n    return None",
    ]


def test_return_none_covers_nested_function_returns():
    src = "def f():\n    def g():\n        return 1\n    return g"
    assert [m.line for m in ReturnNone().generate(src)] == [3, 4]


# --- ortak davranışlar -------------------------------------------------------------------------


@pytest.mark.parametrize("operator", ALL_OPERATORS, ids=lambda op: op.name)
def test_no_mutation_points_gives_empty_list(operator):
    assert operator.generate("def f(a):\n    pass") == []
    assert operator.generate("") == []


@pytest.mark.parametrize("operator", ALL_OPERATORS, ids=lambda op: op.name)
@pytest.mark.parametrize("bad", ["def f(:", "x = = 1", "return (", "x = 1\x00"])
def test_invalid_code_raises_value_error(operator, bad):
    with pytest.raises(ValueError, match="Geçersiz Python kodu"):
        operator.generate(bad)


@pytest.mark.parametrize("bad", ["def f(:", "x = 1\x00"])
def test_generate_all_invalid_code_raises_value_error(bad):
    with pytest.raises(ValueError):
        generate_all(bad)


@pytest.mark.parametrize("operator", ALL_OPERATORS, ids=lambda op: op.name)
def test_original_source_is_untouched_and_generation_repeatable(operator):
    src = "def f(a, b):\n    if a < b and a != 0:\n        return a + 1\n    return True"
    snapshot = str(src)
    first = operator.generate(src)
    second = operator.generate(src)
    assert src == snapshot
    assert first == second
    assert first, "bu örnek her operatör için en az bir mutasyon noktası içerir"


@pytest.mark.parametrize("operator", ALL_OPERATORS, ids=lambda op: op.name)
def test_every_mutant_is_valid_python_and_differs_from_original(operator):
    import ast

    src = "def f(a, b):\n    if a < b and a != 0:\n        return a + 1\n    return True"
    original = ast.unparse(ast.parse(src))
    for mutant in operator.generate(src):
        assert mutant.source != original
        ast.parse(mutant.source)


def test_docstring_is_never_mutated():
    src = 'def f(a):\n    """Returns 0 + 1 and True; a < b, a == b."""\n    return a * 2'
    mutants = generate_all(src)
    assert mutants
    for mutant in mutants:
        assert "Returns 0 + 1 and True; a < b, a == b." in mutant.source


def test_string_constants_are_not_mutated():
    assert _sources(generate_all("x = '0' + '1'")) == ["x = '0' - '1'"]


def test_mutant_is_frozen():
    mutant = Mutant("AOR", 1, "+ -> -", "x = a - b")
    with pytest.raises(AttributeError):
        mutant.line = 2  # type: ignore[misc]


def test_operator_base_is_abstract():
    with pytest.raises(TypeError):
        MutationOperator()  # type: ignore[abstract]


# --- registry ve generate_all ------------------------------------------------------------------


def test_registry_contains_all_operators_keyed_by_name():
    assert list(OPERATOR_REGISTRY) == ["AOR", "ROR", "COR", "CONST", "RETURN_NONE"]
    for name, operator in OPERATOR_REGISTRY.items():
        assert operator.name == name


def test_generate_all_combines_operators_in_registry_order():
    mutants = generate_all("def f(a):\n    return a + 1")
    assert [m.operator for m in mutants] == ["AOR", "CONST", "RETURN_NONE"]
    assert _sources(mutants) == [
        "def f(a):\n    return a - 1",
        "def f(a):\n    return a + 0",
        "def f(a):\n    return None",
    ]


def test_generate_all_with_selected_operators():
    mutants = generate_all("def f(a):\n    return a + 1", operators=[ReturnNone()])
    assert [m.operator for m in mutants] == ["RETURN_NONE"]
    assert generate_all("x = 1 + 1", operators=[]) == []


def test_generate_all_deduplicates_identical_sources():
    mutants = generate_all("x = a + b", operators=[AOR(), AOR()])
    assert len(mutants) == 1


class _Same(MutationOperator):
    name = "SAME"

    def generate(self, source: str) -> list[Mutant]:
        return [Mutant("SAME", 1, "noop", "x = 1")]


def test_generate_all_drops_mutants_equal_to_original():
    assert generate_all("x   =   1", operators=[_Same()]) == []


def test_generate_all_no_points_gives_empty_list():
    assert generate_all("def f(a):\n    pass") == []
