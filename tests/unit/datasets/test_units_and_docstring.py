import pytest

from testzede.datasets.base import (
    EMPTY_SOURCE,
    NO_ENTRY_POINT,
    SYNTAX_ERROR,
    LoadResult,
    SkippedUnit,
)
from testzede.datasets.docstring import doctest_examples
from testzede.datasets.hashing import sha256_file, sha256_text
from testzede.datasets.units import make_unit
from testzede.domain.models import CodeUnit


def test_make_unit_picks_first_function_when_no_entry_point_given():
    unit = make_unit("u/1", "demo", "x = 1\ndef a(v):\n    return v\ndef b(v):\n    return v\n")
    assert isinstance(unit, CodeUnit)
    assert unit.entry_point == "a"
    assert unit.dataset == "demo"


def test_make_unit_with_explicit_entry_point():
    unit = make_unit("u/1", "demo", "def a(v):\n    return v\ndef b(v):\n    return v\n", "b")
    assert isinstance(unit, CodeUnit)
    assert unit.entry_point == "b"


@pytest.mark.parametrize(
    ("source", "entry", "reason"),
    [
        ("   \n", None, EMPTY_SOURCE),
        ("def (:\n", None, SYNTAX_ERROR),
        ("x = 1\n", None, NO_ENTRY_POINT),
        ("def a(v):\n    return v\n", "zzz", NO_ENTRY_POINT),
        ("\x00", None, SYNTAX_ERROR),
    ],
)
def test_make_unit_reports_reasons(source, entry, reason):
    result = make_unit("u/1", "demo", source, entry)
    assert isinstance(result, SkippedUnit)
    assert result.reason == reason
    assert result.uid == "u/1"


def test_doctest_examples_keeps_only_the_call_lines():
    doc = "Toplar.\n\n>>> add(1, 2)\n3\n>>> add(-1, 1)\n0\n"
    assert doctest_examples(doc) == (">>> add(1, 2)", ">>> add(-1, 1)")


def test_doctest_examples_handles_missing_or_broken_docstrings():
    assert doctest_examples(None) == ()
    assert doctest_examples("") == ()
    assert doctest_examples("açıklama, örnek yok") == ()
    assert doctest_examples(">>> f(1)\n  bozuk girinti\n>>>   \n") != ()  # bozuk ama çökmez


def test_load_result_counts_skip_reasons():
    result = LoadResult(
        "demo",
        (),
        (SkippedUnit("a", SYNTAX_ERROR), SkippedUnit("b", SYNTAX_ERROR), SkippedUnit("c", "x")),
    )
    assert result.skip_counts() == {SYNTAX_ERROR: 2, "x": 1}


def test_hashing(tmp_path):
    path = tmp_path / "f.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == sha256_text("abc")
    assert sha256_text("abc").startswith("ba7816bf")
