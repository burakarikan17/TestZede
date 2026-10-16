import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from dataset_builders import write_parquet

from testzede.datasets.base import NO_ENTRY_POINT, SYNTAX_ERROR
from testzede.datasets.errors import DatasetFormatError, DatasetNotFoundError
from testzede.datasets.humaneval import HumanEvalLoader


def test_humaneval_builds_units_from_prompt_and_solution(data_dir):
    result = HumanEvalLoader(data_dir).load()
    units = {u.uid: u for u in result.units}
    assert set(units) == {"HumanEval/0", "HumanEval/1"}
    inc = units["HumanEval/0"]
    assert inc.entry_point == "inc"
    assert inc.dataset == "humaneval"
    assert "return x + 1" in inc.source
    assert inc.seed_examples == (">>> inc(1)",)
    assert units["HumanEval/1"].seed_examples == ()
    assert result.skipped == ()


def test_humaneval_is_iterable(data_dir):
    assert [u.uid for u in HumanEvalLoader(data_dir)] == ["HumanEval/0", "HumanEval/1"]


def test_humaneval_skips_rows_with_missing_entry_point(tmp_path):
    rows = [
        {"task_id": "HumanEval/7", "prompt": "def a(x):\n", "canonical_solution": "    return x\n"}
        | {"entry_point": "nope"},
        {
            "task_id": "HumanEval/8",
            "prompt": "def b(:\n",
            "canonical_solution": "",
            "entry_point": "b",
        },
    ]
    write_parquet(tmp_path / "raw" / "humaneval" / "test.parquet", rows)
    result = HumanEvalLoader(tmp_path).load()
    assert result.units == ()
    assert [s.reason for s in result.skipped] == [NO_ENTRY_POINT, SYNTAX_ERROR]
    assert result.skip_counts() == {NO_ENTRY_POINT: 1, SYNTAX_ERROR: 1}


def test_missing_file_message_names_the_download_command(tmp_path):
    with pytest.raises(DatasetNotFoundError, match="testzede download --dataset humaneval"):
        HumanEvalLoader(tmp_path).load()


def test_missing_column_is_a_format_error(tmp_path):
    write_parquet(tmp_path / "raw" / "humaneval" / "test.parquet", [{"task_id": "x"}])
    with pytest.raises(DatasetFormatError, match="beklenen sütunlar yok"):
        HumanEvalLoader(tmp_path).load()


def test_corrupted_parquet_is_a_format_error(tmp_path):
    path = tmp_path / "raw" / "humaneval" / "test.parquet"
    path.parent.mkdir(parents=True)
    path.write_bytes("bu bir parquet dosyası değil".encode())
    with pytest.raises(DatasetFormatError, match="okunamadı"):
        HumanEvalLoader(tmp_path).load()


def test_parquet_with_extra_columns_is_fine(tmp_path):
    table = pa.Table.from_pylist(
        [
            {
                "task_id": "HumanEval/0",
                "prompt": "def f(x):\n",
                "canonical_solution": "    return x\n",
                "entry_point": "f",
                "test": "ignored",
            }
        ]
    )
    path = tmp_path / "raw" / "humaneval" / "test.parquet"
    path.parent.mkdir(parents=True)
    pq.write_table(table, path)
    assert len(HumanEvalLoader(tmp_path).load().units) == 1
