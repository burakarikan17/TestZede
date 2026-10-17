from __future__ import annotations

import ast

import pytest

from testzede.domain.models import CodeUnit
from testzede.execution.coverage_runner import run_tests
from testzede.services.test_loader import load_tests

# --- test düğümlerini bulma --------------------------------------------------------------------


def test_single_test_function():
    cases = load_tests("def test_a():\n    assert 1 == 1")
    assert len(cases) == 1
    assert (cases[0].name, cases[0].origin) == ("test_a", "user")
    assert cases[0].code == "def test_a():\n    assert 1 == 1"


def test_many_tests_keep_source_order_and_are_separate():
    src = "def test_a():\n    pass\n\ndef test_b():\n    pass\n\ndef test_c():\n    pass\n"
    cases = load_tests(src)
    assert [c.name for c in cases] == ["test_a", "test_b", "test_c"]
    assert "test_b" not in cases[0].code and "test_a" not in cases[1].code


def test_class_with_methods_is_one_test_case_named_after_the_class():
    src = "class TestMath:\n    def test_x(self):\n        assert 1\n\n    def test_y(self):\n        assert 2\n"
    cases = load_tests(src)
    assert [c.name for c in cases] == ["TestMath"]
    assert "def test_x" in cases[0].code and "def test_y" in cases[0].code


def test_only_top_level_tests_count():
    src = (
        "def helper():\n    def test_inner():\n        pass\n"
        "class Helper:\n    def test_not_collected(self):\n        pass\n"
        "def test_real():\n    pass\n"
    )
    assert [c.name for c in load_tests(src)] == ["test_real"]


def test_decorators_are_kept():
    src = "import pytest\n@pytest.mark.parametrize('a', [1, 2])\ndef test_p(a):\n    assert a\n"
    case = load_tests(src)[0]
    assert "@pytest.mark.parametrize('a', [1, 2])" in case.code
    ast.parse(case.code)


# --- ortak ön kısım ----------------------------------------------------------------------------


def test_non_test_nodes_become_a_shared_preamble_before_every_test():
    src = (
        "import pytest\n"
        "from math import floor\n"
        "LIMIT = 10\n"
        "def helper(x):\n    return x + LIMIT\n"
        "@pytest.fixture\ndef data():\n    return [1, 2]\n"
        "class Helper:\n    pass\n"
        "def test_a():\n    assert helper(1) == 11\n"
        "def test_b(data):\n    assert data\n"
    )
    cases = load_tests(src)
    assert [c.name for c in cases] == ["test_a", "test_b"]
    for case in cases:
        for piece in (
            "import pytest",
            "from math import floor",
            "LIMIT = 10",
            "def helper",
            "def data",
            "class Helper",
        ):
            assert piece in case.code
        ast.parse(case.code)
        assert case.code.index("LIMIT = 10") < case.code.index("def test_")
    assert "def test_b" not in cases[0].code and "def test_a" not in cases[1].code


def test_no_preamble_when_file_has_only_tests():
    assert load_tests("def test_a():\n    pass").pop().code.startswith("def test_a")


# --- import yeniden yazma ----------------------------------------------------------------------


def _code(src: str, module: str | None = "calc") -> str:
    return load_tests(src + "\ndef test_x():\n    pass", module)[0].code


def test_from_import_is_redirected_to_target():
    assert "from target import add, sub" in _code("from calc import add, sub")


def test_plain_import_becomes_aliased_target_import():
    code = _code("import calc")
    assert "import target as calc" in code


def test_import_with_alias_keeps_alias():
    code = _code("import calc as c")
    assert "import target as c" in code and "calc" not in code


def test_star_import_is_redirected():
    assert "from target import *" in _code("from calc import *")


def test_multi_alias_import_rewrites_only_the_matching_alias():
    code = _code("import os, calc, sys")
    assert "import os, target as calc, sys" in code


