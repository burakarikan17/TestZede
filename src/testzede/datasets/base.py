"""Veri seti yükleyicilerinin ortak sözleşmesi.

Her yükleyici bir veri setini ``CodeUnit`` listesine çevirir. Çevrilemeyen
örnekler sessizce atılmaz; neden koduyla ``SkippedUnit`` olarak raporlanır.

Disk düzeni: ``<data_dir>/raw/<veri_seti>/...`` (``data/`` repoya commit edilmez).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from testzede.domain.models import CodeUnit

# Atlama neden kodları.
SYNTAX_ERROR = "syntax_error"
EMPTY_SOURCE = "empty_source"
NO_ENTRY_POINT = "no_entry_point"
NO_ELIGIBLE_FUNCTION = "no_eligible_function"

DEFAULT_DATA_DIR = Path("data")


@dataclass(frozen=True)
class SkippedUnit:
    """Birime çevrilemeyen örnek ve nedeni."""

    uid: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class LoadResult:
    """Bir veri setinin yükleme sonucu.

    Attributes:
        units: Kullanıma hazır kod birimleri.
        skipped: Birime çevrilemeyen örnekler (neden koduyla).
        stats: Ek sayaçlar (örn. fonksiyon düzeyinde ret nedenleri).
    """

    dataset: str
    units: tuple[CodeUnit, ...]
    skipped: tuple[SkippedUnit, ...] = ()
    stats: Mapping[str, int] = field(default_factory=dict)

    def skip_counts(self) -> dict[str, int]:
        """Atlanan örneklerin neden koduna göre sayısı."""
        return dict(Counter(item.reason for item in self.skipped))


def raw_dir(data_dir: Path, dataset: str) -> Path:
    """Bir veri setinin ham dosyalarının klasörü: ``<data_dir>/raw/<veri_seti>``."""
    return Path(data_dir) / "raw" / dataset


class DatasetLoader(ABC):
    """Veri seti yükleyicisi (Factory ile üretilir)."""

    name: ClassVar[str]

    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR) -> None:
        self.data_dir = Path(data_dir)

    @property
    def raw_dir(self) -> Path:
        """Bu veri setinin ham dosya klasörü."""
        return raw_dir(self.data_dir, self.name)

    @abstractmethod
    def load(self) -> LoadResult:
        """Veri setini okuyup birimlere çevirir.

        Raises:
            DatasetNotFoundError: Ham veri dosyası yoksa.
            DatasetFormatError: Dosya okunamıyor ya da beklenen sütunlar yok.
        """

    @abstractmethod
    def source_files(self) -> list[Path]:
        """Yükleyicinin okuduğu ham veri dosyaları (özetleri raporlara yazılır).

        Raises:
            DatasetNotFoundError: Ham veri dosyası yoksa.
        """

    def __iter__(self) -> Iterator[CodeUnit]:
        return iter(self.load().units)
