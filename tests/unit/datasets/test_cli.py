import json

import pytest
from dataset_builders import build_data_dir

from testzede import cli


def test_download_all_delegates_and_reminds_about_small67(monkeypatch, tmp_path, capsys):
    calls = []

    def fake(name, data_dir, *, force, progress):
        calls.append((name, data_dir, force))
        return [data_dir / "raw" / name / "test.parquet"]

    monkeypatch.setattr(cli, "download_dataset", fake)
    code = cli.main(["download", "--dataset", "all", "--data-dir", str(tmp_path), "--force"])
    out = capsys.readouterr().out
    assert code == 0
    assert [c[0] for c in calls] == list(cli.downloadable_datasets())
    assert all(c[2] for c in calls)
    assert "small67" in out


def test_download_single_dataset(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        cli, "download_dataset", lambda name, data_dir, **_: [data_dir / "x.parquet"]
    )
    assert cli.main(["download", "--dataset", "humaneval", "--data-dir", str(tmp_path)]) == 0
    assert "humaneval: hazır" in capsys.readouterr().out


def test_progress_printer_is_throttled(capsys):
    show = cli._progress_printer()
    for received in range(0, 101, 1):
        show("f.parquet", received, 100)
    show("f.parquet", 5, None)  # toplam bilinmiyorsa sessiz
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 11  # %0, %10 … %100


def test_user_errors_become_a_message_and_exit_code_1(tmp_path, capsys):
    code = cli.main(["make-splits", "--data-dir", str(tmp_path)])
    err = capsys.readouterr().err
    assert code == 1
    assert err.startswith("Hata:")
    assert "Traceback" not in err


def test_make_splits_writes_files_and_prints_hashes(tmp_path, capsys):
    data_dir = build_data_dir(tmp_path / "data")
    assert cli.main(["make-splits", "--data-dir", str(data_dir)]) == 0
    out = capsys.readouterr().out
    for name in ("development", "main", "external"):
        assert (data_dir / "splits" / f"{name}.json").is_file()
        assert f"{name}:" in out
    assert "SHA-256" in out


def test_make_splits_strict_files_flag(tmp_path):
    data_dir = build_data_dir(tmp_path / "data")
    assert cli.main(["make-splits", "--strict-files", "--data-dir", str(data_dir)]) == 0
    main = json.loads((data_dir / "splits" / "main.json").read_text(encoding="utf-8"))
    assert main["strict_files"] is True


def test_make_splits_allow_missing_warns(tmp_path, capsys):
    data_dir = build_data_dir(tmp_path / "data")
    for path in (data_dir / "raw" / "small67").iterdir():
        path.unlink()
    assert cli.main(["make-splits", "--allow-missing", "--data-dir", str(data_dir)]) == 0
    assert "small67" in capsys.readouterr().err


def test_unknown_command_is_an_argparse_error():
    with pytest.raises(SystemExit) as raised:
        cli.main(["nope"])
    assert raised.value.code == 2


def test_dataset_choice_is_validated():
    with pytest.raises(SystemExit):
        cli.main(["download", "--dataset", "yok"])


def test_missing_dataset_warnings_are_sorted(tmp_path, capsys):
    data_dir = build_data_dir(tmp_path / "data")
    for name in ("small67", "humaneval"):
        for path in (data_dir / "raw" / name).iterdir():
            path.unlink()
    assert cli.main(["make-splits", "--allow-missing", "--data-dir", str(data_dir)]) == 0
    warnings = capsys.readouterr().err.splitlines()
    assert [line.split("'")[1] for line in warnings] == ["humaneval", "small67"]
