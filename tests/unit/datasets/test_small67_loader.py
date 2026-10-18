import pytest
from dataset_builders import write_xlsx

from testzede.datasets.base import SYNTAX_ERROR
from testzede.datasets.errors import DatasetFormatError, DatasetNotFoundError
from testzede.datasets.small67 import Small67Loader


def test_small67_uses_row_numbers_and_reports_bad_rows(data_dir):
    result = Small67Loader(data_dir).load()
    assert [u.uid for u in result.units] == ["small67/1"]
    assert result.units[0].entry_point == "one"
    assert [(s.uid, s.reason) for s in result.skipped] == [("small67/2", SYNTAX_ERROR)]


def test_small67_skips_blank_rows_but_keeps_numbering(tmp_path):
    cells = ["def a(x):\n    return x\n", None, "   ", "def b(x):\n    return x\n"]
    write_xlsx(tmp_path / "raw" / "small67" / "set.xlsx", cells)
    result = Small67Loader(tmp_path).load()
    assert [u.uid for u in result.units] == ["small67/1", "small67/4"]
    assert result.skipped == ()


def test_small67_normalizes_windows_line_endings(tmp_path):
    write_xlsx(tmp_path / "raw" / "small67" / "set.xlsx", ["def a(x):\r\n    return x\r\n"])
    assert "\r" not in Small67Loader(tmp_path).load().units[0].source


def test_small67_extracts_seed_examples(tmp_path):
    source = 'def a(x):\n    """\n    >>> a(2)\n    2\n    """\n    return x\n'
    write_xlsx(tmp_path / "raw" / "small67" / "set.xlsx", [source])
    assert Small67Loader(tmp_path).load().units[0].seed_examples == (">>> a(2)",)


def test_small67_without_a_workbook_explains_where_to_put_it(tmp_path):
    with pytest.raises(DatasetNotFoundError, match="small67"):
        Small67Loader(tmp_path).load()


def test_small67_rejects_ambiguous_folder(tmp_path):
    for name in ("a.xlsx", "b.xlsx"):
        write_xlsx(tmp_path / "raw" / "small67" / name, ["def a(x):\n    return x\n"])
    with pytest.raises(DatasetFormatError, match="tek .xlsx"):
        Small67Loader(tmp_path).load()


def test_small67_ignores_excel_lock_files(tmp_path):
    folder = tmp_path / "raw" / "small67"
    write_xlsx(folder / "set.xlsx", ["def a(x):\n    return x\n"])
    (folder / "~$set.xlsx").write_bytes(b"kilit")
    assert len(Small67Loader(tmp_path).load().units) == 1


def test_small67_corrupted_workbook_is_a_format_error(tmp_path):
    folder = tmp_path / "raw" / "small67"
    folder.mkdir(parents=True)
    (folder / "set.xlsx").write_bytes(b"bozuk")
    with pytest.raises(DatasetFormatError):
        Small67Loader(tmp_path).load()