def test_import_inside_test_body_is_rewritten():
    code = load_tests("def test_x():\n    from calc import add\n    assert add", "calc")[0].code
    assert "from target import add" in code


@pytest.mark.parametrize(
    "unrelated",
    [
        "from other import x",
        "import other",
        "import calculator",
        "from calculator import x",
        "import calc.sub",
        "from calc.sub import y",
        "from .calc import z",
        "import pytest",
    ],
)
def test_unrelated_imports_are_untouched(unrelated):
    code = _code(unrelated)
    assert ast.unparse(ast.parse(unrelated)) in code
    assert "target" not in code


@pytest.mark.parametrize("module_name", [None, ""])
def test_no_rewriting_without_module_name(module_name):
    assert "from calc import add" in _code("from calc import add", module_name)


# --- adlar, hatalar ----------------------------------------------------------------------------


def test_duplicate_names_get_numeric_suffixes():
    src = "def test_a():\n    pass\ndef test_a():\n    pass\ndef test_a():\n    pass\n"
    assert [c.name for c in load_tests(src)] == ["test_a", "test_a_2", "test_a_3"]


def test_suffix_does_not_collide_with_existing_name():
    src = "def test_a():\n    pass\ndef test_a_2():\n    pass\ndef test_a():\n    pass\n"
    names = [c.name for c in load_tests(src)]
    assert len(set(names)) == 3 and names[:2] == ["test_a", "test_a_2"]


@pytest.mark.parametrize(
    "src",
    [
        "x = 1",
        "def helper():\n    pass",
        "import pytest",
        "class Helper:\n    def test_m(self): pass",
        "async def test_async():\n    pass",
    ],
)
def test_no_tests_raises(src):
    with pytest.raises(ValueError, match="Test fonksiyonu bulunamadı"):
        load_tests(src)


def test_syntax_error_reports_line():
    with pytest.raises(ValueError, match="Satır 2"):
        load_tests("def test_a():\n    assert (1 +\n")


def test_syntax_error_on_first_line():
    with pytest.raises(ValueError, match="Satır 1"):
        load_tests("def test_a(:\n    pass")


@pytest.mark.parametrize("src", ["", "   \n\t"])
def test_blank_source_raises(src):
    with pytest.raises(ValueError, match="boş"):
        load_tests(src)


def test_null_byte_raises_value_error():
    with pytest.raises(ValueError):
        load_tests("def test_a():\n    pass\x00")


# --- gerçek koşu -------------------------------------------------------------------------------

CALC = "def add(a, b):\n    return a + b\n"
USER_TESTS = """\
import pytest
import calc
from calc import add

BASE = 2


def helper(x):
    return x + BASE


def test_add():
    assert add(1, 2) == 3


def test_helper_and_module_access():
    assert helper(1) == 3
    assert calc.add(1, 1) == 2


class TestAdd:
    def test_negative(self):
        assert add(-1, 1) == 0


def test_raises():
    with pytest.raises(TypeError):
        add(1, None)
"""


def test_loaded_tests_really_pass_with_run_tests():
    cases = load_tests(USER_TESTS, "calc")
    unit = CodeUnit(uid="user/0", source=CALC, entry_point="add", dataset=None)
    result = run_tests(unit, cases)
    assert result.test_outcomes == {
        "test_add": "passed",
        "test_helper_and_module_access": "passed",
        "TestAdd": "passed",
        "test_raises": "passed",
    }
    assert result.stats.compilation_rate == 1.0
    assert result.coverage.covered_lines == result.coverage.total_lines


def test_loaded_tests_really_pass_with_coverage_service():
    coverage_service = pytest.importorskip(
        "testzede.services.coverage_service",
        reason="CoverageService bu branch'te yok (services-facade dalında)",
    )
    result = coverage_service.CoverageService().run(CALC, load_tests(USER_TESTS, "calc"))
    assert set(result.test_outcomes.values()) == {"passed"}
