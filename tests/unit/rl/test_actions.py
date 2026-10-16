import ast
import math
import random

import pytest

from testzede.rl.actions import ACTION_NAMES, ACTION_REGISTRY, ActionContext
from testzede.rl.signature import ANY, ParamSpec, TypeSpec

PARAMS = (
    ParamSpec("n", TypeSpec("int")),
    ParamSpec("x", TypeSpec("float")),
    ParamSpec("s", TypeSpec("str")),
    ParamSpec("flag", TypeSpec("bool")),
    ParamSpec("xs", TypeSpec("list", (TypeSpec("int"),))),
    ParamSpec("t", TypeSpec("tuple", (TypeSpec("str"),))),
    ParamSpec("d", TypeSpec("dict", (TypeSpec("str"), TypeSpec("float")))),
    ParamSpec("anything", ANY),
)
CTX = ActionContext(params=PARAMS, seed_inputs=((1, 2.0, "a", True, [1], ("b",), {}, 0),))


def test_registry_has_all_architecture_actions_in_stable_order():
    assert ACTION_NAMES == (
        "BOUNDARY",
        "EMPTY",
        "NEGATIVE",
        "RANDOM_SMALL",
        "RANDOM_LARGE",
        "SPECIAL_CHARS",
        "FROM_DOCSTRING",
        "MUTATE_BEST",
    )


@pytest.mark.parametrize("name", ACTION_NAMES)
def test_generated_inputs_round_trip_through_repr(name):
    rng = random.Random(0)
    ctx = ActionContext(PARAMS, CTX.seed_inputs, best_input=CTX.seed_inputs[0])
    for _ in range(50):
        args = ACTION_REGISTRY[name].generate(ctx, rng)
        assert args is not None and len(args) == len(PARAMS)
        assert ast.literal_eval(repr(args)) == args


@pytest.mark.parametrize("name", ACTION_NAMES)
def test_generated_floats_are_finite(name):
    rng = random.Random(1)
    ctx = ActionContext(PARAMS, CTX.seed_inputs, best_input=CTX.seed_inputs[0])
    for _ in range(50):
        x = ACTION_REGISTRY[name].generate(ctx, rng)[1]
        assert isinstance(x, float) and math.isfinite(x)


def test_generation_is_deterministic_for_same_seed():
    action = ACTION_REGISTRY["RANDOM_SMALL"]
    assert action.generate(CTX, random.Random(7)) == action.generate(CTX, random.Random(7))


def test_empty_produces_empty_values():
    args = ACTION_REGISTRY["EMPTY"].generate(CTX, random.Random(0))
    assert args[:7] == (0, 0.0, "", False, [], (), {})


def test_negative_produces_negative_numbers():
    rng = random.Random(0)
    for _ in range(20):
        n, x, *_, xs, _t, _d, _a = ACTION_REGISTRY["NEGATIVE"].generate(CTX, rng)
        assert n < 0 and x < 0 and all(v < 0 for v in xs)


def test_random_large_produces_long_strings_and_lists():
    args = ACTION_REGISTRY["RANDOM_LARGE"].generate(CTX, random.Random(0))
    assert len(args[2]) >= 50 and len(args[4]) >= 50


def test_from_docstring_uses_seed_inputs_or_none():
    rng = random.Random(0)
    assert ACTION_REGISTRY["FROM_DOCSTRING"].generate(CTX, rng) == CTX.seed_inputs[0]
    assert ACTION_REGISTRY["FROM_DOCSTRING"].generate(ActionContext(PARAMS), rng) is None


def test_from_docstring_ignores_seed_with_wrong_arity():
    ctx = ActionContext(PARAMS, seed_inputs=((1, 2),))
    assert ACTION_REGISTRY["FROM_DOCSTRING"].generate(ctx, random.Random(0)) is None


def test_mutate_best_changes_exactly_one_argument():
    best = (5, "abc", [1, 2, 3])
    params = (
        ParamSpec("n", TypeSpec("int")),
        ParamSpec("s", TypeSpec("str")),
        ParamSpec("xs", TypeSpec("list")),
    )
    ctx = ActionContext(params, best_input=best)
    rng = random.Random(0)
    for _ in range(30):
        args = ACTION_REGISTRY["MUTATE_BEST"].generate(ctx, rng)
        assert sum(a != b for a, b in zip(args, best, strict=True)) <= 1
        assert type(args[2]) is list


def test_mutate_best_without_best_input_is_none():
    assert ACTION_REGISTRY["MUTATE_BEST"].generate(CTX, random.Random(0)) is None


def test_mutate_best_negates_bool_not_increments():
    assert ACTION_REGISTRY["MUTATE_BEST"].mutate(True, random.Random(0)) is False


def test_function_without_params_yields_empty_tuple():
    ctx = ActionContext(params=())
    assert ACTION_REGISTRY["BOUNDARY"].generate(ctx, random.Random(0)) == ()
