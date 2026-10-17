"""Toplu test cephesi (Facade): GUI'nin "Toplu Test" sayfası bunu kullanır (US-6)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from testzede.batch.report import FORMATS, UnitResult
from testzede.batch.runner import (
    BatchConfig,
    BatchOutcome,
    Progress,
    StopFlag,
    run_dataset,
    run_split,
)
from testzede.config import default_config_path, load_config
from testzede.datasets.base import DEFAULT_DATA_DIR, raw_dir
from testzede.datasets.errors import DatasetError
from testzede.datasets.factory import DatasetFactory
from testzede.datasets.splits import SPLIT_NAMES, split_path
from testzede.execution.executor import SandboxExecutor
from testzede.rl.executor import Executor
from testzede.services.errors import ServiceError

__all__ = ["FORMATS", "BatchOutcome", "Target", "UnitResult", "run", "targets"]

TargetKind = Literal["split", "dataset"]


@dataclass(frozen=True)
class Target:
    """Arayüzde seçilebilecek bir çalıştırma hedefi."""

    kind: TargetKind
    name: str
    available: bool  # dosyaları diskte var mı

    @property
    def label(self) -> str:
        prefix = "Split" if self.kind == "split" else "Veri seti"
        suffix = "" if self.available else " (bulunamadı)"
        return f"{prefix}: {self.name}{suffix}"


def targets(data_dir: Path = DEFAULT_DATA_DIR) -> list[Target]:
    """Önce splitler, sonra veri setleri; diskte olmayanlar ``available=False``."""
    found = [Target("split", name, split_path(data_dir, name).is_file()) for name in SPLIT_NAMES]
    for name in DatasetFactory.names():
        folder = raw_dir(data_dir, name)
        found.append(Target("dataset", name, folder.is_dir() and any(folder.iterdir())))
    return found


def run(
    target: Target,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    reports_root: Path = Path("reports"),
    config_path: Path | None = None,
    limit: int | None = None,
    formats: Iterable[str] = FORMATS,
    executor: Executor | None = None,
    progress: Progress | None = None,
    should_stop: StopFlag | None = None,
) -> BatchOutcome:
    """Hedefi çalıştırıp raporları yazar.

    Raises:
        ServiceError: Yapılandırma, split, veri ya da rapor yazma hatası.
    """
    config_path = config_path or default_config_path()
    formats = tuple(formats)
    if not formats:
        raise ServiceError("En az bir rapor biçimi seçin.")
    try:
        config = BatchConfig.from_mapping(load_config(config_path))
    except (ValueError, TypeError) as exc:  # ConfigError dahil
        raise ServiceError(f"Yapılandırma geçersiz ({config_path}): {exc}") from exc
    runner = run_split if target.kind == "split" else run_dataset
    try:
        return runner(
            target.name,
            executor or SandboxExecutor(),
            config,
            data_dir=data_dir,
            reports_root=reports_root,
            config_name=config_path.as_posix(),
            limit=limit,
            formats=formats,
            progress=progress,
            should_stop=should_stop,
        )
    except DatasetError as exc:
        raise ServiceError(str(exc)) from exc
    except OSError as exc:
        raise ServiceError(f"Dosya hatası: {exc}") from exc
