"""Çağrı grafiği ve kod metrikleri cephesi (Facade): "Çağrı Grafiği" ve "Metrikler" sayfaları
bunu kullanır (US-1, US-2).

GUI ``analysis`` ve ``datasets`` modüllerini doğrudan çağırmaz; bu cephe sonuçları, çizim
için hazır (yerleşimi hesaplanmış) ve ``networkx``/``radon`` türlerinden bağımsız veri
sınıflarına çevirir. Kullanıcı kaynaklı her hata ``ServiceError`` olarak döner; mesajı
doğrudan arayüzde gösterilebilir.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import networkx as nx

from testzede.analysis.callgraph import (
    BUILTIN_PREFIX,
    EXTERNAL_PREFIX,
    CallGraphError,
    build_call_graph,
)
from testzede.analysis.metrics import (
    METRIC_DESCRIPTIONS,
    METRIC_NAMES,
    MetricsError,
    compute_metrics,
    maintainability_rank,
)
from testzede.datasets.base import DEFAULT_DATA_DIR, raw_dir
from testzede.datasets.errors import DatasetError
from testzede.datasets.factory import DatasetFactory
from testzede.services.errors import ServiceError

__all__ = [
    "AnalysisService",
    "CallGraphView",
    "GraphNode",
    "MetricRow",
    "MetricsView",
    "SampleTask",
]

NodeKind = Literal["function", "builtin", "external", "module"]

EMPTY_SOURCE_MESSAGE = (
    "Kaynak kod boş. Önce 'Kod Yükle' sayfasında kod yükleyin ya da bir HumanEval görevi seçin."
)

# Yerleşim aralıkları (veri koordinatları): düğümler aynı katmanda yan yana, katmanlar alt alta.
_X_SPACING = 1.6
_Y_SPACING = 1.0

# Tam sayı olarak gösterilen metrikler; diğerleri iki ondalıkla.
_INTEGER_METRICS = frozenset(
    {
        "LOC",
        "LLOC",
        "SLOC",
        "Yorum",
        "Çoklu Satır",
        "Boş Satır",
        "Halstead Uzunluk",
        "Halstead Kelime Haznesi",
        "Çevrimsel Karmaşıklık",
    }
)
_MAINTAINABILITY = "Sürdürülebilirlik İndeksi"

RANK_MEANINGS = {"A": "yüksek", "B": "orta", "C": "düşük"}


# ---- çağrı grafiği -------------------------------------------------------------------


@dataclass(frozen=True)
class GraphNode:
    """Çizilmeye hazır bir düğüm: konumu ve komşuları hesaplanmıştır."""

    name: str
    kind: NodeKind
    layer: int  # 0: hiçbir fonksiyon tarafından çağrılmayan (en üst) katman
    x: float
    y: float
    calls: tuple[str, ...]  # bu düğümün çağırdıkları (özyineleme varsa kendisi de)
    called_by: tuple[str, ...]  # bu düğümü çağıranlar

    @property
    def label(self) -> str:
        """Çizimde gösterilen kısa ad (``<builtin>.len`` → ``len``)."""
        if self.kind == "builtin":
            return self.name.removeprefix(BUILTIN_PREFIX)
        if self.kind == "external":
            return self.name.removeprefix(EXTERNAL_PREFIX)
        return self.name

    @property
    def recursive(self) -> bool:
        """Kendini çağırıyor mu."""
        return self.name in self.calls


@dataclass(frozen=True)
class CallGraphView:
    """Bir kodun çağrı grafiği (yerleşimi hesaplanmış, ``networkx``'ten bağımsız)."""

    nodes: tuple[GraphNode, ...]
    edges: tuple[tuple[str, str], ...]  # (çağıran, çağrılan)

    def node(self, name: str) -> GraphNode:
        """Adı verilen düğüm.

        Raises:
            KeyError: Böyle bir düğüm yoksa.
        """
        for node in self.nodes:
            if node.name == name:
                return node
        raise KeyError(name)

    def count(self, kind: str) -> int:
        """Verilen türdeki düğüm sayısı."""
        return sum(1 for node in self.nodes if node.kind == kind)

    @property
    def recursive(self) -> tuple[str, ...]:
        """Özyinelemeli (kendini çağıran) düğümlerin adları."""
        return tuple(node.name for node in self.nodes if node.recursive)


def _layout(graph: nx.DiGraph) -> dict[str, tuple[int, float, float]]:
    """Katmanlı (çağıranlar üstte) ve tekrarlanabilir yerleşim: ``ad -> (katman, x, y)``.

    Katman, uzun yol katmanlamasıdır (döngüler tek düğüm sayılır). Her katmandaki
    sıralama, çağıranların ortalama konumuna göre yapılır (kenar kesişimini azaltır);
    eşitlikte ada göre sıralanır. Rastgelelik yoktur.
    """
    if graph.number_of_nodes() == 0:
        return {}
    condensed = nx.condensation(graph)
    layer_of: dict[str, int] = {}
    for layer, generation in enumerate(nx.topological_generations(condensed)):
        for component in generation:
            for member in condensed.nodes[component]["members"]:
                layer_of[member] = layer
    layers: dict[int, list[str]] = defaultdict(list)
    for name in sorted(layer_of):
        layers[layer_of[name]].append(name)

    x_of: dict[str, float] = {}
    result: dict[str, tuple[int, float, float]] = {}

    def barycenter(name: str) -> float:
        """Üst katmanlardaki çağıranların ortalama x konumu (çağıranı yoksa sonsuz)."""
        xs = [
            x_of[p] for p in graph.predecessors(name) if p in x_of and layer_of[p] < layer_of[name]
        ]
        return sum(xs) / len(xs) if xs else float("inf")

    for layer in sorted(layers):
        names = layers[layer]
        ordered = sorted(names, key=lambda name: (barycenter(name), name)) if layer else names
        for index, name in enumerate(ordered):
            x = (index - (len(ordered) - 1) / 2) * _X_SPACING
            x_of[name] = x
            result[name] = (layer, x, -layer * _Y_SPACING)
    return result


# ---- metrikler -----------------------------------------------------------------------


@dataclass(frozen=True)
class MetricRow:
    """Metrikler tablosunun bir satırı."""

    name: str
    value: float
    text: str  # arayüzde ve CSV'de gösterilen biçim (sayılar tam, diğerleri iki ondalık)
    description: str


@dataclass(frozen=True)
class MetricsView:
    """Bir kodun 14 metriği ve sürdürülebilirlik derecesi."""

    rows: tuple[MetricRow, ...]
    maintainability_rank: str  # "A", "B" ya da "C"

    def value(self, name: str) -> float:
        """Adı verilen metriğin değeri.

        Raises:
            KeyError: Böyle bir metrik yoksa.
        """
        for row in self.rows:
            if row.name == name:
                return row.value
        raise KeyError(name)

    @property
    def maintainability_text(self) -> str:
        """``"A (yüksek)"`` gibi okunur derece."""
        return f"{self.maintainability_rank} ({RANK_MEANINGS[self.maintainability_rank]})"


def format_metric(name: str, value: float) -> str:
    """Metrik değerini gösterim metnine çevirir."""
    if name in _INTEGER_METRICS:
        return str(round(value))
    return f"{value:.2f}"


# ---- örnek görevler ------------------------------------------------------------------


@dataclass(frozen=True)
class SampleTask:
    """Seçilebilir bir HumanEval görevi."""

    uid: str  # "HumanEval/12"
    entry_point: str
    source: str

    @property
    def label(self) -> str:
        return f"{self.uid} · {self.entry_point}"


# ---- cephe ---------------------------------------------------------------------------


class AnalysisService:
    """Çağrı grafiği, metrikler ve örnek görevler için GUI cephesi."""

    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR) -> None:
        self.data_dir = Path(data_dir)

    def call_graph(self, source: str) -> CallGraphView:
        """Kodun çağrı grafiğini çizime hazır olarak üretir.

        Raises:
            ServiceError: Kod boşsa ya da ayrıştırılamıyorsa.
        """
        _require_source(source)
        try:
            graph = build_call_graph(source)
        except CallGraphError as exc:
            raise ServiceError(f"Çağrı grafiği çıkarılamadı: {exc}") from exc
        placed = _layout(graph)
        nodes = []
        for name in sorted(placed, key=lambda n: (placed[n][0], placed[n][1], n)):
            layer, x, y = placed[name]
            nodes.append(
                GraphNode(
                    name=name,
                    kind=graph.nodes[name]["kind"],
                    layer=layer,
                    x=x,
                    y=y,
                    calls=tuple(sorted(graph.successors(name))),
                    called_by=tuple(sorted(graph.predecessors(name))),
                )
            )
        return CallGraphView(tuple(nodes), tuple(sorted(graph.edges)))

    def metrics(self, source: str) -> MetricsView:
        """Kodun 14 metriğini açıklamalarıyla üretir.

        Raises:
            ServiceError: Kod boşsa ya da ayrıştırılamıyorsa.
        """
        _require_source(source)
        try:
            values = compute_metrics(source).values
        except MetricsError as exc:
            raise ServiceError(f"Metrikler hesaplanamadı: {exc}") from exc
        rows = tuple(
            MetricRow(
                name, values[name], format_metric(name, values[name]), METRIC_DESCRIPTIONS[name]
            )
            for name in METRIC_NAMES
        )
        return MetricsView(rows, maintainability_rank(values[_MAINTAINABILITY]))

    @staticmethod
    def metrics_csv(view: MetricsView) -> str:
        """Metrikleri ``Metrik,Değer,Açıklama`` başlıklı CSV metni olarak döndürür."""
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["Metrik", "Değer", "Açıklama"])
        for row in view.rows:
            writer.writerow([row.name, row.text, row.description])
        return buffer.getvalue()

    def export_metrics_csv(self, view: MetricsView, path: Path) -> Path:
        """Metrikleri CSV dosyasına yazar (``utf-8-sig``: Excel Türkçe karakterleri doğru açar).

        Raises:
            ServiceError: Dosya yazılamazsa.
        """
        path = Path(path)
        try:
            path.write_text(self.metrics_csv(view), encoding="utf-8-sig", newline="")
        except OSError as exc:
            raise ServiceError(f"CSV dosyası yazılamadı: {path} ({exc})") from exc
        return path

    def humaneval_available(self) -> bool:
        """HumanEval verisi diskte var mı (``testzede download`` ile indirilir)."""
        return (raw_dir(self.data_dir, "humaneval") / "test.parquet").is_file()

    def humaneval_tasks(self) -> Sequence[SampleTask]:
        """HumanEval görevlerini (``prompt + canonical_solution`` kaynaklı) yükler.

        Raises:
            ServiceError: Veri indirilmemişse ya da okunamıyorsa.
        """
        try:
            units = DatasetFactory.get("humaneval", self.data_dir).load().units
        except DatasetError as exc:
            raise ServiceError(str(exc)) from exc
        return [SampleTask(unit.uid, unit.entry_point or "", unit.source) for unit in units]


def _require_source(source: str) -> None:
    if not source.strip():
        raise ServiceError(EMPTY_SOURCE_MESSAGE)
