"""Data leakage'sız veri ayrımı (``testzede make-splits``).

Üç split üretilir ve ``data/splits/<ad>.json`` olarak yazılır:

==============  ============================================  ======================
Split           İçerik                                        Kullanım
==============  ============================================  ======================
``development`` TestGenEvalLite                               ödül ve hiperparametre
``main``        TestGenEval test **eksi** Lite                ana deney
``external``    HumanEval + 67_Python_Code_Small              genellenebilirlik
==============  ============================================  ======================

Sızıntı kuralları (ARCHITECTURE.md §4):
    1. Lite örnekleri ``instance_id`` ile ana deneyden çıkarılır. (``id`` sütunları iki
       veri setinde farklıdır; ``instance_id`` ortaktır.)
    2. Ana deneyde, geliştirme kümesindekiyle **birebir aynı kaynak** olan birimler de
       çıkarılır (aynı fonksiyon farklı commit'lerde tekrar eder).
    3. Her split dosyası, kullandığı ham veri dosyalarının SHA-256 özetini taşır; veri
       değişirse ``load_split_units`` hata verir. Raporlar split dosyasının özetini yazar.

Split dosyaları zaman damgası içermez: aynı veriden her zaman aynı bayt dizisi çıkar.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from testzede.datasets.base import DEFAULT_DATA_DIR, DatasetLoader, LoadResult
from testzede.datasets.errors import DatasetNotFoundError, IntegrityError, SplitError
from testzede.datasets.factory import DatasetFactory
from testzede.datasets.hashing import sha256_file, sha256_text
from testzede.datasets.testgeneval import (
    RowKey,
    TestGenEvalLiteLoader,
    TestGenEvalLoader,
    uid_instance_id,
)
from testzede.domain.models import CodeUnit

SCHEMA_VERSION = 1
EXTRACTOR_VERSION = 1  # extraction.py kuralları değişirse artırılır
LEAKAGE_KEY = "instance_id"
SPLIT_NAMES = ("development", "main", "external")


@dataclass(frozen=True)
class SplitDefinition:
    """Bir split: veri setlerine göre sıralı birim kimlikleri ve izlenebilirlik bilgisi."""

    name: str
    units: Mapping[str, tuple[str, ...]]  # veri seti → sıralı uid'ler
    sources: Mapping[str, str]  # "testgeneval/test.parquet" → SHA-256
    strict_files: bool = False
    missing_datasets: tuple[str, ...] = ()
    stats: Mapping[str, Mapping[str, int]] = field(default_factory=dict)

    @property
    def unit_count(self) -> int:
        """Splitteki toplam birim sayısı."""
        return sum(len(uids) for uids in self.units.values())

    def to_json(self) -> str:
        """Kararlı (sıralı, zaman damgasız) JSON metni."""
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "extractor_version": EXTRACTOR_VERSION,
            "name": self.name,
            "leakage_key": LEAKAGE_KEY,
            "strict_files": self.strict_files,
            "missing_datasets": list(self.missing_datasets),
            "sources": dict(self.sources),
            "units": {dataset: list(uids) for dataset, uids in self.units.items()},
            "stats": {key: dict(value) for key, value in self.stats.items()},
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, text: str) -> SplitDefinition:
        """JSON metninden split okur.

        Raises:
            SplitError: Biçim bozuksa ya da şema sürümü desteklenmiyorsa.
        """
        try:
            data = json.loads(text)
            version = data["schema_version"]
            if version != SCHEMA_VERSION:
                raise SplitError(
                    f"Desteklenmeyen split şeması: {version} (beklenen {SCHEMA_VERSION}). "
                    "make-splits'i yeniden çalıştırın."
                )
            return cls(
                name=str(data["name"]),
                units={k: tuple(v) for k, v in data["units"].items()},
                sources={k: str(v) for k, v in data["sources"].items()},
                strict_files=bool(data.get("strict_files", False)),
                missing_datasets=tuple(data.get("missing_datasets", ())),
                stats={k: dict(v) for k, v in data.get("stats", {}).items()},
            )
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise SplitError(f"Split dosyası bozuk: {exc!r}") from exc


def split_path(data_dir: Path, name: str) -> Path:
    """``<data_dir>/splits/<ad>.json``."""
    return Path(data_dir) / "splits" / f"{name}.json"


def read_split(path: Path) -> SplitDefinition:
    """Split dosyasını okur.

    Raises:
        SplitError: Dosya yok, okunamıyor ya da bozuk.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SplitError(
            f"Split dosyası okunamadı: {path} ({exc}). Önce şunu çalıştırın: testzede make-splits"
        ) from exc
    return SplitDefinition.from_json(text)


def write_splits(splits: Mapping[str, SplitDefinition], data_dir: Path) -> list[Path]:
    """Splitleri ``<data_dir>/splits/`` altına yazar ve dosya yollarını döndürür."""
    paths: list[Path] = []
    try:
        (Path(data_dir) / "splits").mkdir(parents=True, exist_ok=True)
        for name, split in splits.items():
            path = split_path(data_dir, name)
            path.write_text(split.to_json(), encoding="utf-8", newline="\n")
            paths.append(path)
    except OSError as exc:
        raise SplitError(f"Split dosyaları yazılamadı: {exc}") from exc
    return paths


