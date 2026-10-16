"""67_Python_Code_Small yükleyicisi (bağımsız dış test).

Veri seti ders sorumlusundan alınır ve ``data/raw/small67/`` altına konur. Dosya
tek sayfalı bir ``.xlsx``'tir: her satırın ilk hücresi bir Python fonksiyonudur,
başlık satırı yoktur. ``uid`` satır numarasıdır: ``small67/<satır>``.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

from testzede.datasets.base import DatasetLoader, LoadResult, SkippedUnit
from testzede.datasets.errors import DatasetFormatError, DatasetNotFoundError
from testzede.datasets.units import make_unit
from testzede.domain.models import CodeUnit


class Small67Loader(DatasetLoader):
    """``data/raw/small67/*.xlsx`` dosyasındaki fonksiyonları yükler."""

    name = "small67"

    def source_files(self) -> list[Path]:
        return [self._find_workbook()]

    def load(self) -> LoadResult:
        path = self._find_workbook()
        try:
            workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except (OSError, InvalidFileException, zipfile.BadZipFile, KeyError) as exc:
            raise DatasetFormatError(f"{path.name} okunamadı: {exc}") from exc
        try:
            rows = list(workbook.worksheets[0].iter_rows(max_col=1, values_only=True))
        except (IndexError, OSError, zipfile.BadZipFile) as exc:
            raise DatasetFormatError(f"{path.name}: sayfa okunamadı ({exc})") from exc
        finally:
            workbook.close()

        units: list[CodeUnit] = []
        skipped: list[SkippedUnit] = []
        for number, (cell,) in enumerate(rows, start=1):
            if cell is None or not str(cell).strip():
                continue  # boş satır örnek değildir
            source = str(cell).replace("\r\n", "\n").replace("\r", "\n")
            result = make_unit(f"{self.name}/{number}", self.name, source)
            if isinstance(result, SkippedUnit):
                skipped.append(result)
            else:
                units.append(result)
        return LoadResult(self.name, tuple(units), tuple(skipped))

    def _find_workbook(self) -> Path:
        folder = self.raw_dir
        candidates = sorted(folder.glob("*.xlsx")) if folder.is_dir() else []
        candidates = [path for path in candidates if not path.name.startswith("~$")]
        if not candidates:
            raise DatasetNotFoundError(
                f"67_Python_Code_Small bulunamadı. Ders sorumlusundan alınan .xlsx dosyasını "
                f"şuraya koyun: {folder}"
            )
        if len(candidates) > 1:
            names = ", ".join(path.name for path in candidates)
            raise DatasetFormatError(f"{folder} içinde tek .xlsx olmalı, bulunanlar: {names}")
        return candidates[0]
