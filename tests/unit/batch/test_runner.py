from pathlib import Path

import openpyxl
import pytest

from testzede.batch.runner import (
    BatchConfig,
    mutation_stage,
    run_batch,
    run_dataset,
    run_split,
    run_unit,
)
from testzede.config import ConfigError, load_config
from testzede.datasets.hashing import sha256_file
from testzede.datasets.splits import build_splits, write_splits
from testzede.domain.models import CodeUnit, MutationReport, Prediction, RunStats, TestCase
from testzede.execution.executor import SandboxExecutor
from testzede.mutation.engine import MutationRun
from testzede.rl.env import EnvConfig
from testzede.rl.trainer import RLConfig

SIGN = """def sign(x: int) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0
"""

FAST = BatchConfig(rl=RLConfig(env=EnvConfig(max_steps=6, patience=4)), suite_timeout_s=30)


def _unit(uid="demo/sign", source=SIGN, entry_point="sign", dataset="demo"):
    return CodeUnit(uid, source, entry_point=entry_point, dataset=dataset)


@pytest.fixture(scope="module")
def executor():
    return SandboxExecutor()


def _write_small67(data_dir: Path, sources: list[str]) -> None:
    folder = data_dir / "raw" / "small67"
    folder.mkdir(parents=True)
    workbook = openpyxl.Workbook()
    for source in sources:
        workbook.active.append([source])
    workbook.save(folder / "small.xlsx")


def test_run_unit_fills_every_stage(executor):
    result = run_unit(_unit(), executor, FAST, seed=1)
    assert result.error is None
    assert result.metrics is not None and result.metrics.values["Çevrimsel Karmaşıklık"] == 3
    assert result.test_count > 0
    assert result.coverage is not None and result.coverage.covered_lines > 0
    assert "sign" in result.coverage.per_function  # tam paket coverage_runner'dan ölçüldü
    assert result.stats.generated >= result.test_count
    assert result.stats.execution_time_s > 0


def test_syntax_error_is_reported_not_raised(executor):
    result = run_unit(_unit(source="def sign(:\n"), executor, FAST)
    assert result.error.startswith("Metrik:")
    assert result.test_count == 0 and result.coverage is None


def test_missing_entry_point_is_reported(executor):
    result = run_unit(_unit(entry_point="nope"), executor, FAST)
    assert result.error.startswith("RL:")
    assert result.metrics is not None


def test_mutation_and_prediction_hooks(executor):
    seen = {}

    def mutation(unit, tests):
        seen["tests"] = len(tests)
        return MutationReport(total=4, killed=3, survived=1, timeout=0)

    def prediction(unit, metrics, episode):
        return Prediction(metrics.values["Halstead Hacim"] / 3000, len(episode.tests), "test")

    config = BatchConfig(rl=FAST.rl, mutation=mutation, prediction=prediction)
    result = run_unit(_unit(), executor, config, seed=1)
    assert seen["tests"] == result.test_count
    assert result.mutation.score == 0.75
    assert result.prediction.optimum_test_count == result.test_count


def test_failing_hook_keeps_earlier_results(executor):
    def mutation(unit, tests):
        raise RuntimeError("motor çöktü")

    result = run_unit(_unit(), executor, BatchConfig(rl=FAST.rl, mutation=mutation), seed=1)
    assert result.error == "Mutasyon: motor çöktü"
    assert result.coverage is not None and result.mutation is None


def test_mutation_stage_returns_report_of_detailed_run():
    calls = []
    report = MutationReport(total=4, killed=3, survived=1, timeout=0)

    class FakeEngine:
        def run_detailed(self, source, tests):
            calls.append((source, tests))
            return MutationRun(report=report, stats=RunStats(1, 1, 0.1), survivors=[])

    tests = (TestCase("test_a", "def test_a():\n    assert sign(1) == 1", "rl"),)
    assert mutation_stage(FakeEngine())(_unit(), tests) is report
    assert calls == [(SIGN, list(tests))]


def test_mutation_stage_counts_uncovered_mutants_as_survived():
    source = "def f(a):\n    if a > 0:\n        return 1\n    return 2\n"
    tests = [TestCase("test_one", "def test_one():\n    assert f(1) == 1", "rl")]
    report = mutation_stage()(_unit(source=source, entry_point="f"), tests)
    # 5 mutant: 3'ü öldü; ROR (satır 2) ve kapsanmayan satır 4'teki RETURN_NONE hayatta kaldı.
    assert (report.total, report.killed, report.survived) == (5, 3, 2)