# ---- üretim --------------------------------------------------------------------


@dataclass(frozen=True)
class _Part:
    """Bir splitin tek veri seti parçası: yükleyici, ham sonuç ve tutulan birimler."""

    loader: DatasetLoader
    result: LoadResult
    kept: list[CodeUnit]


def build_splits(
    data_dir: Path = DEFAULT_DATA_DIR,
    *,
    strict_files: bool = False,
    allow_missing: bool = False,
) -> dict[str, SplitDefinition]:
    """Ham verilerden ``development``, ``main`` ve ``external`` splitlerini üretir.

    Args:
        strict_files: ``True`` ise ana deneyden Lite ile **ortak dosyalar** da çıkarılır
            (varsayılan: yalnızca Lite örnekleri ve birebir aynı birimler; ortak dosya
            sayısı yine de ``stats.leakage`` içinde raporlanır).
        allow_missing: ``True`` ise eksik veri setleri atlanır ve split içinde belirtilir;
            aksi halde herhangi bir eksik veri seti hata verir.

    Raises:
        SplitError: Veri eksikse (``allow_missing`` kapalıyken) ya da sızıntı denetimi
            başarısız olursa.
        DatasetFormatError: Veri dosyaları okunamıyorsa.
    """
    data_dir = Path(data_dir)
    missing: list[str] = []
    lite_loader = TestGenEvalLiteLoader(data_dir)
    lite = _try_load(lite_loader, missing)
    lite_keys = lite_loader.row_keys() if lite else []
    full_keys = _try_keys(TestGenEvalLoader(data_dir), missing)
    humaneval = _try_load(DatasetFactory.get("humaneval", data_dir), missing)
    small67 = _try_load(DatasetFactory.get("small67", data_dir), missing)
    if missing and not allow_missing:
        raise SplitError(
            f"Eksik veri setleri: {', '.join(sorted(set(missing)))}. "
            "İndirmek için: testzede download --dataset all "
            "(small67 ders sorumlusundan alınır; --allow-missing ile atlanabilir)."
        )
    missing_names = tuple(sorted(set(missing)))

    splits: dict[str, SplitDefinition] = {}
    development_units: list[CodeUnit] = []
    if lite is not None:
        development_units, duplicates, _ = _deduplicate(lite.result.units)
        part = _Part(lite.loader, lite.result, development_units)
        splits["development"] = _make_split(
            "development",
            [part],
            strict_files,
            missing_names,
            {"deduplication": {"identical_units_removed": duplicates}},
        )
    if lite is not None and full_keys is not None:
        splits["main"] = _build_main(
            data_dir, lite_keys, full_keys, development_units, strict_files, missing_names
        )
        verify_no_leakage(splits["development"], splits["main"])
    external = [
        _Part(loaded.loader, loaded.result, list(loaded.result.units))
        for loaded in (humaneval, small67)
        if loaded is not None
    ]
    if external:
        splits["external"] = _make_split("external", external, strict_files, missing_names, {})
    return splits


def _build_main(
    data_dir: Path,
    lite_keys: list[RowKey],
    full_keys: list[RowKey],
    development_units: list[CodeUnit],
    strict_files: bool,
    missing_names: tuple[str, ...],
) -> SplitDefinition:
    lite_ids = frozenset(key.instance_id for key in lite_keys)
    lite_files = frozenset((key.repo, key.code_file) for key in lite_keys)
    loader = TestGenEvalLoader(
        data_dir,
        exclude_instance_ids=lite_ids,
        exclude_files=lite_files if strict_files else frozenset(),
    )
    result = loader.load()
    forbidden = frozenset(sha256_text(unit.source) for unit in development_units)
    kept, duplicates, identical = _deduplicate(result.units, forbidden)
    extra = {
        "deduplication": {
            "identical_units_removed": duplicates,
            "identical_to_development_removed": identical,
        },
        "leakage": _overlap_stats(lite_keys, full_keys, strict_files),
    }
    return _make_split("main", [_Part(loader, result, kept)], strict_files, missing_names, extra)


def _overlap_stats(
    lite_keys: list[RowKey], full_keys: list[RowKey], strict_files: bool
) -> dict[str, int]:
    """Lite ile ana deney arasındaki örtüşme sayıları (şeffaflık için rapora yazılır)."""
    lite_ids = {key.instance_id for key in lite_keys}
    lite_files = {(key.repo, key.code_file) for key in lite_keys}
    remaining = [key for key in full_keys if key.instance_id not in lite_ids]
    shared = [key for key in remaining if (key.repo, key.code_file) in lite_files]
    return {
        "lite_instances": len(lite_ids),
        "full_rows": len(full_keys),
        "rows_removed_same_instance": len(full_keys) - len(remaining),
        "rows_in_files_shared_with_lite": len(shared),
        "files_shared_with_lite": len({(key.repo, key.code_file) for key in shared}),
        "rows_removed_strict_files": len(shared) if strict_files else 0,
    }


