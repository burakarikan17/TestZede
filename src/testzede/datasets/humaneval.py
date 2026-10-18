"""HumanEval yükleyicisi (bağımsız dış test, US-1 ve US-6).

Her görev bir ``CodeUnit``'tir: ``source = prompt + canonical_solution`` referans
(canonical) çözümdür; RL oracle'ı girdileri bu çözümde çalıştırır.
"""

from __future__ import annotations

from pathlib import Path

from testzede.datasets.base import DatasetLoader, LoadResult, SkippedUnit
from testzede.datasets.parquet_io import read_rows
from testzede.datasets.units import make_unit
from testzede.domain.models import CodeUnit

_COLUMNS = ("task_id", "prompt", "canonical_solution", "entry_point")


class HumanEvalLoader(DatasetLoader):
    """``data/raw/humaneval/test.parquet`` dosyasındaki 164 görevi yükler."""

    name = "humaneval"

    def source_files(self) -> list[Path]:
        return [self.raw_dir / "test.parquet"]

    def load(self) -> LoadResult:
        units: list[CodeUnit] = []
        skipped: list[SkippedUnit] = []
        for row in read_rows(self.source_files()[0], _COLUMNS, dataset=self.name):
            source = f"{row['prompt'] or ''}{row['canonical_solution'] or ''}"
            entry_point = str(row["entry_point"] or "") or None
            result = make_unit(str(row["task_id"]), self.name, source, entry_point)
            if isinstance(result, SkippedUnit):
                skipped.append(result)
            else:
                units.append(result)
        return LoadResult(self.name, tuple(units), tuple(skipped))
