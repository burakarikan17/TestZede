from __future__ import annotations

import pytest
from result_builders import make_result

from testzede.domain.models import CodeUnit, RunStats, TestCase
from testzede.execution.coverage_runner import run_tests
from testzede.gui.pages import coverage_logic as logic


def _t(name: str) -> TestCase:
    return TestCase(name=name, code=f"def test_{name}(): pass", origin="user")


# --- line_statuses -----------------------------------------------------------------------------


def test_covered_partial_and_missed():
    result = make_result(
        all_lines={1, 2, 3, 4, 5},
        covered_lines={1, 2, 3, 5},
        all_branches={(2, 3), (2, 4)},
        covered_branches={(2, 3)},
    )
    assert logic.line_statuses(result) == {
        1: "covered",
        2: "partial",  # if: yalnızca bir dal kapsandı
        3: "covered",
        4: "missed",
        5: "covered",
    }


def test_line_with_all_branches_covered_is_covered():
    result = make_result(
        all_lines={2, 3, 4},
        covered_lines={2, 3, 4},
        all_branches={(2, 3), (2, 4)},
        covered_branches={(2, 3), (2, 4)},
    )
    assert logic.line_statuses(result)[2] == "covered"


def test_line_without_branches_is_covered_or_missed():
    result = make_result(all_lines={1, 2}, covered_lines={1})
    assert logic.line_statuses(result) == {1: "covered", 2: "missed"}


def test_negative_exit_arcs_count_as_branches():
    # Satır 6: if sonrası fonksiyondan çıkış arc'ı (6, -5) de bir daldır.
    base = {"all_lines": {6, 7}, "covered_lines": {6, 7}, "all_branches": {(6, 7), (6, -5)}}
    partial = make_result(**base, covered_branches={(6, 7)})
    full = make_result(**base, covered_branches={(6, 7), (6, -5)})
    assert logic.line_statuses(partial)[6] == "partial"
    assert logic.line_statuses(full)[6] == "covered"


def test_executed_line_with_no_covered_branch_is_partial():
    result = make_result(
        all_lines={2}, covered_lines={2}, all_branches={(2, 3), (2, 4)}, covered_branches=set()
    )
    assert logic.line_statuses(result) == {2: "partial"}


def test_unexecuted_line_with_branches_is_missed():
    result = make_result(all_lines={2}, all_branches={(2, 3), (2, 4)})
    assert logic.line_statuses(result) == {2: "missed"}


def test_branches_of_other_lines_do_not_leak():
    result = make_result(
        all_lines={1, 2},
        covered_lines={1, 2},
        all_branches={(1, 2), (1, 5)},
        covered_branches={(1, 2)},
    )
    statuses = logic.line_statuses(result)
    assert statuses == {1: "partial", 2: "covered"}


def test_non_executable_lines_are_absent():
    result = make_result(all_lines={1, 3}, covered_lines={1, 3})
    assert 2 not in logic.line_statuses(result)


def test_empty_result_has_no_statuses():
    assert logic.line_statuses(make_result()) == {}


def test_statuses_follow_real_coverage_data():
    source = (
        "def f(a):\n    x = 0\n    if a > 0:\n        x = 1\n    for i in range(a):\n"
        "        x += i\n    return x\n\nclass C:\n    def m(self, v):\n"
        "        while v > 3:\n            v -= 1\n        return v\n"
    )
    unit = CodeUnit("u", source, "f", None)
    result = run_tests(unit, [TestCase("t", "def test_a():\n    assert f(0) == 0", "user")])
    assert logic.line_statuses(result) == {
        1: "covered",
        2: "covered",
        3: "partial",
        4: "missed",
        5: "partial",
        6: "missed",
        7: "covered",
        9: "covered",
        10: "covered",
        11: "missed",
        12: "missed",
        13: "missed",
    }
    assert logic.function_rows(result) == [("C.m", 0.0), ("f", pytest.approx(60.0))]


# --- function_rows / outcome_rows --------------------------------------------------------------


def test_function_rows_sorted_by_name_not_by_percentage():
    result = make_result(per_function={"zeta": 1.0, "alpha": 0.25, "Mid": 0.5})
    assert logic.function_rows(result) == [("Mid", 50.0), ("alpha", 25.0), ("zeta", 100.0)]


def test_function_rows_empty():
    assert logic.function_rows(make_result()) == []


def test_outcome_rows_follow_test_order_and_lookup_by_name():
    result = make_result(outcomes={"b": "failed", "a": "passed"})
    assert logic.outcome_rows([_t("a"), _t("b")], result) == [("a", "passed"), ("b", "failed")]


def test_missing_outcome_is_error():
    result = make_result(outcomes={"a": "passed"})
    assert logic.outcome_rows([_t("a"), _t("ghost")], result) == [
        ("a", "passed"),
        ("ghost", "error"),
    ]


def test_outcome_rows_empty():
    assert logic.outcome_rows([], make_result()) == []
    assert logic.outcome_rows([_t("a")], make_result()) == [("a", "error")]


# --- summary -----------------------------------------------------------------------------------


def test_summary_formats_every_field():
    result = make_result(
        all_lines={1, 2, 3, 4},
        covered_lines={1, 2, 3},
        all_branches={(2, 3), (2, 4)},
        covered_branches={(2, 3)},
        stats=RunStats(generated=3, compiled=2, execution_time_s=1.234),
    )
    s = logic.summary(result)
    assert s.lines == "75.0% (3/4)"
    assert s.branches == "50.0% (1/2)"
    assert s.compilation == "66.7% (2/3)"
    assert s.time == "1.23 sn"


def test_summary_without_data_uses_dash():
    s = logic.summary(make_result(stats=RunStats(0, 0, 0.0)))
    assert (s.lines, s.branches, s.compilation) == ("—", "—", "—")
    assert s.time == "0.00 sn"
    assert logic.empty_summary() == logic.CoverageSummary("—", "—", "—", "—")


def test_summary_full_coverage():
    result = make_result(
        all_lines={1}, covered_lines={1}, all_branches={(1, 2)}, covered_branches={(1, 2)}
    )
    s = logic.summary(result)
    assert s.lines == "100.0% (1/1)" and s.branches == "100.0% (1/1)"


# --- source_lines ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a\nb\n", ["a", "b"]),
        ("a\r\nb\r\n", ["a", "b"]),
        ("a\rb", ["a", "b"]),
        ("a\n\nb", ["a", "", "b"]),
        ("", []),
        ("x", ["x"]),
    ],
)
def test_source_lines(source, expected):
    assert logic.source_lines(source) == expected
