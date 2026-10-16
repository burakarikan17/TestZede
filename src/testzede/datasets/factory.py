"""Veri seti yükleyicilerini adıyla üreten fabrika (Factory kalıbı)."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from testzede.datasets.base import DEFAULT_DATA_DIR, DatasetLoader
from testzede.datasets.errors import DatasetError
from testzede.datasets.humaneval import HumanEvalLoader
from testzede.datasets.small67 import Small67Loader
from testzede.datasets.testgeneval import TestGenEvalLiteLoader, TestGenEvalLoader


class DatasetFactory:
    """``DatasetFactory.get("humaneval")`` → ``DatasetLoader`` → ``Iterable[CodeUnit]``.

    Yeni veri seti: ``DatasetLoader``'dan türetip ``register`` ile kaydedin.
    """

    _loaders: ClassVar[dict[str, type[DatasetLoader]]] = {
        loader.name: loader
        for loader in (HumanEvalLoader, Small67Loader, TestGenEvalLiteLoader, TestGenEvalLoader)
    }

    @classmethod
    def register(cls, loader: type[DatasetLoader]) -> type[DatasetLoader]:
        """Yükleyici sınıfını adıyla kaydeder (dekoratör olarak da kullanılabilir)."""
        cls._loaders[loader.name] = loader
        return loader

    @classmethod
    def names(cls) -> tuple[str, ...]:
        """Kayıtlı veri seti adları."""
        return tuple(cls._loaders)

    @classmethod
    def get(cls, name: str, data_dir: Path = DEFAULT_DATA_DIR) -> DatasetLoader:
        """Adı verilen veri setinin yükleyicisini üretir.

        Raises:
            DatasetError: Veri seti adı bilinmiyorsa.
        """
        try:
            loader = cls._loaders[name]
        except KeyError:
            raise DatasetError(
                f"Bilinmeyen veri seti: '{name}'. Seçenekler: {', '.join(cls._loaders)}"
            ) from None
        return loader(data_dir)
