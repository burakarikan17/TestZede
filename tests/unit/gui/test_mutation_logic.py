from __future__ import annotations

from testzede.domain.models import MutationReport, RunStats
from testzede.gui.pages import mutation_logic as logic
from testzede.mutation.engine import MutationRun
from testzede.mutation.operators import Mutant, generate_all


def make_run(
    total: int = 0,
    killed: int = 0,
    survived: int = 0,
    timeout: int = 0,
    survivors: list[Mutant] | None = None,
    skipped: int = 0,
    stats: RunStats | None = None,
) -> MutationRun:
    return MutationRun(
        report=MutationReport(total=total, killed=killed, survived=survived, timeout=timeout),
        stats=stats or RunStats(generated=3, compiled=3, execution_time_s=1.234),
        survivors=survivors or [],
        skipped_uncovered=skipped,
    )


def _m(operator: str, line: int, description: str = "d", source: str = "x = 1") -> Mutant:
    return Mutant(operator, line, description, source)


# --- summary_texts -----------------------------------------------------------------------------


def test_summary_texts_formats_every_field():
    run = make_run(
        total=10,
        killed=6,
        survived=3,
        timeout=1,
        skipped=2,
        stats=RunStats(generated=3, compiled=2, execution_time_s=1.234),
    )
    s = logic.summary_texts(run)
    assert s.score == "70.0%"  # (killed + timeout) / total
    assert (s.killed, s.survived, s.timeout, s.skipped) == ("6", "3", "1", "2")
    assert s.compilation == "66.7% (2/3)"
    assert s.time == "1.23 sn"


def test_summary_texts_perfect_and_zero_scores():
    assert logic.summary_texts(make_run(total=4, killed=4)).score == "100.0%"
    assert logic.summary_texts(make_run(total=4, survived=4)).score == "0.0%"


def test_summary_texts_without_mutants_uses_dash_for_score():
    s = logic.summary_texts(make_run())
    assert s.score == "—"
    assert (s.killed, s.survived, s.timeout, s.skipped) == ("0", "0", "0", "0")


def test_summary_texts_without_generated_tests_uses_dash_for_compilation():
    s = logic.summary_texts(make_run(stats=RunStats(0, 0, 0.0)))
    assert s.compilation == "—" and s.time == "0.00 sn"


def test_empty_summary_is_all_dashes():
    assert set(vars(logic.empty_summary()).values()) == {"—"}


# --- survivor_rows -----------------------------------------------------------------------------


def test_survivor_rows_sorted_by_line_then_operator():
    run = make_run(
        survivors=[
            _m("RETURN_NONE", 9, "r9"),
            _m("ROR", 3, "ror3"),
            _m("AOR", 3, "aor3"),
            _m("CONST", 1, "c1"),
        ]
    )
    assert logic.survivor_rows(run) == [
        ("CONST", 1, "c1"),
        ("AOR", 3, "aor3"),
        ("ROR", 3, "ror3"),
        ("RETURN_NONE", 9, "r9"),
    ]
    assert [m.description for m in logic.sorted_survivors(run)] == ["c1", "aor3", "ror3", "r9"]


def test_survivor_rows_does_not_reorder_the_run_in_place():
    survivors = [_m("B", 2), _m("A", 1)]
    logic.survivor_rows(make_run(survivors=survivors))
    assert [m.line for m in survivors] == [2, 1]


def test_survivor_rows_empty():
    assert logic.survivor_rows(make_run()) == []


# --- mutant_diff -------------------------------------------------------------------------------


def test_diff_shows_only_the_changed_line_with_context_and_no_headers():
    diff = logic.mutant_diff("def f(a):\n    return a + 1\n", "def f(a):\n    return a - 1")
    assert diff == " def f(a):\n-    return a + 1\n+    return a - 1"
    assert "---" not in diff.splitlines()[0] and "@@" not in diff


def test_diff_ignores_formatting_and_comment_differences_of_the_original():
    original = "def f(a):  # yorum\n    return a+1\n"
    mutant = generate_all(original)[0]
    diff = logic.mutant_diff(original, mutant.source)
    assert diff == " def f(a):\n-    return a + 1\n+    return a - 1"


def test_diff_has_two_lines_of_context():
    original = "\n".join(f"x{i} = {i + 5}" for i in range(7)) + "\n"
    mutant = original.replace("x3 = 8", "x3 = 0")
    diff = logic.mutant_diff(original, mutant).splitlines()
    assert diff == [" x1 = 6", " x2 = 7", "-x3 = 8", "+x3 = 0", " x4 = 9", " x5 = 10"]


def test_distant_hunks_are_separated():
    original = "\n".join(f"x{i} = {i + 5}" for i in range(12))
    mutant = original.replace("x0 = 5", "x0 = 0").replace("x11 = 16", "x11 = 0")
    diff = logic.mutant_diff(original, mutant).splitlines()
    assert "⋯" in diff
    assert diff.index("⋯") == diff.index("+x0 = 0") + 3  # 2 satır bağlam sonra ayırıcı
    assert diff[-3:] == [" x10 = 15", "-x11 = 16", "+x11 = 0"]


def test_identical_sources_give_empty_diff():
    assert logic.mutant_diff("x = 1\n", "x = 1") == ""


def test_diff_keeps_lines_that_look_like_headers():
    # Silinen satır "--x" diff'te "---x" olur; başlık sanılıp atılmamalı.
    assert logic.mutant_diff("--x\n", "pass") == "---x\n+pass"


def test_diff_falls_back_to_raw_original_when_it_is_not_valid_python():
    diff = logic.mutant_diff("def f(:\n", "pass")
    assert diff == "-def f(:\n+pass"
