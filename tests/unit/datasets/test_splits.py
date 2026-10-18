import json
import shutil

import pytest
from dataset_builders import write_parquet

from testzede.datasets.errors import DatasetNotFoundError, IntegrityError, SplitError
from testzede.datasets.hashing import sha256_file
from testzede.datasets.splits import (
    EXTRACTOR_VERSION,
    SplitDefinition,
    build_splits,
    load_split_units,
    read_split,
    split_path,
    verify_no_leakage,
    write_splits,
)
from testzede.datasets.testgeneval import uid_instance_id

DEV = {"org__repo-1::pkg/a.py::add", "org__repo-2::pkg/b.py::mul"}


def uids(split: SplitDefinition, dataset: str) -> set[str]:
    return set(split.units[dataset])


def test_development_is_lite(data_dir):
    splits = build_splits(data_dir)
    assert uids(splits["development"], "testgeneval-lite") == DEV


def test_main_removes_lite_instances_and_identical_units(data_dir):
    main = build_splits(data_dir)["main"]
    # i1: Lite örneği (instance), i3: Lite'taki add ile birebir aynı kaynak, i5: i4'ün kopyası
    assert uids(main, "testgeneval") == {
        "org__repo-4::pkg/b.py::neg",
        "org__repo-6::pkg/e.py::sub",
    }
    stats = main.stats
    assert stats["deduplication"] == {
        "identical_units_removed": 1,
        "identical_to_development_removed": 1,
    }
    assert stats["leakage"]["rows_removed_same_instance"] == 1
    assert stats["leakage"]["files_shared_with_lite"] == 1  # pkg/b.py
    assert stats["leakage"]["rows_removed_strict_files"] == 0


def test_strict_files_also_removes_files_shared_with_lite(data_dir):
    main = build_splits(data_dir, strict_files=True)["main"]
    # i4, Lite'ın pkg/b.py dosyasında; artık i5 (kopya, pkg/d.py) kalır
    assert uids(main, "testgeneval") == {
        "org__repo-5::pkg/d.py::neg",
        "org__repo-6::pkg/e.py::sub",
    }
    assert main.strict_files is True
    assert main.stats["leakage"]["rows_removed_strict_files"] == 1


def test_no_leakage_between_development_and_main(data_dir):
    splits = build_splits(data_dir)
    dev_instances = {uid_instance_id(u) for u in splits["development"].units["testgeneval-lite"]}
    main_instances = {uid_instance_id(u) for u in splits["main"].units["testgeneval"]}
    assert not dev_instances & main_instances
    verify_no_leakage(splits["development"], splits["main"])


def test_verify_no_leakage_detects_shared_instances(data_dir):
    splits = build_splits(data_dir)
    leaky = SplitDefinition(
        "main", {"testgeneval": ("org__repo-1::pkg/other.py::f",)}, {}, stats={}
    )
    with pytest.raises(SplitError, match="Data leakage"):
        verify_no_leakage(splits["development"], leaky)


def test_external_has_humaneval_and_valid_small67_units(data_dir):
    external = build_splits(data_dir)["external"]
    assert uids(external, "humaneval") == {"HumanEval/0", "HumanEval/1"}
    assert uids(external, "small67") == {"small67/1"}
    assert external.stats["small67"]["skipped.syntax_error"] == 1


def test_splits_record_raw_file_hashes(data_dir):
    main = build_splits(data_dir)["main"]
    raw = data_dir / "raw" / "testgeneval" / "test.parquet"
    assert main.sources == {"testgeneval/test.parquet": sha256_file(raw)}


def test_missing_dataset_is_an_error_by_default(data_dir):
    shutil.rmtree(data_dir / "raw" / "small67")
    with pytest.raises(SplitError, match="small67"):
        build_splits(data_dir)


def test_allow_missing_skips_and_records_the_gap(data_dir):
    shutil.rmtree(data_dir / "raw" / "small67")
    splits = build_splits(data_dir, allow_missing=True)
    assert set(splits["external"].units) == {"humaneval"}
    assert splits["external"].missing_datasets == ("small67",)


