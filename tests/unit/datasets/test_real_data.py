"""Gerçek veri setleriyle doğrulama.

``data/raw/`` altında ilgili veri yoksa testler atlanır (CI ağa çıkmaz). Yerelde
``testzede download --dataset all`` ve Small67 dosyasını yerleştirdikten sonra çalışır.
"""

from pathlib import Path

import pytest

from testzede.datasets.factory import DatasetFactory
from testzede.datasets.splits import build_splits, verify_no_leakage
from testzede.datasets.testgeneval import uid_instance_id

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def needs(*names: str):
    missing = [n for n in names if not (DATA_DIR / "raw" / n).is_dir()]
    return pytest.mark.skipif(bool(missing), reason=f"gerçek veri yok: {', '.join(missing)}")


def define(source: str, name: str) -> object:
    namespace: dict = {}
    exec(compile(source, "<unit>", "exec"), namespace)  # noqa: S102 - birimi tanımlar, çağırmaz
    return namespace[name]


@needs("humaneval")
def test_humaneval_has_164_valid_units():
    result = DatasetFactory.get("humaneval", DATA_DIR).load()
    assert len(result.units) == 164
    assert not result.skipped
    assert all(callable(define(u.source, u.entry_point)) for u in result.units)
    assert sum(bool(u.seed_examples) for u in result.units) >= 70  # >>> içeren docstring'ler


@needs("small67")
def test_small67_has_66_valid_units_and_one_reported_broken_row():
    result = DatasetFactory.get("small67", DATA_DIR).load()
    assert len(result.units) == 66
    assert [s.uid for s in result.skipped] == ["small67/50"]
    assert all(callable(define(u.source, u.entry_point)) for u in result.units)


@needs("testgeneval-lite")
def test_lite_units_are_standalone_functions():
    result = DatasetFactory.get("testgeneval-lite", DATA_DIR).load()
    assert len(result.units) > 100
    assert all(callable(define(u.source, u.entry_point)) for u in result.units)


@needs("testgeneval-lite", "testgeneval", "humaneval", "small67")
def test_real_splits_have_no_leakage():
    splits = build_splits(DATA_DIR)
    development, main = splits["development"], splits["main"]
    verify_no_leakage(development, main)
    dev_instances = {uid_instance_id(u) for u in development.units["testgeneval-lite"]}
    main_instances = {uid_instance_id(u) for u in main.units["testgeneval"]}
    assert not dev_instances & main_instances
    assert main.stats["leakage"]["rows_removed_same_instance"] == 160
    assert main.unit_count > 100
