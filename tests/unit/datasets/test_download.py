import hashlib
import re
from pathlib import Path

import pytest

from testzede.datasets import download
from testzede.datasets.download import download_dataset, downloadable_datasets
from testzede.datasets.errors import DatasetError, DownloadError, IntegrityError
from testzede.datasets.sources import SOURCES, RemoteFile

PAYLOAD = b"parquet-benzeri-icerik" * 1000
REVISION = "a" * 40


@pytest.fixture
def server(tmp_path, monkeypatch) -> tuple[str, Path]:
    """``file://`` tabanlı sahte Hugging Face; ``(base_url, uzak dosya yolu)`` döndürür."""
    remote_root = tmp_path / "remote"
    remote_path = (
        remote_root / "datasets" / "org" / "demo" / "resolve" / REVISION / "data" / "x.parquet"
    )
    remote_path.parent.mkdir(parents=True)
    remote_path.write_bytes(PAYLOAD)
    remote = RemoteFile(
        "org/demo", REVISION, "data/x.parquet", "x.parquet", hashlib.sha256(PAYLOAD).hexdigest()
    )
    monkeypatch.setitem(download.SOURCES, "demo", (remote,))
    return remote_root.as_uri(), remote_path


def test_downloads_and_verifies(server, tmp_path):
    base_url, _ = server
    data_dir = tmp_path / "data"
    paths = download_dataset("demo", data_dir, base_url=base_url)
    assert paths == [data_dir / "raw" / "demo" / "x.parquet"]
    assert paths[0].read_bytes() == PAYLOAD
    assert not list(paths[0].parent.glob("*.part"))


def test_progress_callback_receives_sizes(server, tmp_path):
    base_url, _ = server
    calls: list[tuple[str, int, int | None]] = []
    download_dataset("demo", tmp_path, base_url=base_url, progress=lambda *args: calls.append(args))
    assert calls[-1] == ("x.parquet", len(PAYLOAD), len(PAYLOAD))


def test_valid_existing_file_is_not_downloaded_again(server, tmp_path):
    base_url, remote_path = server
    download_dataset("demo", tmp_path, base_url=base_url)
    remote_path.unlink()  # uzak kaynak kaybolsa da yerel dosya yeterli
    assert download_dataset("demo", tmp_path, base_url=base_url)


def test_force_downloads_again(server, tmp_path):
    base_url, remote_path = server
    download_dataset("demo", tmp_path, base_url=base_url)
    remote_path.unlink()
    with pytest.raises(DownloadError):
        download_dataset("demo", tmp_path, base_url=base_url, force=True)


def test_corrupted_local_file_is_replaced(server, tmp_path):
    base_url, _ = server
    (path,) = download_dataset("demo", tmp_path, base_url=base_url)
    path.write_bytes(b"bozuk")
    download_dataset("demo", tmp_path, base_url=base_url)
    assert path.read_bytes() == PAYLOAD


def test_checksum_mismatch_raises_and_leaves_no_file(server, tmp_path):
    base_url, remote_path = server
    remote_path.write_bytes(b"degistirilmis")
    with pytest.raises(IntegrityError, match="SHA-256"):
        download_dataset("demo", tmp_path, base_url=base_url)
    folder = tmp_path / "raw" / "demo"
    assert not list(folder.iterdir())


def test_interrupt_leaves_no_partial_file(server, tmp_path):
    base_url, _ = server

    def interrupt(*_args):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        download_dataset("demo", tmp_path, base_url=base_url, progress=interrupt)
    assert not list((tmp_path / "raw" / "demo").iterdir())


def test_network_failure_is_a_download_error(tmp_path, monkeypatch):
    remote = RemoteFile("org/none", REVISION, "data/x.parquet", "x.parquet", "0" * 64)
    monkeypatch.setitem(download.SOURCES, "demo", (remote,))
    base_url = (tmp_path / "bos").as_uri()
    with pytest.raises(DownloadError, match="İndirilemedi"):
        download_dataset("demo", tmp_path, base_url=base_url)
    assert not list((tmp_path / "raw" / "demo").glob("*.part"))


def test_malformed_base_url_is_a_download_error(tmp_path, monkeypatch):
    remote = RemoteFile("org/none", REVISION, "data/x.parquet", "x.parquet", "0" * 64)
    monkeypatch.setitem(download.SOURCES, "demo", (remote,))
    with pytest.raises(DownloadError):
        download_dataset("demo", tmp_path, base_url="geçersiz")


def test_unknown_dataset_lists_options(tmp_path):
    with pytest.raises(DatasetError, match="humaneval"):
        download_dataset("yok", tmp_path)


def test_unwritable_target_is_a_download_error(tmp_path):
    blocker = tmp_path / "data"
    blocker.write_text("dosya", encoding="utf-8")  # klasör yerine dosya
    with pytest.raises(DownloadError, match="Klasör oluşturulamadı"):
        download_dataset("humaneval", blocker)


def test_registry_is_pinned_and_complete():
    assert set(downloadable_datasets()) == {"humaneval", "testgeneval", "testgeneval-lite"}
    for files in SOURCES.values():
        for remote in files:
            assert re.fullmatch(r"[0-9a-f]{40}", remote.revision)
            assert re.fullmatch(r"[0-9a-f]{64}", remote.sha256)
            assert remote.url().startswith("https://huggingface.co/datasets/")
            assert remote.revision in remote.url()
