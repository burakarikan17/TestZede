"""Çağrı grafiğini çizen matplotlib bileşeni (Qt'ye gömülü, açık/koyu temaya uyumlu).

Çizim (:func:`draw_call_graph`) Qt'den bağımsızdır ve ``CallGraphView``'ı olduğu gibi
çizer; yerleşim servis katmanında hesaplanmıştır. Düğüm türleri hem renkle hem şekille
ayırt edilir (renk körlüğü için Okabe-Ito paleti). Bir düğüm seçilince onunla ilgili
düğüm ve kenarlar vurgulanır, diğerleri sönükleştirilir.

Fare tekerleği yoktur; yakınlaştırma/kaydırma/kaydetme matplotlib araç çubuğundandır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from matplotlib.axes import Axes
from matplotlib.backend_bases import MouseEvent
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from testzede.gui.styles import is_dark_theme
from testzede.services.analysis_service import CallGraphView, GraphNode

PLACEHOLDER = "Grafik için bir kod seçip 'Grafiği Oluştur'a basın."
EMPTY_GRAPH = "Kodda fonksiyon ya da çağrı yok."
_CLICK_RADIUS_PX = 18.0
_NODE_SIZE = 260
_DIM_ALPHA = 0.25
_PAD_X, _PAD_Y = 1.1, 0.75


@dataclass(frozen=True)
class GraphPalette:
    """Temaya göre değişen renkler."""

    background: str
    text: str
    edge: str
    highlight: str
    outline: str


LIGHT = GraphPalette("#ffffff", "#1f1f1f", "#6b6b6b", "#d32f2f", "#ffffff")
DARK = GraphPalette("#232629", "#eaeaea", "#a8a8a8", "#ff8a80", "#232629")


@dataclass(frozen=True)
class KindStyle:
    """Bir düğüm türünün gösterimi: açıklama, işaret şekli ve rengi."""

    label: str
    marker: str
    color: str


KIND_STYLES: dict[str, KindStyle] = {
    "function": KindStyle("Fonksiyon", "o", "#0072B2"),
    "builtin": KindStyle("Yerleşik (builtin)", "s", "#E69F00"),
    "external": KindStyle("Harici (import)", "D", "#CC79A7"),
    "module": KindStyle("Modül düzeyi", "^", "#009E73"),
}


def palette_for(dark: bool) -> GraphPalette:
    """Açık ya da koyu tema paleti."""
    return DARK if dark else LIGHT


def _focus(view: CallGraphView, selected: str | None) -> set[str] | None:
    """Seçili düğüm ve komşuları; seçim yoksa (ya da geçersizse) ``None``."""
    if selected is None:
        return None
    try:
        node = view.node(selected)
    except KeyError:
        return None
    return {node.name, *node.calls, *node.called_by}


def _limits(nodes: tuple[GraphNode, ...]) -> tuple[float, float, float, float]:
    xs = [n.x for n in nodes]
    ys = [n.y for n in nodes]
    return min(xs) - _PAD_X, max(xs) + _PAD_X, min(ys) - _PAD_Y, max(ys) + _PAD_Y


def draw_call_graph(
    ax: Axes,
    view: CallGraphView | None,
    *,
    dark: bool,
    selected: str | None = None,
    keep_limits: bool = False,
) -> None:
    """Çağrı grafiğini ``ax`` üzerine çizer.

    Args:
        view: Çizilecek grafik; ``None`` ise yönlendirme metni gösterilir.
        dark: Koyu tema renkleri kullanılsın mı.
        selected: Vurgulanacak düğümün adı.
        keep_limits: ``True`` ise mevcut yakınlaştırma/kaydırma korunur.
    """
    palette = palette_for(dark)
    previous = (ax.get_xlim(), ax.get_ylim()) if keep_limits else None
    ax.clear()
    ax.set_axis_off()
    ax.figure.set_facecolor(palette.background)
    ax.set_facecolor(palette.background)

    if view is None or not view.nodes:
        message = PLACEHOLDER if view is None else EMPTY_GRAPH
        ax.text(
            0.5, 0.5, message, transform=ax.transAxes, ha="center", va="center", color=palette.text
        )
        return

    focus = _focus(view, selected)
    positions = {n.name: (n.x, n.y) for n in view.nodes}
    _draw_edges(ax, view, positions, palette, selected if focus is not None else None)
    _draw_nodes(ax, view, palette, focus, selected)
    _draw_legend(ax, view, palette)

    if previous is not None:
        ax.set_xlim(previous[0])
        ax.set_ylim(previous[1])
    else:
        x0, x1, y0, y1 = _limits(view.nodes)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)


def _draw_edges(
    ax: Axes,
    view: CallGraphView,
    positions: dict[str, tuple[float, float]],
    palette: GraphPalette,
    selected: str | None,
) -> None:
    for caller, callee in view.edges:
        active = selected is None or selected in (caller, callee)
        color = palette.highlight if selected is not None and active else palette.edge
        common = {
            "arrowstyle": "-|>",
            "mutation_scale": 14,
            "color": color,
            "linewidth": 2.0 if selected is not None and active else 1.2,
            "alpha": 1.0 if active else _DIM_ALPHA,
            "zorder": 2 if active else 1,
        }
        if caller == callee:  # özyineleme: düğümün üstünde küçük bir halka
            x, y = positions[caller]
            patch = FancyArrowPatch(
                (x - 0.13, y + 0.06),
                (x + 0.13, y + 0.06),
                connectionstyle="arc3,rad=-2.4",
                shrinkA=0,
                shrinkB=0,
                **common,
            )
        else:
            patch = FancyArrowPatch(
                positions[caller],
                positions[callee],
                connectionstyle="arc3,rad=0.06",
                shrinkA=12,
                shrinkB=12,
                **common,
            )
        ax.add_patch(patch)


def _draw_nodes(
    ax: Axes,
    view: CallGraphView,
    palette: GraphPalette,
    focus: set[str] | None,
    selected: str | None,
) -> None:
    for kind, style in KIND_STYLES.items():
        for dimmed in (False, True):
            group = [
                n
                for n in view.nodes
                if n.kind == kind and (focus is not None and n.name not in focus) == dimmed
            ]
            if not group:
                continue
            ax.scatter(
                [n.x for n in group],
                [n.y for n in group],
                s=_NODE_SIZE,
                marker=style.marker,
                c=style.color,
                edgecolors=palette.outline,
                linewidths=1.2,
                alpha=_DIM_ALPHA if dimmed else 1.0,
                zorder=3,
            )
            for n in group:
                ax.annotate(
                    n.label,
                    (n.x, n.y),
                    xytext=(0, -15),
                    textcoords="offset points",
                    ha="center",
                    va="top",
                    fontsize=9,
                    color=palette.text,
                    alpha=_DIM_ALPHA + 0.15 if dimmed else 1.0,
                    zorder=5,
                )
    if focus is not None and selected is not None:
        node = view.node(selected)
        ax.scatter(
            [node.x],
            [node.y],
            s=_NODE_SIZE * 2.4,
            facecolors="none",
            edgecolors=palette.highlight,
            linewidths=2.5,
            zorder=4,
        )


def _draw_legend(ax: Axes, view: CallGraphView, palette: GraphPalette) -> None:
    handles = [
        Line2D(
            [],
            [],
            marker=style.marker,
            linestyle="",
            markersize=8,
            markerfacecolor=style.color,
            markeredgecolor=palette.outline,
            label=style.label,
        )
        for kind, style in KIND_STYLES.items()
        if view.count(kind) > 0
    ]
    ax.legend(
        handles=handles,
        loc="upper right",
        fontsize=8,
        frameon=True,
        facecolor=palette.background,
        edgecolor=palette.edge,
        labelcolor=palette.text,
    )


def nearest_node(
    ax: Axes, view: CallGraphView, x: float, y: float, radius: float = _CLICK_RADIUS_PX
) -> str | None:
    """Ekran koordinatındaki (``x``, ``y`` piksel) en yakın düğümün adı; ``radius`` dışındaysa ``None``."""
    best: tuple[float, str] | None = None
    for node in view.nodes:
        px, py = ax.transData.transform((node.x, node.y))
        distance = math.hypot(px - x, py - y)
        if distance <= radius and (best is None or distance < best[0]):
            best = (distance, node.name)
    return best[1] if best else None


class GraphCanvas(QWidget):
    """Araç çubuğu (yakınlaştır, kaydır, PNG kaydet) ve çağrı grafiği tuvali."""

    node_clicked = Signal(str)  # kullanıcı bir düğüme tıkladı

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.figure = Figure(figsize=(6, 4), layout="constrained")
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)
        self._view: CallGraphView | None = None
        self._selected: str | None = None
        self.canvas.mpl_connect("button_press_event", self._on_click)
        self._redraw()

    @property
    def view(self) -> CallGraphView | None:
        """Çizilen grafik (yoksa ``None``)."""
        return self._view

    @property
    def selected(self) -> str | None:
        """Vurgulanan düğümün adı."""
        return self._selected

    def set_view(self, view: CallGraphView | None, selected: str | None = None) -> None:
        """Yeni grafiği çizer (yakınlaştırma sıfırlanır)."""
        self._view = view
        self._selected = selected
        self._redraw()

    def select(self, name: str | None) -> None:
        """Düğümü vurgular (``None`` vurguyu kaldırır); yakınlaştırma korunur."""
        if name == self._selected:
            return
        self._selected = name
        self._redraw(keep_limits=True)

    def _redraw(self, keep_limits: bool = False) -> None:
        draw_call_graph(
            self.axes,
            self._view,
            dark=is_dark_theme(self),
            selected=self._selected,
            keep_limits=keep_limits,
        )
        self.canvas.draw_idle()

    def _on_click(self, event: MouseEvent) -> None:
        if self._view is None or event.inaxes is not self.axes or event.button != 1:
            return
        if self.toolbar.mode:  # yakınlaştırma/kaydırma aracı açıkken tıklama düğüm seçmez
            return
        name = nearest_node(self.axes, self._view, event.x, event.y)
        if name is not None:
            self.node_clicked.emit(name)
