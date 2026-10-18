import pytest

from testzede import cli
from testzede.batch.report import UnitResult
from testzede.batch.runner import BatchOutcome


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "test.yaml"
    path.write_text("agent:\n  max_steps: 3\nbatch:\n  seed: 7\n", encoding="utf-8")
    return path


def test_batch_dataset_passes_options(monkeypatch, tmp_path, config, capsys):
    seen = {}

    def fake(dataset, executor, batch_config, **kwargs):
        seen.update(dataset=dataset, config=batch_config, **kwargs)
        results = [
            UnitResult("small67/1", "small67"),
            UnitResult("small67/2", "small67", error="x"),
        ]
        return BatchOutcome(results, {"small67": [tmp_path / "r" / "results.csv"]})

    monkeypatch.setattr(cli, "run_dataset", fake)
    argv = ["batch", "--dataset", "small67", "--limit", "2", "--config", str(config)]
    assert cli.main([*argv, "--formats", "csv", "--data-dir", str(tmp_path)]) == 0
    assert seen["dataset"] == "small67" and seen["limit"] == 2
    assert seen["formats"] == ["csv"]
    assert seen["config"].seed == 7 and seen["config"].rl.env.max_steps == 3
    assert "2 birim çalıştırıldı, 1 hatalı." in capsys.readouterr().out


def test_batch_split_with_only(monkeypatch, tmp_path, config):
    seen = {}

    def fake(split, executor, batch_config, **kwargs):
        seen.update(split=split, **kwargs)
        return BatchOutcome([])

    monkeypatch.setattr(cli, "run_split", fake)
    argv = ["batch", "--split", "external", "--only", "humaneval,small67", "--config", str(config)]
    assert cli.main(argv) == 0
    assert seen["split"] == "external" and seen["datasets"] == ["humaneval", "small67"]


def test_batch_bad_config_is_user_error(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("batch:\n  paralel: 4\n", encoding="utf-8")
    assert cli.main(["batch", "--dataset", "small67", "--config", str(bad)]) == 1
    assert "Hata:" in capsys.readouterr().err


def test_batch_missing_split_is_user_error(tmp_path, config, capsys):
    argv = ["batch", "--split", "main", "--config", str(config), "--data-dir", str(tmp_path)]
    assert cli.main(argv) == 1
    assert "make-splits" in capsys.readouterr().err


def test_batch_requires_target():
    with pytest.raises(SystemExit):
        cli.main(["batch"])
