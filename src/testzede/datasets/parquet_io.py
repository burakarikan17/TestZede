"""Parquet dosyalarından sütun bazlı satır okuma."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from testzede.datasets.errors import DatasetFormatError, DatasetNotFoundError

_BATCH_SIZE = 256


def read_rows(path: Path, columns: Sequence[str], *, dataset: str) -> Iterator[dict[str, object]]:
    """Parquet dosyasının yalnızca istenen sütunlarını satır satır okur.

    Büyük dosyalar (TestGenEval test: ~58 MB) belleğe topluca alınmaz.

    Raises:
        DatasetNotFoundError: Dosya yoksa (mesaj indirme komutunu söyler).
        DatasetFormatError: Dosya bozuksa ya da sütunlardan biri yoksa.
    """
    path = Path(path)
    if not path.is_file():
        raise DatasetNotFoundError(
            f"'{dataset}' veri dosyası bulunamadı: {path}. "
            f"Önce şunu çalıştırın: testzede download --dataset {dataset}"
        )
    try:
        parquet = pq.ParquetFile(path)
        missing = [name for name in columns if name not in parquet.schema_arrow.names]
        if missing:
            raise DatasetFormatError(f"{path.name}: beklenen sütunlar yok: {', '.join(missing)}")
        for batch in parquet.iter_batches(batch_size=_BATCH_SIZE, columns=list(columns)):
            yield from batch.to_pylist()
    except (pa.ArrowException, OSError) as exc:
        raise DatasetFormatError(f"{path.name} okunamadı: {exc}") from exc
