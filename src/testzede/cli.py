"""``testzede`` komut satırı girişi.

Alt komutlar:
    download     veri setlerini ``data/raw/`` altına indirir
    make-splits  data leakage'sız ``data/splits/*.json`` dosyalarını üretir

Diğer alt komutlar (``batch``, ``gui``) kendi modülleri hazır oldukça ``_COMMANDS``'a
eklenir. Kullanıcı kaynaklı hatalar ``Hata: ...`` mesajıyla bildirilir, çıkış kodu 1'dir.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from testzede.datasets.base import DEFAULT_DATA_DIR
from testzede.datasets.download import download_dataset, downloadable_datasets
from testzede.datasets.errors import DatasetError
from testzede.datasets.hashing import sha256_file
from testzede.datasets.splits import build_splits, write_splits

_ALL = "all"


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
    for name in {n for split in splits.values() for n in split.missing_datasets}:
        print(f"Uyarı: '{name}' bulunamadı, atlandı.", file=sys.stderr)
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

    for command in (download, splits):
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
}


def main(argv: Sequence[str] | None = None) -> int:
    """Komut satırı girişi; çıkış kodunu döndürür (0: başarılı)."""
    args = _build_parser().parse_args(argv)
    try:
        return _COMMANDS[args.command](args)
    except (DatasetError, OSError) as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
