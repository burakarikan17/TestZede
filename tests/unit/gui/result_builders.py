"""GUI testleri için sentetik ``ExecutionResult`` üreticisi."""

from __future__ import annotations

from collections.abc import Iterable

from testzede.domain.models import CoverageReport, RunStats
from testzede.execution.coverage_runner import ExecutionResult


def make_result(
    all_lines: Iterable[int] = (),
    covered_lines: Iterable[int] = (),
    all_branches: Iterable[tuple[int, int]] = (),
    covered_branches: Iterable[tuple[int, int]] = (),
    per_function: dict[str, float] | None = None,
    outcomes: dict[str, str] | None = None,
    stats: RunStats | None = None,
) -> ExecutionResult:
    """Sentetik ``ExecutionResult``; kapsama sayıları kümelerden türetilir."""
    all_lines, covered_lines = frozenset(all_lines), frozenset(covered_lines)
    all_branches, covered_branches = frozenset(all_branches), frozenset(covered_branches)
    return ExecutionResult(
        coverage=CoverageReport(
            covered_lines=len(covered_lines),
            total_lines=len(all_lines),
            covered_branches=len(covered_branches),
            total_branches=len(all_branches),
            per_function=per_function or {},
        ),
        stats=stats or RunStats(generated=1, compiled=1, execution_time_s=0.5),
        covered_lines=covered_lines,
        covered_branches=covered_branches,
        all_lines=all_lines,
        all_branches=all_branches,
        test_outcomes=outcomes or {},  # type: ignore[arg-type]
    )
