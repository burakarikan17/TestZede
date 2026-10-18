"""TestGenEval ve TestGenEvalLite yükleyicileri (geliştirme ve ana deney).

TestGenEval örnekleri gerçek repo dosyalarıdır; dosyanın tamamı tek başına çalışmaz.
Bu yüzden birim **fonksiyon düzeyindedir**: ``extraction`` modülü her dosyadan bağımsız
çalışabilen fonksiyonları (gerekli import, sabit ve yardımcılarıyla) çıkarır. Çıkarılamayan
dosyalar neden koduyla ``skipped`` listesine yazılır.

``uid``: ``<instance_id>::<dosya yolu>::<fonksiyon>``. Lite ile ana deney arasındaki
data leakage ``instance_id`` üzerinden denetlenir (iki veri setinin ``id`` sütunları
farklıdır, ``instance_id`` ortaktır).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar, NamedTuple

from testzede.datasets.base import (
    DEFAULT_DATA_DIR,
    EMPTY_SOURCE,
    NO_ELIGIBLE_FUNCTION,
    SYNTAX_ERROR,
    DatasetLoader,
    LoadResult,
    SkippedUnit,
)
from testzede.datasets.docstring import doctest_examples
from testzede.datasets.extraction import ExtractionError, extract_functions
from testzede.datasets.parquet_io import read_rows
from testzede.domain.models import CodeUnit

_COLUMNS = ("instance_id", "repo", "code_file", "code_src")
_UID_SEPARATOR = "::"


class RowKey(NamedTuple):
    """Bir veri satırının kimliği (kaynak kod okunmadan)."""

    instance_id: str
    repo: str
    code_file: str


def unit_uid(instance_id: str, code_file: str, function: str) -> str:
    """Fonksiyon düzeyi birimin benzersiz kimliği."""
    return _UID_SEPARATOR.join((instance_id, code_file, function))


def uid_instance_id(uid: str) -> str:
    """Birim kimliğinden ``instance_id``'yi çıkarır (sızıntı denetimi için)."""
    return uid.split(_UID_SEPARATOR, 1)[0]


class _TestGenEvalBase(DatasetLoader):
    """TestGenEval ailesinin ortak yükleyicisi (parquet bölümleri ``splits``)."""

    __test__ = False  # pytest, ``Test`` ile başlayan sınıf adını toplamasın

    splits: ClassVar[tuple[str, ...]]

    def __init__(
        self,
        data_dir: Path = DEFAULT_DATA_DIR,
        *,
        exclude_instance_ids: frozenset[str] = frozenset(),
        exclude_files: frozenset[tuple[str, str]] = frozenset(),
    ) -> None:
        """
        Args:
            exclude_instance_ids: Bu ``instance_id``'lere ait satırlar atlanır
                (ana deneyden Lite örneklerini çıkarmak için).
            exclude_files: ``(repo, dosya yolu)`` çiftlerine ait satırlar atlanır
                (sıkı mod: Lite ile ortak dosyaları da çıkarmak için).
        """
        super().__init__(data_dir)
        self._exclude_instance_ids = exclude_instance_ids
        self._exclude_files = exclude_files

    def source_files(self) -> list[Path]:
        return [self.raw_dir / f"{split}.parquet" for split in self.splits]

    def _rows(self, columns: tuple[str, ...]) -> Iterator[dict[str, object]]:
        for path in self.source_files():
            yield from read_rows(path, columns, dataset=self.name)

    def row_keys(self) -> list[RowKey]:
        """Tüm satırların kimlikleri (dışlama filtresi uygulanmadan)."""
        keys = ("instance_id", "repo", "code_file")
        return [RowKey(*(str(row[k]) for k in keys)) for row in self._rows(keys)]

    def load(self) -> LoadResult:
        units: list[CodeUnit] = []
        skipped: list[SkippedUnit] = []
        stats: Counter[str] = Counter()
        for row in self._rows(_COLUMNS):
            instance_id, repo = str(row["instance_id"]), str(row["repo"])
            code_file, source = str(row["code_file"]), str(row["code_src"] or "")
            if instance_id in self._exclude_instance_ids:
                stats["rows_excluded_instance"] += 1
                continue
            if (repo, code_file) in self._exclude_files:
                stats["rows_excluded_file"] += 1
                continue
            stats["rows"] += 1
            row_uid = _UID_SEPARATOR.join((instance_id, code_file))
            if not source.strip():
                skipped.append(SkippedUnit(row_uid, EMPTY_SOURCE))
                continue
            try:
                extraction = extract_functions(source)
            except ExtractionError as exc:
                skipped.append(SkippedUnit(row_uid, SYNTAX_ERROR, str(exc)))
                continue
            for reason, count in extraction.rejected.items():
                stats[f"rejected.{reason}"] += count
            if not extraction.functions:
                skipped.append(SkippedUnit(row_uid, NO_ELIGIBLE_FUNCTION))
                continue
            for function in extraction.functions:
                units.append(
                    CodeUnit(
                        uid=unit_uid(instance_id, code_file, function.name),
                        source=function.source,
                        entry_point=function.name,
                        dataset=self.name,
                        seed_examples=doctest_examples(function.docstring),
                    )
                )
        return LoadResult(self.name, tuple(units), tuple(skipped), dict(stats))


class TestGenEvalLoader(_TestGenEvalBase):
    """Ana deney: ``data/raw/testgeneval/test.parquet``."""

    name = "testgeneval"
    splits = ("test",)


class TestGenEvalLiteLoader(_TestGenEvalBase):
    """Geliştirme kümesi: ``data/raw/testgeneval-lite/{test,dev}.parquet``."""

    name = "testgeneval-lite"
    splits = ("test", "dev")
