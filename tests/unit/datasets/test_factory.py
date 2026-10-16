import pytest

from testzede.datasets.base import DatasetLoader, LoadResult
from testzede.datasets.errors import DatasetError
from testzede.datasets.factory import DatasetFactory
from testzede.datasets.humaneval import HumanEvalLoader


def test_known_names():
    assert set(DatasetFactory.names()) >= {
        "humaneval",
        "small67",
        "testgeneval",
        "testgeneval-lite",
    }


def test_get_returns_a_configured_loader(tmp_path):
    loader = DatasetFactory.get("humaneval", tmp_path)
    assert isinstance(loader, HumanEvalLoader)
    assert loader.data_dir == tmp_path
    assert loader.raw_dir == tmp_path / "raw" / "humaneval"


def test_unknown_name_lists_options():
    with pytest.raises(DatasetError, match="humaneval"):
        DatasetFactory.get("yok")


def test_register_adds_a_new_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(DatasetFactory, "_loaders", dict(DatasetFactory._loaders))

    @DatasetFactory.register
    class Demo(DatasetLoader):
        name = "demo"

        def load(self) -> LoadResult:
            return LoadResult(self.name, ())

        def source_files(self):
            return []

    assert isinstance(DatasetFactory.get("demo", tmp_path), Demo)
    assert "demo" in DatasetFactory.names()
