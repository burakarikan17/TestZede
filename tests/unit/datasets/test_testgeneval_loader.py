from dataset_builders import tge_row, write_parquet

from testzede.datasets.base import (
    EMPTY_SOURCE,
    NO_ELIGIBLE_FUNCTION,
    SYNTAX_ERROR,
)
from testzede.datasets.small67 import Small67Loader
from testzede.datasets.testgeneval import (
    TestGenEvalLiteLoader,
    TestGenEvalLoader,
    uid_instance_id,
    unit_uid,
)


def test_testgeneval_units_are_function_level(tmp_path):
    src = "import math\ndef root(x):\n    return math.sqrt(x)\n\ndef _hidden(x):\n    return x\n"
    write_parquet(
        tmp_path / "raw" / "testgeneval" / "test.parquet", [tge_row("a-1", src, "p/m.py")]
    )
    result = TestGenEvalLoader(tmp_path).load()
    assert [u.uid for u in result.units] == ["a-1::p/m.py::root"]
    unit = result.units[0]
    assert unit.dataset == "testgeneval"
    assert unit.entry_point == "root"
    assert "import math" in unit.source
    assert result.stats["rejected.not_public"] == 1
    assert result.stats["rows"] == 1


def test_testgeneval_reports_skipped_rows_with_reasons(tmp_path):
    rows = [
        tge_row("a-1", "", "p/empty.py"),
        tge_row("a-2", "def broken(:\n", "p/bad.py"),
        tge_row("a-3", "import numpy\ndef f(x):\n    return numpy.sum(x)\n", "p/ext.py"),
    ]
    write_parquet(tmp_path / "raw" / "testgeneval" / "test.parquet", rows)
    result = TestGenEvalLoader(tmp_path).load()
    assert result.units == ()
    assert result.skip_counts() == {
        EMPTY_SOURCE: 1,
        SYNTAX_ERROR: 1,
        NO_ELIGIBLE_FUNCTION: 1,
    }


def test_lite_reads_test_and_dev(data_dir):
    result = TestGenEvalLiteLoader(data_dir).load()
    assert sorted(u.uid for u in result.units) == [
        "org__repo-1::pkg/a.py::add",
        "org__repo-2::pkg/b.py::mul",
    ]
    assert result.skip_counts() == {NO_ELIGIBLE_FUNCTION: 1}  # dev: yalnızca sabit
    assert {u.dataset for u in result.units} == {"testgeneval-lite"}


def test_exclusions_by_instance_and_by_file(data_dir):
    loader = TestGenEvalLoader(
        data_dir,
        exclude_instance_ids=frozenset({"org__repo-1"}),
        exclude_files=frozenset({("org/repo", "pkg/b.py")}),
    )
    result = loader.load()
    assert sorted(u.uid for u in result.units) == [
        "org__repo-3::pkg/c.py::add",
        "org__repo-5::pkg/d.py::neg",
        "org__repo-6::pkg/e.py::sub",
    ]
    assert result.stats["rows_excluded_instance"] == 1
    assert result.stats["rows_excluded_file"] == 1


def test_row_keys_ignore_exclusions_and_need_no_extraction(data_dir):
    loader = TestGenEvalLoader(data_dir, exclude_instance_ids=frozenset({"org__repo-1"}))
    keys = loader.row_keys()
    assert [k.instance_id for k in keys][:2] == ["org__repo-1", "org__repo-3"]
    assert keys[0].repo == "org/repo"
    assert keys[0].code_file == "pkg/a.py"


def test_source_files_are_reported(data_dir):
    names = [p.name for p in TestGenEvalLiteLoader(data_dir).source_files()]
    assert names == ["test.parquet", "dev.parquet"]
    assert [p.name for p in Small67Loader(data_dir).source_files()] == ["small.xlsx"]


def test_uid_helpers_roundtrip():
    uid = unit_uid("django__django-1", "django/utils/text.py", "slugify")
    assert uid == "django__django-1::django/utils/text.py::slugify"
    assert uid_instance_id(uid) == "django__django-1"


def test_seed_examples_come_from_the_extracted_function(tmp_path):
    src = 'def inc(x):\n    """\n    >>> inc(4)\n    5\n    """\n    return x + 1\n'
    write_parquet(tmp_path / "raw" / "testgeneval" / "test.parquet", [tge_row("a-1", src)])
    assert TestGenEvalLoader(tmp_path).load().units[0].seed_examples == (">>> inc(4)",)
