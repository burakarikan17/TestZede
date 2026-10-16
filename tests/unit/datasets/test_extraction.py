import pytest

from testzede.datasets.extraction import (
    ASYNC_FUNCTION,
    DECORATED,
    EXTERNAL_DEPENDENCY,
    GLOBAL_STATEMENT,
    HELPER_REJECTED,
    NO_PARAMETERS,
    NOT_PUBLIC,
    REDEFINED,
    SIDE_EFFECT_DEPENDENCY,
    UNSAFE_BUILTIN,
    ExtractionError,
    extract_functions,
)


def names(source: str) -> list[str]:
    return [f.name for f in extract_functions(source).functions]


def rejected(source: str) -> dict[str, int]:
    return dict(extract_functions(source).rejected)


def run(source: str, function: str, *args):
    namespace: dict = {}
    exec(compile(source, "<unit>", "exec"), namespace)  # noqa: S102 - üretilen birimi çalıştırır
    return namespace[function](*args)


def test_pure_function_is_extracted_and_runs():
    assert names("def add(a, b):\n    return a + b\n") == ["add"]


def test_imports_constants_and_helpers_are_bundled():
    source = (
        "import math\n"
        "from collections import Counter\n"
        "import json\n"
        "SCALE = 2\n"
        "def _square(x):\n    return x * x\n"
        "def norm(x):\n    return math.sqrt(_square(x)) * SCALE\n"
        "def unrelated(x):\n    return json.dumps(x)\n"
        "def count(items):\n    return Counter(items)\n"
    )
    result = extract_functions(source)
    by_name = {f.name: f.source for f in result.functions}
    assert set(by_name) == {"norm", "unrelated", "count"}
    assert "import math" in by_name["norm"]
    assert "SCALE = 2" in by_name["norm"]
    assert "def _square" in by_name["norm"]
    assert "json" not in by_name["norm"]
    assert "Counter" not in by_name["norm"]
    assert run(by_name["norm"], "norm", 3) == 6.0


def test_output_order_is_original_and_deterministic():
    source = "import re\nimport math\nA = 1\nB = 2\ndef f(x):\n    return re.escape(str(math.pi + A + B + x))\n"
    first = extract_functions(source).functions[0].source
    second = extract_functions(source).functions[0].source
    assert first == second
    assert first.index("import re") < first.index("import math") < first.index("A = 1")


def test_docstring_is_returned():
    result = extract_functions('def f(x):\n    """Çok güzel."""\n    return x\n')
    assert result.functions[0].docstring == "Çok güzel."


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ("def _private(x):\n    return x\n", NOT_PUBLIC),
        ("def f():\n    return 1\n", NO_PARAMETERS),
        ("async def f(x):\n    return x\n", ASYNC_FUNCTION),
        ("import functools\n@functools.cache\ndef f(x):\n    return x\n", DECORATED),
        ("import numpy as np\ndef f(x):\n    return np.sum(x)\n", EXTERNAL_DEPENDENCY),
        ("from . import sibling\ndef f(x):\n    return sibling.go(x)\n", EXTERNAL_DEPENDENCY),
        ("import os\ndef f(x):\n    return os.getcwd() + x\n", SIDE_EFFECT_DEPENDENCY),
        ("import random\ndef f(x):\n    return random.random() * x\n", SIDE_EFFECT_DEPENDENCY),
        ("def f(x):\n    return open(x).read()\n", UNSAFE_BUILTIN),
        ("def f(x):\n    return input(x)\n", UNSAFE_BUILTIN),
        (
            "COUNT = 0\ndef f(x):\n    global COUNT\n    COUNT += x\n    return COUNT\n",
            GLOBAL_STATEMENT,
        ),
        ("def f(x):\n    return x\ndef f(x):\n    return -x\n", REDEFINED),
        ("class K:\n    pass\ndef f(x):\n    return K()\n", EXTERNAL_DEPENDENCY),
        ("def f(x):\n    return unknown_name(x)\n", EXTERNAL_DEPENDENCY),
        ("def f(x):\n    import os\n    return os.sep + x\n", SIDE_EFFECT_DEPENDENCY),
        ("def f(x):\n    import requests\n    return requests.get(x)\n", EXTERNAL_DEPENDENCY),
        ("def f(x):\n    return x\nf = 3\n", REDEFINED),
    ],
)
def test_rejection_reasons(source, reason):
    assert names(source) == []
    assert rejected(source)[reason] >= 1