def test_missing_lite_makes_main_impossible_but_not_external(data_dir):
    shutil.rmtree(data_dir / "raw" / "testgeneval-lite")
    splits = build_splits(data_dir, allow_missing=True)
    assert set(splits) == {"external"}
    assert splits["external"].missing_datasets == ("testgeneval-lite",)


def test_json_is_deterministic_and_roundtrips(data_dir):
    first = build_splits(data_dir)
    second = build_splits(data_dir)
    for name in first:
        assert first[name].to_json() == second[name].to_json()
        assert SplitDefinition.from_json(first[name].to_json()) == first[name]
    assert "created" not in first["main"].to_json()  # zaman damgası yok


def test_write_and_read_back(data_dir):
    splits = build_splits(data_dir)
    paths = write_splits(splits, data_dir)
    assert {p.name for p in paths} == {"development.json", "main.json", "external.json"}
    assert read_split(split_path(data_dir, "main")) == splits["main"]
    assert json.loads(split_path(data_dir, "main").read_text(encoding="utf-8"))["leakage_key"] == (
        "instance_id"
    )


def test_identical_data_yields_identical_files(data_dir):
    first = write_splits(build_splits(data_dir), data_dir)
    hashes = {p.name: sha256_file(p) for p in first}
    again = write_splits(build_splits(data_dir), data_dir)
    assert {p.name: sha256_file(p) for p in again} == hashes


def test_load_split_units_returns_code_units_in_split_order(data_dir):
    splits = build_splits(data_dir)
    units = load_split_units(splits["external"], data_dir)
    assert [u.uid for u in units] == ["HumanEval/0", "HumanEval/1", "small67/1"]
    main_units = load_split_units(splits["main"], data_dir)
    assert [u.entry_point for u in main_units] == ["neg", "sub"]


def test_load_split_units_detects_changed_raw_data(data_dir):
    splits = build_splits(data_dir)
    write_parquet(
        data_dir / "raw" / "humaneval" / "test.parquet",
        [
            {
                "task_id": "HumanEval/0",
                "prompt": "def inc(x):\n",
                "canonical_solution": "    return x\n",
                "entry_point": "inc",
            }
        ],
    )
    with pytest.raises(IntegrityError, match="make-splits"):
        load_split_units(splits["external"], data_dir)


def test_load_split_units_needs_the_raw_files(data_dir):
    splits = build_splits(data_dir)
    (data_dir / "raw" / "humaneval" / "test.parquet").unlink()
    with pytest.raises(DatasetNotFoundError):
        load_split_units(splits["external"], data_dir)


def test_load_split_units_reports_units_that_vanished(data_dir):
    splits = build_splits(data_dir)
    stale = SplitDefinition(
        "main", {"humaneval": ("HumanEval/99",)}, splits["external"].sources, stats={}
    )
    with pytest.raises(SplitError, match="HumanEval/99"):
        load_split_units(stale, data_dir)


def test_read_split_errors_are_split_errors(tmp_path):
    with pytest.raises(SplitError, match="make-splits"):
        read_split(tmp_path / "yok.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{ bozuk", encoding="utf-8")
    with pytest.raises(SplitError, match="bozuk"):
        read_split(broken)
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"schema_version": 0}), encoding="utf-8")
    with pytest.raises(SplitError, match="şema"):
        read_split(old)


def test_write_splits_to_an_unwritable_place_is_a_split_error(tmp_path, data_dir):
    splits = build_splits(data_dir)
    blocker = tmp_path / "engel"
    blocker.write_text("dosya", encoding="utf-8")
    with pytest.raises(SplitError, match="yazılamadı"):
        write_splits(splits, blocker)


def test_split_records_the_extractor_version(data_dir):
    split = build_splits(data_dir)["main"]
    assert split.extractor_version == EXTRACTOR_VERSION
    assert json.loads(split.to_json())["extractor_version"] == EXTRACTOR_VERSION


def test_split_made_with_older_extraction_rules_is_refused(data_dir):
    split = build_splits(data_dir)["external"]
    stale = SplitDefinition.from_json(
        split.to_json().replace(
            f'"extractor_version": {EXTRACTOR_VERSION}', '"extractor_version": 1'
        )
    )
    assert stale.extractor_version == 1
    with pytest.raises(SplitError, match="eski çıkarma kuralları"):
        load_split_units(stale, data_dir)