def test_config_mutation_switch():
    assert BatchConfig.from_mapping({}).mutation is None
    assert BatchConfig.from_mapping({"batch": {"mutation": False}}).mutation is None
    assert callable(BatchConfig.from_mapping({"batch": {"mutation": True}}).mutation)
    assert callable(BatchConfig.from_mapping(load_config(Path("configs/default.yaml"))).mutation)


def test_run_batch_reports_progress_and_stops(executor):
    units = [_unit(f"demo/{i}") for i in range(3)]
    calls = []
    results, stopped = run_batch(
        units,
        executor,
        FAST,
        progress=lambda done, total, r: calls.append((done, total, r.uid)),
        should_stop=lambda: len(calls) >= 2,
    )
    assert stopped
    assert [r.uid for r in results] == ["demo/0", "demo/1"]
    assert calls == [(1, 3, "demo/0"), (2, 3, "demo/1")]


def test_run_dataset_writes_report_with_errors_listed(executor, tmp_path):
    data_dir = tmp_path / "data"
    _write_small67(data_dir, [SIGN, "def one(x):\n    return x\n"])
    outcome = run_dataset(
        "small67",
        executor,
        FAST,
        data_dir=data_dir,
        reports_root=tmp_path / "reports",
        config_name="configs/test.yaml",
        limit=1,
        formats=["csv"],
    )
    assert [r.uid for r in outcome.results] == ["small67/1"]
    paths = outcome.reports["small67"]
    assert {p.name for p in paths} == {"results.csv", "summary.csv", "meta.csv"}
    assert "configs/test.yaml" in (paths[0].parent / "meta.csv").read_text(encoding="utf-8-sig")


def test_run_split_records_split_hash(executor, tmp_path):
    data_dir = tmp_path / "data"
    _write_small67(data_dir, [SIGN])
    write_splits(build_splits(data_dir, allow_missing=True), data_dir)
    outcome = run_split(
        "external",
        executor,
        FAST,
        data_dir=data_dir,
        reports_root=tmp_path / "reports",
        formats=["csv"],
    )
    assert [r.uid for r in outcome.results] == ["small67/1"]
    meta = (outcome.reports["small67"][0].parent / "meta.csv").read_text(encoding="utf-8-sig")
    assert "Split,external" in meta
    assert sha256_file(data_dir / "splits" / "external.json") in meta


def test_config_from_default_yaml():
    config = BatchConfig.from_mapping(load_config(Path("configs/default.yaml")))
    assert config.seed == 0 and config.share_agent
    assert config.rl.env.max_steps == 50


def test_config_rejects_unknown_batch_key():
    with pytest.raises(ValueError, match="paralel"):
        BatchConfig.from_mapping({"batch": {"paralel": 4}})


def test_load_config_errors(tmp_path):
    with pytest.raises(ConfigError, match="okunamadı"):
        load_config(tmp_path / "yok.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("reward: [1,\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="bozuk"):
        load_config(bad)
    listing = tmp_path / "list.yaml"
    listing.write_text("- 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="eşleme"):
        load_config(listing)
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    assert load_config(empty) == {}


ROTATIONS = '''def rotations(s, dir=1):
    """
    >>> list(rotations([1, 2, 3]))
    [[1, 2, 3], [2, 3, 1], [3, 1, 2]]
    """
    seq = list(s)
    for i in range(len(seq)):
        yield seq
        seq = seq[dir:] + seq[:dir]
'''


def test_generator_unit_body_is_covered(executor):
    unit = _unit("demo/rot", ROTATIONS, "rotations")
    result = run_unit(unit, executor, FAST, seed=1)
    assert result.error is None and result.test_count > 0
    assert result.coverage.line_rate == 1.0
    assert result.coverage.covered_branches == result.coverage.total_branches


def test_frozen_config_is_valid_and_preferred():
    from testzede.config import default_config_path

    assert default_config_path() == Path("configs/frozen.yaml")
    config = BatchConfig.from_mapping(load_config(Path("configs/frozen.yaml")))
    assert config.rl.episodes == 3 and config.rl.env.patience == 20


def test_prediction_stage_is_wired_only_when_enabled():
    assert BatchConfig.from_mapping({}).prediction is None
    assert BatchConfig.from_mapping({"batch": {"prediction": False}}).prediction is None
    assert callable(BatchConfig.from_mapping({"batch": {"prediction": True}}).prediction)