def test_mutable_module_constants_are_rejected():
    # liste/sözlük sabitleri çağrılar arasında değiştirilebilir: oracle kararsızlaşır
    source = "TABLE = {1: 2}\ndef f(x):\n    return TABLE[x]\n"
    assert names(source) == []


def test_immutable_constants_including_negative_and_tuple_are_allowed():
    source = "LIMIT = -5\nPAIR = (1, 'a')\ndef f(x):\n    return x < LIMIT or PAIR[0]\n"
    assert names(source) == ["f"]


def test_constant_rebound_later_is_rejected():
    source = "LIMIT = 1\nLIMIT += 1\ndef f(x):\n    return x + LIMIT\n"
    assert names(source) == []


def test_names_bound_inside_blocks_are_not_trusted():
    source = "try:\n    import fastlib\nexcept ImportError:\n    fastlib = None\ndef f(x):\n    return fastlib\n"
    assert names(source) == []


def test_module_level_name_shadowing_a_builtin_is_not_treated_as_builtin():
    source = "max = compute()\ndef f(x):\n    return max(x)\n"
    assert names(source) == []


def test_local_variables_parameters_and_comprehensions_are_not_dependencies():
    source = (
        "def f(items, key=len):\n"
        "    total = 0\n"
        "    for item in items:\n"
        "        total += key(item)\n"
        "    return [x * 2 for x in range(total)] + sorted(items, key=lambda y: -len(y))\n"
    )
    assert names(source) == ["f"]


def test_annotations_and_defaults_are_evaluated_at_definition_time():
    ok = "from typing import List\ndef f(x: List[int], y: int = 3) -> List[int]:\n    return [x, y]\n"
    bad = "def f(x: Missing = None):\n    return x\n"
    assert names(ok) == ["f"]
    assert names(bad) == []


def test_recursion_and_mutual_recursion_are_supported():
    source = (
        "def fact(n):\n    return 1 if n < 2 else n * fact(n - 1)\n"
        "def even(n):\n    return True if n == 0 else odd(n - 1)\n"
        "def odd(n):\n    return False if n == 0 else even(n - 1)\n"
    )
    result = {f.name: f.source for f in extract_functions(source).functions}
    assert set(result) == {"fact", "even", "odd"}
    assert run(result["fact"], "fact", 5) == 120
    assert run(result["even"], "even", 4) is True


def test_function_depending_on_rejected_helper_is_rejected():
    source = "import os\ndef helper(x):\n    return os.sep + x\ndef f(x):\n    return helper(x)\n"
    assert names(source) == []
    assert rejected(source)[SIDE_EFFECT_DEPENDENCY] == 1
    assert rejected(source)[HELPER_REJECTED] == 1


def test_methods_and_nested_definitions_are_not_top_level_units():
    source = "class K:\n    def m(self, x):\n        return x\ndef outer(x):\n    def inner(y):\n        return y\n    return inner(x)\n"
    assert names(source) == ["outer"]


def test_every_unit_compiles_standalone():
    source = "import re\nPAT = 'a+'\ndef f(text):\n    return re.findall(PAT, text)\n"
    unit = extract_functions(source).functions[0].source
    assert run(unit, "f", "caaat") == ["aaa"]


@pytest.mark.parametrize("source", ["def broken(:\n", "x = (\n", "\x00"])
def test_unparseable_source_raises_extraction_error(source):
    with pytest.raises(ExtractionError):
        extract_functions(source)


def test_invalid_escape_sequences_do_not_emit_warnings(recwarn):
    extract_functions('def f(x):\n    return "\\d" + x\n')
    assert not [w for w in recwarn if issubclass(w.category, (SyntaxWarning, DeprecationWarning))]
