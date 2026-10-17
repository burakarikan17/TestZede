import subprocess
import sys

import pytest

from testzede.rl.env import EnvConfig
from testzede.rl.trainer import RLConfig
from testzede.services import rl_service
from testzede.services.errors import ServiceError

SOURCE = '''import math


def clamp(x: int, low: int, high: int) -> int:
    """
    >>> clamp(5, 0, 3)
    3
    """
    if x < low:
        return low
    if x > high:
        return high
    return x


def nothing():
    return 1
'''

FAST = RLConfig(env=EnvConfig(max_steps=8, patience=5))


def test_list_functions_skips_parameterless():
    assert rl_service.list_functions(SOURCE) == ["clamp"]


def test_list_functions_reports_syntax_error():
    with pytest.raises(ServiceError, match="satır 1"):
        rl_service.list_functions("def f(:\n")


@pytest.mark.parametrize(
    ("source", "entry", "message"),
    [("   ", "f", "boş"), ("def f(:\n", "f", "ayrıştırılamadı"), (SOURCE, "yok", "bulunamadı")],
)
def test_build_unit_errors(source, entry, message):
    with pytest.raises(ServiceError, match=message):
        rl_service.build_unit(source, entry)


def test_build_unit_takes_docstring_examples():
    unit = rl_service.build_unit(SOURCE, "clamp")
    assert unit.seed_examples == (">>> clamp(5, 0, 3)",)


def test_load_rl_config_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("agent:\n  bilinmeyen: 1\n", encoding="utf-8")
    with pytest.raises(ServiceError, match="Yapılandırma geçersiz"):
        rl_service.load_rl_config(bad)


def test_generate_and_saved_module_runs_under_pytest(tmp_path):
    result = rl_service.generate(SOURCE, "clamp", config=FAST, seed=3)
    assert result.tests
    assert result.coverage is not None and result.coverage.covered_lines > 0
    assert 0.0 <= result.branch_rate <= 1.0

    module = rl_service.tests_module(result)
    assert module.count("import pytest") == 1
    (tmp_path / "target.py").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "test_clamp.py").write_text(module, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_clamp.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"{len(result.tests)} passed" in proc.stdout


USER_TESTS = """from hesap import clamp


def test_inside():
    assert clamp(2, 0, 3) == 2
"""


def test_user_test_case_rewrites_module_imports():
    code = "import hesap\nimport hesap as h\nfrom hesap import clamp\nimport math\n\n\ndef test_x():\n    pass\n"
    test = rl_service.user_test_case(code, "hesap")
    assert test.origin == "user" and test.name == "user_tests"
    assert "import target as hesap" in test.code
    assert "import target as h" in test.code
    assert "from target import clamp" in test.code
    assert "import math" in test.code


@pytest.mark.parametrize(
    ("code", "message"),
    [("def test_x(:\n", "satır 1"), ("def helper():\n    pass\n", "test fonksiyonu yok")],
)
def test_user_test_case_errors(code, message):
    with pytest.raises(ServiceError, match=message):
        rl_service.user_test_case(code, "hesap")


def test_guess_module_name():
    assert rl_service.guess_module_name(USER_TESTS, SOURCE) == "hesap"
    assert rl_service.guess_module_name("import pytest\n", SOURCE) is None
    assert rl_service.guess_module_name("def test(:", SOURCE) is None


def test_generate_augments_user_tests():
    result = rl_service.generate(SOURCE, "clamp", config=FAST, seed=3, user_tests=USER_TESTS)
    assert result.user_outcome == "passed"
    assert result.baseline is not None
    assert result.coverage.covered_lines > result.baseline.covered_lines
    assert result.tests  # RL eksik dalları (x < low, x > high) için test ekledi


def test_generate_with_complete_user_tests_adds_nothing():
    complete = USER_TESTS + (
        "\n\ndef test_edges():\n    assert clamp(-1, 0, 3) == 0\n    assert clamp(9, 0, 3) == 3\n"
    )
    result = rl_service.generate(SOURCE, "clamp", config=FAST, seed=3, user_tests=complete)
    assert result.tests == []
    assert result.coverage.covered_branches == result.coverage.total_branches


def test_saved_module_uses_user_module_name():
    result = rl_service.generate(SOURCE, "clamp", config=FAST, seed=3)
    assert "from hesap import clamp" in rl_service.tests_module(result, "hesap")
