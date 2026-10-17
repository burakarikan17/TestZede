"""``testzede`` komut satırı girişi.

Alt komutlar:
    download     veri setlerini ``data/raw/`` altına indirir
    make-splits  data leakage'sız ``data/splits/*.json`` dosyalarını üretir
    batch        bir split ya da veri setinde toplu test çalıştırıp rapor yazar (US-6)

Diğer alt komutlar (``gui``) kendi modülleri hazır oldukça ``_COMMANDS``'a eklenir. Kullanıcı kaynaklı hatalar ``Hata: ...`` mesajıyla bildirilir, çıkış kodu 1'dir.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from testzede.batch.report import FORMATS, UnitResult
from testzede.batch.runner import BatchConfig, run_dataset, run_split
from testzede.config import ConfigError, default_config_path, load_config
from testzede.datasets.base import DEFAULT_DATA_DIR
from testzede.datasets.download import download_dataset, downloadable_datasets
from testzede.datasets.errors import DatasetError
from testzede.datasets.factory import DatasetFactory
from testzede.datasets.hashing import sha256_file
from testzede.datasets.splits import SPLIT_NAMES, build_splits, write_splits
from testzede.execution.executor import SandboxExecutor

_ALL = "all"


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("1 ya da daha büyük olmalı")
    return value


def _progress_printer() -> Callable[[str, int, int | None], None]:
    """Her dosya için yüzde ilerlemesini (en fazla %10 adımlarla) yazdıran geri çağrı."""
    last: dict[str, int] = {}

    def show(name: str, received: int, total: int | None) -> None:
        if not total:
            return
        step = int(received * 10 / total)
        if last.get(name) != step:
            last[name] = step
            print(f"  {name}: %{step * 10} ({received / 1e6:.1f}/{total / 1e6:.1f} MB)")

    return show


def _cmd_download(args: argparse.Namespace) -> int:
    names = downloadable_datasets() if args.dataset == _ALL else (args.dataset,)
    for name in names:
        print(f"{name}: indiriliyor...")
        paths = download_dataset(
            name, args.data_dir, force=args.force, progress=_progress_printer()
        )
        print(f"{name}: hazır ({', '.join(path.name for path in paths)})")
    if args.dataset == _ALL:
        print(
            "Not: 67_Python_Code_Small ders sorumlusundan alınır; "
            f".xlsx dosyasını {args.data_dir / 'raw' / 'small67'} altına koyun."
        )
    return 0


def _cmd_make_splits(args: argparse.Namespace) -> int:
    splits = build_splits(
        args.data_dir, strict_files=args.strict_files, allow_missing=args.allow_missing
    )
    for path in write_splits(splits, args.data_dir):
        split = splits[path.stem]
        counts = ", ".join(f"{name}: {len(uids)}" for name, uids in split.units.items())
        print(f"{split.name}: {split.unit_count} birim ({counts}) -> {path}")
        print(f"  SHA-256: {sha256_file(path)}")
    for name in sorted({n for split in splits.values() for n in split.missing_datasets}):
        print(f"Uyarı: '{name}' bulunamadı, atlandı.", file=sys.stderr)
    return 0


def _batch_progress(done: int, total: int, result: UnitResult) -> None:
    if result.error:
        status = f"hata: {result.error}"
    else:
        cov = result.coverage
        rate = f"%{cov.line_rate * 100:.0f} satır" if cov else "coverage yok"
        status = f"{result.test_count} test, {rate}"
    print(f"  [{done}/{total}] {result.uid}: {status}")


def _cmd_batch(args: argparse.Namespace) -> int:
    config_path = args.config or default_config_path()
    try:
        config = BatchConfig.from_mapping(load_config(config_path))
    except ValueError as exc:  # ConfigError dahil
        raise ConfigError(f"{config_path}: {exc}") from exc
    common = {
        "data_dir": args.data_dir,
        "reports_root": args.reports_dir,
        "config_name": config_path.as_posix(),
        "limit": args.limit,
        "formats": args.formats,
        "progress": _batch_progress,
    }
    executor = SandboxExecutor()
    if args.split:
        datasets = args.only.split(",") if args.only else None
        outcome = run_split(args.split, executor, config, datasets=datasets, **common)
    else:
        outcome = run_dataset(args.dataset, executor, config, **common)
    failed = sum(1 for r in outcome.results if r.error)
    print(f"{len(outcome.results)} birim çalıştırıldı, {failed} hatalı.")
    for dataset, paths in outcome.reports.items():
        print(f"{dataset}: rapor -> {paths[0].parent}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="testzede", description="RL ile otomatik test case hazırlama"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    download = sub.add_parser("download", help="veri setlerini indir")
    download.add_argument(
        "--dataset",
        required=True,
        choices=[*downloadable_datasets(), _ALL],
        help="indirilecek veri seti",
    )
    download.add_argument("--force", action="store_true", help="var olan dosyayı yeniden indir")

    splits = sub.add_parser("make-splits", help="data leakage'sız split dosyalarını üret")
    splits.add_argument(
        "--strict-files",
        action="store_true",
        help="ana deneyden Lite ile ortak dosyaları da çıkar",
    )
    splits.add_argument(
        "--allow-missing", action="store_true", help="eksik veri setlerini atla (uyarıyla)"
    )

    batch = sub.add_parser("batch", help="toplu test çalıştır ve rapor yaz (US-6)")
    target = batch.add_mutually_exclusive_group(required=True)
    target.add_argument("--split", choices=SPLIT_NAMES, help="data/splits/<split>.json")
    target.add_argument(
        "--dataset", choices=DatasetFactory.names(), help="split olmadan tek veri seti"
    )
    batch.add_argument("--only", help="split içinden virgülle ayrılmış veri setleri")
    batch.add_argument(
        "--limit", type=_positive_int, help="veri seti başına ilk N birim (deneme için)"
    )
    batch.add_argument(
        "--config", type=Path, help="yapılandırma (varsayılan: frozen.yaml, yoksa default.yaml)"
    )
    batch.add_argument(
        "--reports-dir", type=Path, default=Path("reports"), help="rapor kök klasörü"
    )
    batch.add_argument(
        "--formats", nargs="+", choices=FORMATS, default=list(FORMATS), help="rapor biçimleri"
    )

    for command in (download, splits, batch):
        command.add_argument(
            "--data-dir",
            type=Path,
            default=DEFAULT_DATA_DIR,
            help="veri klasörü (varsayılan: data)",
        )
    return parser


_COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "download": _cmd_download,
    "make-splits": _cmd_make_splits,
    "batch": _cmd_batch,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Komut satırı girişi; çıkış kodunu döndürür (0: başarılı)."""
    args = _build_parser().parse_args(argv)
    try:
        return _COMMANDS[args.command](args)
    except (DatasetError, ConfigError, OSError) as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
