"""Çağrı Grafiği sayfası (US-1): kodun fonksiyon çağrılarını graf olarak gösterir.

Kaynak, "Kod Yükle" sayfasındaki kod ya da bir HumanEval görevidir. Solda grafik
(yakınlaştırılabilir, PNG olarak kaydedilebilir), sağda düğüm tablosu bulunur; tabloda ya da
grafikte bir düğüm seçilince onunla ilgili düğümler ve çağrılar vurgulanır.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from testzede.gui.pages.analysis_common import AnalysisPage
from testzede.gui.pages.graph_canvas import KIND_STYLES, GraphCanvas
from testzede.gui.state import AppState
from testzede.gui.styles import fix_table_header
from testzede.services.analysis_service import AnalysisService, CallGraphView, GraphNode

PAGE_TITLE = "Çağrı Grafiği"
_KIND_ORDER = {kind: index for index, kind in enumerate(KIND_STYLES)}
# Tabloda dar sütuna sığan kısa tür adları (tam adlar grafiğin göstergesindedir).
KIND_SHORT = {
    "function": "Fonksiyon",
    "builtin": "Yerleşik",
    "external": "Harici",
    "module": "Modül",
}
_SIDE_MIN_WIDTH = 380
_NO_SELECTION = "Ayrıntı için tablodan ya da grafikten bir düğüm seçin."


def node_rows(view: CallGraphView) -> list[GraphNode]:
    """Tablo sırası: önce fonksiyonlar, sonra yerleşik/harici/modül; her grupta ada göre."""
    return sorted(view.nodes, key=lambda n: (_KIND_ORDER.get(n.kind, len(_KIND_ORDER)), n.label))


def summary_text(view: CallGraphView, label: str) -> str:
    """Grafik özeti: kaynak, düğüm türü sayıları, çağrı sayısı ve özyineleme."""
    if not view.nodes:
        return f"Kaynak: {label} · Kodda fonksiyon ya da çağrı yok."
    parts = [
        f"{view.count(kind)} {style.label.lower()}"
        for kind, style in KIND_STYLES.items()
        if view.count(kind)
    ]
    text = f"Kaynak: {label} · {', '.join(parts)} · {len(view.edges)} çağrı"
    recursive = view.recursive
    if recursive:
        text += f" · özyinelemeli: {', '.join(view.node(name).label for name in recursive)}"
    return text


def detail_text(view: CallGraphView, name: str) -> str:
    """Seçili düğümün çağırdıkları ve onu çağıranlar."""
    node = view.node(name)

    def names(items: tuple[str, ...]) -> str:
        labels = sorted(view.node(item).label for item in items if item != name)
        return ", ".join(labels) if labels else "yok"

    text = f"{node.label}: çağırdıkları: {names(node.calls)} · çağıranlar: {names(node.called_by)}"
    return text + (" · kendini çağırıyor (özyineleme)" if node.recursive else "")


class CallGraphPage(AnalysisPage):
    """Kodun çağrı grafiğini çizer ve düğümleri tabloda listeler."""

    def __init__(
        self,
        state: AppState,
        service: AnalysisService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(PAGE_TITLE, "Grafiği Oluştur", state, service, parent)
        self._view: CallGraphView | None = None
        self._rows: list[GraphNode] = []

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.canvas = GraphCanvas()
        self.node_table = QTableWidget(0, 4)
        self.node_table.setHorizontalHeaderLabels(["Düğüm", "Tür", "Çağırır", "Çağrılır"])
        self.node_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.node_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.node_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.node_table.verticalHeader().setVisible(False)
        header = self.node_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.node_table.horizontalHeaderItem(2).setToolTip("Bu düğümün çağırdığı düğüm sayısı")
        self.node_table.horizontalHeaderItem(3).setToolTip("Bu düğümü çağıran düğüm sayısı")
        fix_table_header(self.node_table)
        self.detail_label = QLabel(_NO_SELECTION)
        self.detail_label.setWordWrap(True)

        side = QWidget()
        side.setMinimumWidth(_SIDE_MIN_WIDTH)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.addWidget(self.node_table, 1)
        side_layout.addWidget(self.detail_label)
        body = QSplitter(Qt.Orientation.Horizontal)
        body.addWidget(self.canvas)
        body.addWidget(side)
        body.setStretchFactor(0, 3)
        body.setStretchFactor(1, 2)
        body.setSizes([640, 420])
        self.body_layout.addWidget(self.summary_label)
        self.body_layout.addWidget(body, 1)

        self.node_table.itemSelectionChanged.connect(self._on_table_selection)
        self.canvas.node_clicked.connect(self.select_node)
        self._refresh_run_state()

    # --- AnalysisPage kancaları ----------------------------------------------------------------

    def _compute(self, source: str) -> object:
        return self._service.call_graph(source)

    def _render(self, result: object, label: str) -> None:
        view: CallGraphView = result  # type: ignore[assignment]
        self._view = view
        self._rows = node_rows(view)
        self.summary_label.setText(summary_text(view, label))
        self.node_table.blockSignals(True)
        self.node_table.clearSelection()
        self.node_table.setRowCount(len(self._rows))
        for row, node in enumerate(self._rows):
            cells = (
                node.label,
                KIND_SHORT[node.kind],
                str(len([c for c in node.calls if c != node.name])),
                str(len([c for c in node.called_by if c != node.name])),
            )
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(node.name)
                if column >= 2:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.node_table.setItem(row, column, item)
        self.node_table.blockSignals(False)
        self.detail_label.setText(_NO_SELECTION)
        self.canvas.set_view(view)

    # --- seçim ---------------------------------------------------------------------------------

    def select_node(self, name: str) -> None:
        """Düğümü tabloda ve grafikte seçer (grafikte tıklanınca ya da koddan çağrılır)."""
        for row, node in enumerate(self._rows):
            if node.name == name:
                self.node_table.selectRow(row)  # _on_table_selection grafiği günceller
                return

    def _on_table_selection(self) -> None:
        rows = self.node_table.selectionModel().selectedRows()
        if self._view is None or not rows:
            return
        name = self._rows[rows[0].row()].name
        self.canvas.select(name)
        self.detail_label.setText(detail_text(self._view, name))
