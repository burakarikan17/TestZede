import openpyxl
import pytest

from testzede.services import batch_service
from testzede.services.errors import ServiceError


def _write_small67(data_dir):
    folder = data_dir / "raw" / "small67"
    folder.mkdir(parents=True)
    workbook = openpyxl.Workbook()
    workbook.active.append(["def one(x):\n    return x\n"])
    workbook.save(folder / "small.xlsx")


def test_targets_mark_missing_files(tmp_path):
    _write_small67(tmp_path)
    found = {(t.kind, t.name): t for t in batch_service.targets(tmp_path)}
    assert not found[("split", "external")].available
    assert found[("dataset", "small67")].available
    assert not found[("dataset", "humaneval")].available
    assert found[("dataset", "humaneval")].label == "Veri seti: humaneval (bulunamadı)"


def test_run_dataset(tmp_path):
    _write_small67(tmp_path)
    target = batch_service.Target("dataset", "small67", True)
    outcome = batch_service.run(
        target, data_dir=tmp_path, reports_root=tmp_path / "reports", formats=["csv"]
    )
    assert [r.uid for r in outcome.results] == ["small67/1"]
    assert outcome.reports["small67"]


def test_missing_split_is_service_error(tmp_path):
    with pytest.raises(ServiceError, match="make-splits"):
        batch_service.run(batch_service.Target("split", "main", False), data_dir=tmp_path)


def test_requires_a_format(tmp_path):
    with pytest.raises(ServiceError, match="biçimi"):
        batch_service.run(batch_service.Target("dataset", "small67", True), formats=[])


def test_bad_config_is_service_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("- 1\n", encoding="utf-8")
    target = batch_service.Target("dataset", "small67", True)
    with pytest.raises(ServiceError, match="Yapılandırma"):
        batch_service.run(target, data_dir=tmp_path, config_path=bad)
