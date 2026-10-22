"""Tahmin sayfası (US-7, opsiyonel): tahmini hata sayısı ve optimum test sayısı.

Kaynak, "Kod Yükle" sayfasındaki kod ya da bir HumanEval görevidir. Tahmin Halstead
hacminden (``B = V / 3000``) ve McCabe karmaşıklığından hesaplanır; hesabın girdileri
sonuçla birlikte tabloda gösterilir.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from testzede.gui.pages.analysis_common import AnalysisPage, show_status
from testzede.gui.state import AppState
from testzede.gui.styles import fix_table_header
from testzede.services.analysis_service import AnalysisService, PredictionView

PAGE_TITLE = "Tahmin"


def prediction_rows(view: PredictionView) -> list[tuple[str, str, str]]:
    """Tablo satırları: (ad, değer, açıklama)."""
    return [
        ("Halstead Hacim (V)", f"{view.volume:.2f}", "Programın bilgi miktarı."),
        (
            "Çevrimsel Karmaşıklık",
            f"{view.complexity:.0f}",
            "McCabe: bağımsız yol sayısı (tüm fonksiyonların toplamı).",
        ),
        (
            "Tahmini Hata Sayısı",
            f"{view.estimated_bugs:.3f}",
            "Halstead'e göre teslim edilen hata sayısı: B = V / 3000.",
        ),
        (
            "Optimum Test Sayısı",
            str(view.optimum_test_count),
            "Her bağımsız yolu sınayan en az test sayısı (McCabe).",
        ),
    ]


class PredictionPage(AnalysisPage):
    """Kod metriklerinden tahmini hata ve optimum test sayısını gösterir."""

    def __init__(
        self,
        state: AppState,
        service: AnalysisService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(PAGE_TITLE, "Tahmini Hesapla", state, service, parent)
        self.summary_label = QLabel("")
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Ölçü", "Değer", "Açıklama"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        fix_table_header(self.table)

        self.body_layout.addWidget(self.summary_label)
        self.body_layout.addWidget(self.table, 1)
        self._refresh_run_state()

    # --- AnalysisPage kancaları ----------------------------------------------------------------

    def _compute(self, source: str) -> object:
        return self._service.prediction(source)

    def _render(self, result: object, label: str) -> None:
        view: PredictionView = result  # type: ignore[assignment]
        rows = prediction_rows(view)
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            for column, text in enumerate(row):
                item = QTableWidgetItem(text)
                if column == 1:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if column == 2:
                    item.setToolTip(text)
                self.table.setItem(index, column, item)
        show_status(
            self.summary_label,
            self.colors,
            f"Kaynak: {label} · Yöntem: {view.method}",
            "info",
        )
