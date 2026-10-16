"""RL testleri için sahte çalıştırıcı (``execution`` modülünün yerine).

Kod süreç içinde çalıştırılır; coverage, girdiye göre kapsanan satır/branch
kümelerini döndüren elle yazılmış bir modelden okunur.
"""

from __future__ import annotations

import ast
import sys
import types
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import pytest

from testzede.domain.models import CodeUnit, RunStats, TestCase
from testzede.rl.executor import TARGET_MODULE

SIGN_SOURCE = """def sign(x: int) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0
"""

Lines = frozenset[int]
Arcs = frozenset[tuple[int, int]]


def sign_model(args: tuple) -> tuple[set[int], set[tuple[int, int]]]:
    (x,) = args
    if x > 0:
        return {2, 3}, {(2, 3)}
    if x < 0:
        return {2, 4, 5}, {(2, 4), (4, 5)}
    return {2, 4, 6}, {(2, 4), (4, 6)}


@dataclass(frozen=True)
class FakeCall:
    status: str
    value_repr: str | None = None
    exc_type: str | None = None
    duration_s: float = 0.001


@dataclass
class FakeRun:
    stats: RunStats
    covered_lines: Lines
    covered_branches: Arcs
    all_lines: Lines
    all_branches: Arcs
    test_outcomes: dict[str, str]


@dataclass
class FakeExecutor:
    model: Callable[[tuple], tuple[set[int], set[tuple[int, int]]]]
    all_lines: Lines
    all_branches: Arcs
    calls: list[str] = field(default_factory=list)
    runs: int = 0

    def _module(self, unit: CodeUnit) -> types.ModuleType:
        module = types.ModuleType(TARGET_MODULE)
        exec(compile(unit.source, "<target>", "exec"), module.__dict__)  # noqa: S102
        return module

    def call_function(self, unit: CodeUnit, args_repr: str, *, timeout: float = 2.0) -> FakeCall:
        self.calls.append(args_repr)
        try:
            func = getattr(self._module(unit), unit.entry_point)
            value = func(*ast.literal_eval(args_repr))
        except Exception as exc:  # noqa: BLE001 — sandbox hiçbir istisnayı dışarı vermez
            return FakeCall("raised", exc_type=type(exc).__name__)
        return FakeCall("ok", value_repr=repr(value))

    def run_tests(
        self, unit: CodeUnit, tests: Sequence[TestCase], *, timeout: float = 10.0
    ) -> FakeRun:
        self.runs += 1
        module = self._module(unit)
        real = getattr(module, unit.entry_point)
        seen: list[tuple] = []

        def recorder(*args):
            seen.append(args)
            return real(*args)

        setattr(module, unit.entry_point, recorder)
        outcomes: dict[str, str] = {}
        previous = sys.modules.get(TARGET_MODULE)
        sys.modules[TARGET_MODULE] = module
        try:
            for test in tests:
                namespace: dict = {}
                try:
                    exec(compile(test.code, f"<{test.name}>", "exec"), namespace)  # noqa: S102
                    namespace[test.name]()
                    outcomes[test.name] = "passed"
                except AssertionError:
                    outcomes[test.name] = "failed"
                except Exception:  # noqa: BLE001
                    outcomes[test.name] = "error"
        finally:
            if previous is None:
                sys.modules.pop(TARGET_MODULE, None)
            else:
                sys.modules[TARGET_MODULE] = previous

        lines: set[int] = set()
        arcs: set[tuple[int, int]] = set()
        for args in seen:
            hit_lines, hit_arcs = self.model(args)
            lines |= hit_lines
            arcs |= hit_arcs
        compiled = sum(1 for o in outcomes.values() if o != "error")
        return FakeRun(
            RunStats(len(tests), compiled, 0.01),
            frozenset(lines),
            frozenset(arcs),
            self.all_lines,
            self.all_branches,
            outcomes,
        )


@pytest.fixture
def sign_unit() -> CodeUnit:
    return CodeUnit("demo/sign", SIGN_SOURCE, entry_point="sign", seed_examples=(">>> sign(5)",))


@pytest.fixture
def sign_executor() -> FakeExecutor:
    return FakeExecutor(
        sign_model,
        all_lines=frozenset({2, 3, 4, 5, 6}),
        all_branches=frozenset({(2, 3), (2, 4), (4, 5), (4, 6)}),
    )
