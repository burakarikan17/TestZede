"""Toplu çalıştırıcı (US-6): her ``CodeUnit`` için metrik → RL → coverage → mutasyon → tahmin.

Bir birimde hangi aşama hata verirse versin toplu çalıştırma durmaz: hata mesajı
``UnitResult.error``'a yazılır, o ana kadarki sonuçlar korunur (Madde-1).

Mutasyon (US-5) ve tahmin (opsiyonel) aşamaları ``BatchConfig`` üzerinden takılır;
verilmezse rapordaki ilgili sütunlar boş kalır.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from testzede.analysis.metrics import MetricsError, compute_metrics
from testzede.batch.report import FORMATS, ReportMeta, UnitResult, report_dir, write_report
from testzede.datasets.base import DEFAULT_DATA_DIR
from testzede.datasets.factory import DatasetFactory
from testzede.datasets.hashing import sha256_file
from testzede.datasets.splits import load_split_units, read_split, split_path
from testzede.domain.models import (
    CodeUnit,
    CoverageReport,
    MetricSet,
    MutationReport,
    Prediction,
    RunStats,
    TestCase,
)
from testzede.mutation.engine import MutationEngine
from testzede.prediction.stage import prediction_stage
from testzede.rl.agent import QLearningAgent
from testzede.rl.executor import Executor
from testzede.rl.signature import SignatureError
from testzede.rl.trainer import EpisodeResult, RLConfig, generate_tests

MutationStage = Callable[[CodeUnit, Sequence[TestCase]], MutationReport]
PredictionStage = Callable[[CodeUnit, MetricSet | None, EpisodeResult], Prediction]
Progress = Callable[[int, int, UnitResult], None]  # (biten, toplam, son sonuç)
StopFlag = Callable[[], bool]


def mutation_stage(engine: MutationEngine | None = None) -> MutationStage:
    """Mutasyon motorunu ``BatchConfig.mutation`` aşamasına sarar (US-5).

    Testlerin hiç çalıştırmadığı satırlardaki mutantlar koşturulmadan hayatta kalan
    sayılır ve skoru düşürür. Motor hatası (``MutationError``) ``run_unit``'te yakalanır.
    """
    engine = engine or MutationEngine()

    def stage(unit: CodeUnit, tests: Sequence[TestCase]) -> MutationReport:
        return engine.run_detailed(unit.source, list(tests)).report

    return stage


@dataclass(frozen=True)
class BatchConfig:
    """Toplu çalıştırma ayarları.

    Attributes:
        seed: Tekrarlanabilirlik için temel tohum; ``i``. birim ``seed + i`` kullanır.
        share_agent: Q-tablosu birimler arasında paylaşılsın mı.
        suite_timeout_s: Üretilen test paketinin son (tam) çalıştırması için süre sınırı.
        mutation: Mutasyon aşaması; yapılandırmada ``batch.mutation: true`` ise
            :func:`mutation_stage` kullanılır.
        prediction: Tahmin aşaması (opsiyonel); ``batch.prediction: true`` ise temel tahmin
            (:func:`testzede.prediction.stage.prediction_stage`) kullanılır.
    """

    rl: RLConfig = field(default_factory=RLConfig)
    seed: int | None = 0
    share_agent: bool = True
    suite_timeout_s: float = 60.0
    mutation: MutationStage | None = None
    prediction: PredictionStage | None = None

    @classmethod
    def from_mapping(cls, config: Mapping) -> BatchConfig:
        """``configs/*.yaml`` içeriğinden kurar (``batch`` bölümü + RL bölümleri)."""
        section = dict(config.get("batch", {}))
        seed = section.pop("seed", 0)
        values = {
            "seed": None if seed is None else int(seed),
            "share_agent": bool(section.pop("share_agent", True)),
            "suite_timeout_s": float(section.pop("suite_timeout_s", 60.0)),
            "mutation": mutation_stage() if bool(section.pop("mutation", False)) else None,
            "prediction": prediction_stage() if bool(section.pop("prediction", False)) else None,
        }
        if section:
            raise ValueError(f"Bilinmeyen batch ayarı: {', '.join(sorted(section))}")
        return cls(rl=RLConfig.from_mapping(config), **values)


@dataclass
class BatchOutcome:
    """Bir toplu çalıştırmanın sonuçları ve yazılan rapor dosyaları (veri seti → yollar)."""

    results: list[UnitResult]
    reports: dict[str, list[Path]] = field(default_factory=dict)
    stopped: bool = False  # kullanıcı yarıda kestiyse


def measure_suite(
    unit: CodeUnit, tests: Sequence[TestCase], executor: Executor, *, timeout: float = 60.0
) -> tuple[CoverageReport | None, float]:
    """Test paketini bir kez baştan çalıştırır: ``(coverage, süre_s)``.

    Paket boşsa ya da hiçbir satır ölçülemediyse coverage ``None`` döner.
    """
    if not tests:
        return None, 0.0
    suite = executor.run_tests(unit, tests, timeout=timeout)
    if not suite.all_lines:
        return None, suite.stats.execution_time_s
    coverage = getattr(suite, "coverage", None)
    if not isinstance(coverage, CoverageReport):
        coverage = CoverageReport(
            covered_lines=len(suite.covered_lines & suite.all_lines),
            total_lines=len(suite.all_lines),
            covered_branches=len(suite.covered_branches & suite.all_branches),
            total_branches=len(suite.all_branches),
        )
    return coverage, suite.stats.execution_time_s


def run_unit(
    unit: CodeUnit,
    executor: Executor,
    config: BatchConfig | None = None,
    *,
    agent: QLearningAgent | None = None,
    seed: int | None = None,
) -> UnitResult:
    """Tek bir birim için hattı çalıştırır. İstisna fırlatmaz.

    Coverage ve test çalıştırma süresi, RL'nin seçtiği test paketinin tek seferde
    baştan çalıştırılmasıyla ölçülür. Derlenebilirlik oranı ise RL'nin ürettiği
    tüm testler üzerindendir (seçilmeyenler dahil).
    """
    config = config or BatchConfig()
    result = UnitResult(uid=unit.uid, dataset=unit.dataset or "")

    try:
        result.metrics = compute_metrics(unit.source)
    except MetricsError as exc:
        result.error = f"Metrik: {exc}"
        return result
    except Exception as exc:  # noqa: BLE001 - Madde-1
        result.error = f"Metrik: beklenmeyen hata ({exc!r})"
        return result

    try:
        episode = generate_tests(unit, executor, config.rl, agent=agent, seed=seed)
    except SignatureError as exc:
        result.error = f"RL: {exc}"
        return result
    except Exception as exc:  # noqa: BLE001 - Madde-1
        result.error = f"RL: beklenmeyen hata ({exc!r})"
        return result

    tests = episode.tests
    result.test_count = len(tests)
    coverage, execution_time = measure_suite(unit, tests, executor, timeout=config.suite_timeout_s)
    result.coverage = coverage or episode.coverage
    result.stats = RunStats(episode.stats.generated, episode.stats.compiled, execution_time)

    if config.mutation is not None and tests:
        try:
            result.mutation = config.mutation(unit, tests)
        except Exception as exc:  # noqa: BLE001 - Madde-1
            result.error = f"Mutasyon: {exc}"
    if config.prediction is not None:
        try:
            result.prediction = config.prediction(unit, result.metrics, episode)
        except Exception as exc:  # noqa: BLE001 - Madde-1
            result.error = result.error or f"Tahmin: {exc}"
    return result


def run_batch(
    units: Sequence[CodeUnit],
    executor: Executor,
    config: BatchConfig | None = None,
    *,
    progress: Progress | None = None,
    should_stop: StopFlag | None = None,
) -> tuple[list[UnitResult], bool]:
    """Birimleri sırayla çalıştırır; ``(sonuçlar, yarıda_kesildi_mi)`` döner.

    ``should_stop`` her birimden önce sorulur (GUI'deki "Durdur" düğmesi).
    """
    config = config or BatchConfig()
    agent = config.rl.make_agent(seed=config.seed) if config.share_agent else None
    results: list[UnitResult] = []
    for i, unit in enumerate(units):
        if should_stop is not None and should_stop():
            return results, True
        seed = None if config.seed is None else config.seed + i
        result = run_unit(unit, executor, config, agent=agent, seed=seed)
        results.append(result)
        if progress is not None:
            progress(i + 1, len(units), result)
    return results, False


def _write_reports(
    results: Iterable[UnitResult],
    reports_root: Path,
    base_meta: ReportMeta,
    formats: Iterable[str],
    datasets: Iterable[str] = (),
) -> dict[str, list[Path]]:
    """Veri seti başına bir rapor; ``datasets``taki adlar birimi olmasa da raporlanır."""
    by_dataset: dict[str, list[UnitResult]] = {name: [] for name in datasets}
    for result in results:
        by_dataset.setdefault(result.dataset, []).append(result)
    formats = tuple(formats)
    written: dict[str, list[Path]] = {}
    for dataset, items in by_dataset.items():
        meta = replace(base_meta, dataset=dataset)
        out_dir = report_dir(reports_root, dataset, base_meta.created_at)
        written[dataset] = write_report(items, out_dir, meta, formats)
    return written


def _select(
    units: Sequence[CodeUnit], datasets: Iterable[str] | None, limit: int | None
) -> list[CodeUnit]:
    wanted = set(datasets) if datasets else None
    counts: dict[str, int] = {}
    selected: list[CodeUnit] = []
    for unit in units:
        name = unit.dataset or ""
        if wanted is not None and name not in wanted:
            continue
        if limit is not None and counts.get(name, 0) >= limit:
            continue
        counts[name] = counts.get(name, 0) + 1
        selected.append(unit)
    return selected


def run_split(
    split: str,
    executor: Executor,
    config: BatchConfig | None = None,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    reports_root: Path = Path("reports"),
    config_name: str | None = None,
    datasets: Iterable[str] | None = None,
    limit: int | None = None,
    formats: Iterable[str] = FORMATS,
    progress: Progress | None = None,
    should_stop: StopFlag | None = None,
) -> BatchOutcome:
    """``data/splits/<split>.json``'daki birimleri çalıştırır, veri seti bazında rapor yazar.

    ``datasets`` splitin yalnızca bazı veri setlerini, ``limit`` veri seti başına ilk N
    birimi seçer (deneme çalıştırmaları için; ana deney sonuçları tam split ile alınır).

    Raises:
        SplitError, DatasetError: Split ya da ham veri okunamazsa.
        OSError: Rapor yazılamazsa.
    """
    path = split_path(data_dir, split)
    definition = read_split(path)
    wanted = [name for name in definition.units if not datasets or name in set(datasets)]
    units = _select(load_split_units(definition, data_dir), wanted, limit)
    results, stopped = run_batch(
        units, executor, config, progress=progress, should_stop=should_stop
    )
    meta = ReportMeta(
        dataset=split,
        split=split,
        split_hash=sha256_file(path),
        config=config_name,
        created_at=datetime.now(),
    )
    written = _write_reports(results, reports_root, meta, formats, wanted)
    return BatchOutcome(results, written, stopped)


def run_dataset(
    dataset: str,
    executor: Executor,
    config: BatchConfig | None = None,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    reports_root: Path = Path("reports"),
    config_name: str | None = None,
    limit: int | None = None,
    formats: Iterable[str] = FORMATS,
    progress: Progress | None = None,
    should_stop: StopFlag | None = None,
) -> BatchOutcome:
    """Bir veri setinin tamamını split dosyası olmadan çalıştırır (raporda split "-" görünür).

    Raises:
        DatasetError: Veri seti bilinmiyor ya da ham veri okunamazsa.
        OSError: Rapor yazılamazsa.
    """
    units = _select(DatasetFactory.get(dataset, data_dir).load().units, None, limit)
    results, stopped = run_batch(
        units, executor, config, progress=progress, should_stop=should_stop
    )
    meta = ReportMeta(dataset=dataset, config=config_name, created_at=datetime.now())
    written = _write_reports(results, reports_root, meta, formats, [dataset])
    return BatchOutcome(results, written, stopped)
