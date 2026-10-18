"""Metrikler sayfası (US-2): kodun 14 metriğini açıklamalarıyla tabloda gösterir.

Kaynak, "Kod Yükle" sayfasındaki kod ya da bir HumanEval görevidir. Sürdürülebilirlik
indeksi harf derecesiyle (A/B/C) renkli gösterilir; tablo CSV olarak dışa aktarılabilir.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from testzede.gui.pages.analysis_common import AnalysisPage, show_status
from testzede.gui.state import AppState
from testzede.gui.styles import fix_table_header
from testzede.services.analysis_service import AnalysisService, MetricsView
from testzede.services.errors import ServiceError

PAGE_TITLE = "Metrikler"
DEFAULT_CSV_NAME = "metrikler.csv"
# Derece -> hücre yazı rengi (``styles.status_colors``) ve durum etiketi türü.
_RANK_COLOR = {"A": "ok", "B": "warning", "C": "error"}
_RANK_KIND = {"A": "ok", "B": "warn", "C": "error"}
_MAINTAINABILITY = "Sürdürülebilirlik İndeksi"


class MetricsPage(AnalysisPage):
    """14 kod metriğini tablo olarak gösterir ve CSV'ye aktarır."""

    def __init__(
        self,
        state: AppState,
        service: AnalysisService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(PAGE_TITLE, "Metrikleri Hesapla", state, service, parent)
        self._view: MetricsView | None = None

        self.export_button = QPushButton("CSV'ye Aktar…")
        self.export_button.setEnabled(False)
        self.summary_label = QLabel("")
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Metrik", "Değer", "Açıklama"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        fix_table_header(self.table)

        bar = QHBoxLayout()
        bar.addWidget(self.summary_label, 1)
        bar.addWidget(self.export_button)
        self.body_layout.addLayout(bar)
        self.body_layout.addWidget(self.table, 1)

        self.export_button.clicked.connect(self.export_dialog)
        self._refresh_run_state()

    # --- AnalysisPage kancaları ----------------------------------------------------------------

    def _compute(self, source: str) -> object:
        return self._service.metrics(source)

    def _render(self, result: object, label: str) -> None:
        view: MetricsView = result  # type: ignore[assignment]
        self._view = view
        self.table.setRowCount(len(view.rows))
        for index, row in enumerate(view.rows):
            name_item = QTableWidgetItem(row.name)
            value_item = QTableWidgetItem(row.text)
            value_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            description_item = QTableWidgetItem(row.description)
            description_item.setToolTip(row.description)
            if row.name == _MAINTAINABILITY:
                value_item.setText(f"{row.text}  ({view.maintainability_rank})")
                color = self.colors[_RANK_COLOR[view.maintainability_rank]]
                value_item.setForeground(QBrush(color.fg))
            for column, item in enumerate((name_item, value_item, description_item)):
                self.table.setItem(index, column, item)
        show_status(
            self.summary_label,
            self.colors,
            f"Kaynak: {label} · Sürdürülebilirlik: {view.maintainability_text}",
            _RANK_KIND[view.maintainability_rank],
        )
        self.export_button.setEnabled(True)

    # --- CSV -----------------------------------------------------------------------------------

    def export_csv(self, path: Path) -> bool:
        """Gösterilen metrikleri CSV'ye yazar; hatayı sayfada gösterir (``False``)."""
        if self._view is None:
            return False
        try:
            self._service.export_metrics_csv(self._view, Path(path))
        except ServiceError as exc:
            self._set_status(str(exc), "error")
            return False
        self._set_status(f"CSV kaydedildi: {path}", "ok")
        return True

    def export_dialog(self) -> None:
        """Kayıt yerini seçtirir ve CSV'yi yazar; iptal edilirse bir şey yapmaz."""
        name, _ = QFileDialog.getSaveFileName(
            self, "Metrikleri CSV olarak kaydet", DEFAULT_CSV_NAME, "CSV (*.csv)"
        )
        if name:
            self.export_csv(Path(name))
