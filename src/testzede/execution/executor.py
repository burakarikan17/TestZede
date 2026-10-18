"""``rl.executor.Executor`` sözleşmesinin sandbox tabanlı gerçek uygulaması."""

from __future__ import annotations

from collections.abc import Sequence

from testzede.domain.models import CodeUnit, TestCase
from testzede.execution import coverage_runner, sandbox


class SandboxExecutor:
    """Oracle çağrılarını ``sandbox``'ta, testleri ``coverage_runner``'da çalıştırır.

    İki metot da istisna fırlatmaz (alt modüllerin garantisi).
    """

    def call_function(
        self, unit: CodeUnit, args_repr: str, *, timeout: float = 2.0
    ) -> sandbox.CallResult:
        return sandbox.call_function(unit, args_repr, timeout=timeout)

    def run_tests(
        self, unit: CodeUnit, tests: Sequence[TestCase], *, timeout: float = 10.0
    ) -> coverage_runner.ExecutionResult:
        return coverage_runner.run_tests(unit, tests, timeout=timeout)
