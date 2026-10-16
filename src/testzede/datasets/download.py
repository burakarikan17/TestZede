"""Veri setlerini indirir ve SHA-256 özetiyle doğrular.

Yalnızca standart kütüphane kullanılır. Dosyalar önce ``.part`` olarak yazılır,
özet doğrulandıktan sonra yerine taşınır; yarım ya da bozuk dosya asla kalmaz.
"""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from testzede.datasets.base import DEFAULT_DATA_DIR, raw_dir
from testzede.datasets.errors import DatasetError, DownloadError, IntegrityError
from testzede.datasets.hashing import sha256_file
from testzede.datasets.sources import HF_BASE_URL, SOURCES, RemoteFile

_CHUNK = 1024 * 256

# (dosya adı, inen bayt, toplam bayt ya da None)
ProgressCallback = Callable[[str, int, int | None], None]


def downloadable_datasets() -> tuple[str, ...]:
    """İndirilebilen veri setlerinin adları."""
    return tuple(SOURCES)


def download_dataset(
    name: str,
    data_dir: Path = DEFAULT_DATA_DIR,
    *,
    base_url: str = HF_BASE_URL,
    force: bool = False,
    timeout: float = 60.0,
    progress: ProgressCallback | None = None,
) -> list[Path]:
    """Bir veri setinin dosyalarını ``<data_dir>/raw/<name>/`` altına indirir.

    Özeti doğru olan mevcut dosya yeniden indirilmez (``force`` ile zorlanabilir).

    Returns:
        Veri setine ait yerel dosya yolları.

    Raises:
        DatasetError: Veri seti adı bilinmiyorsa.
        DownloadError: Ağ ya da disk hatasında.
        IntegrityError: İnen dosyanın özeti beklenenle uyuşmuyorsa.
    """
    if name not in SOURCES:
        available = ", ".join(SOURCES)
        raise DatasetError(f"İndirilebilir veri seti değil: '{name}'. Seçenekler: {available}")

    target_dir = raw_dir(data_dir, name)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DownloadError(f"Klasör oluşturulamadı: {target_dir} ({exc})") from exc

    paths = []
    for remote in SOURCES[name]:
        destination = target_dir / remote.local_name
        if not force and _is_valid(destination, remote.sha256):
            paths.append(destination)
            continue
        _fetch(remote, destination, base_url, timeout, progress)
        paths.append(destination)
    return paths


def _is_valid(path: Path, expected_sha256: str) -> bool:
    try:
        return path.is_file() and sha256_file(path) == expected_sha256
    except OSError:
        return False


def _fetch(
    remote: RemoteFile,
    destination: Path,
    base_url: str,
    timeout: float,
    progress: ProgressCallback | None,
) -> None:
    partial = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256()
    url = remote.url(base_url)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response, partial.open("wb") as out:
            length = response.headers.get("Content-Length")
            total = int(length) if length and length.isdigit() else None
            received = 0
            while chunk := response.read(_CHUNK):
                out.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if progress:
                    progress(remote.local_name, received, total)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        partial.unlink(missing_ok=True)
        raise DownloadError(f"İndirilemedi: {url} ({exc})") from exc

    if digest.hexdigest() != remote.sha256:
        partial.unlink(missing_ok=True)
        raise IntegrityError(
            f"{remote.local_name}: SHA-256 uyuşmuyor (beklenen {remote.sha256[:12]}…, "
            f"gelen {digest.hexdigest()[:12]}…). Dosya silindi; yeniden deneyin."
        )
    try:
        partial.replace(destination)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise DownloadError(f"Dosya yerine taşınamadı: {destination} ({exc})") from exc
