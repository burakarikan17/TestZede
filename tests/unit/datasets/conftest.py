from pathlib import Path

import pytest
from dataset_builders import build_data_dir


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Dört veri setinin de bulunduğu küçük bir ``data/`` klasörü."""
    return build_data_dir(tmp_path / "data")