def _deduplicate(
    units: Iterable[CodeUnit], forbidden: frozenset[str] = frozenset()
) -> tuple[list[CodeUnit], int, int]:
    """Birebir aynı kaynaklı birimleri eler (uid sırasına göre ilki kalır).

    Returns:
        ``(tutulanlar, kendi içinde tekrar edenler, forbidden kümesindekilerle aynı olanlar)``.
    """
    seen: set[str] = set()
    kept: list[CodeUnit] = []
    duplicates = identical = 0
    for unit in sorted(units, key=lambda item: item.uid):
        digest = sha256_text(unit.source)
        if digest in forbidden:
            identical += 1
        elif digest in seen:
            duplicates += 1
        else:
            seen.add(digest)
            kept.append(unit)
    return kept, duplicates, identical


def _make_split(
    name: str,
    parts: list[_Part],
    strict_files: bool,
    missing: tuple[str, ...],
    extra_stats: Mapping[str, Mapping[str, int]],
) -> SplitDefinition:
    units: dict[str, tuple[str, ...]] = {}
    sources: dict[str, str] = {}
    stats: dict[str, Mapping[str, int]] = {}
    for part in parts:
        dataset = part.loader.name
        units[dataset] = tuple(sorted(unit.uid for unit in part.kept))
        for path in part.loader.source_files():
            sources[f"{dataset}/{path.name}"] = sha256_file(path)
        skipped = {f"skipped.{reason}": n for reason, n in part.result.skip_counts().items()}
        stats[dataset] = {"units": len(part.kept), **skipped, **part.result.stats}
    stats.update(extra_stats)
    return SplitDefinition(name, units, sources, strict_files, missing, stats)


def _try_load(loader: DatasetLoader, missing: list[str]) -> _Part | None:
    """Yükler; ham dosya yoksa adını ``missing`` listesine ekleyip ``None`` döndürür."""
    try:
        result = loader.load()
    except DatasetNotFoundError:
        missing.append(loader.name)
        return None
    return _Part(loader, result, list(result.units))


def _try_keys(loader: TestGenEvalLoader, missing: list[str]) -> list[RowKey] | None:
    try:
        return loader.row_keys()
    except DatasetNotFoundError:
        missing.append(loader.name)
        return None


# ---- sızıntı denetimi ----------------------------------------------------------


def verify_no_leakage(development: SplitDefinition, main: SplitDefinition) -> None:
    """``development`` ve ``main`` arasında ortak ``instance_id`` ya da ``uid`` olmadığını doğrular.

    Raises:
        SplitError: Ortak örnek varsa (sayıları mesajda yazılır).
    """
    dev_uids = {uid for uids in development.units.values() for uid in uids}
    main_uids = {uid for uids in main.units.values() for uid in uids}
    dev_instances = {uid_instance_id(uid) for uid in dev_uids}
    main_instances = {uid_instance_id(uid) for uid in main_uids}
    shared_uids = dev_uids & main_uids
    shared_instances = dev_instances & main_instances
    if shared_uids or shared_instances:
        raise SplitError(
            f"Data leakage: development ve main arasında {len(shared_instances)} ortak "
            f"{LEAKAGE_KEY}, {len(shared_uids)} ortak birim var."
        )


# ---- kullanım ------------------------------------------------------------------


def load_split_units(split: SplitDefinition, data_dir: Path = DEFAULT_DATA_DIR) -> list[CodeUnit]:
    """Splitteki birimleri ham verilerden yükler (toplu çalıştırıcı bunu kullanır).

    Önce ham dosyaların özetleri split dosyasındakilerle karşılaştırılır.

    Raises:
        IntegrityError: Ham dosya split üretildikten sonra değişmişse.
        DatasetNotFoundError: Ham dosya yoksa.
        SplitError: Splitteki bir birim artık üretilemiyorsa.
    """
    data_dir = Path(data_dir)
    for relative, expected in split.sources.items():
        path = data_dir / "raw" / relative
        if not path.is_file():
            raise DatasetNotFoundError(f"Ham veri dosyası yok: {path}")
        if sha256_file(path) != expected:
            raise IntegrityError(
                f"{relative} split üretildikten sonra değişmiş. "
                "Şunu yeniden çalıştırın: testzede make-splits"
            )
    loaded: list[CodeUnit] = []
    for dataset, uids in split.units.items():
        available = {unit.uid: unit for unit in DatasetFactory.get(dataset, data_dir).load().units}
        absent = [uid for uid in uids if uid not in available]
        if absent:
            raise SplitError(
                f"{dataset}: splitteki {len(absent)} birim üretilemedi (örn. {absent[0]}). "
                "Şunu yeniden çalıştırın: testzede make-splits"
            )
        loaded.extend(available[uid] for uid in uids)
    return loaded
