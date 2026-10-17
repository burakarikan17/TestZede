"""Coverage sayfası: satır/dal kapsama görünümü (Emma/JaCoCo benzeri)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from testzede.domain.models import TestCase
from testzede.gui.pages import coverage_logic as logic
from testzede.gui.pages.base import BasePage
from testzede.gui.state import AppState
from testzede.gui.styles import apply_monospace, fix_table_header
from testzede.gui.worker import TaskRunner, Worker
from testzede.services.coverage_service import CoverageService

if TYPE_CHECKING:
    from testzede.execution.coverage_runner import ExecutionResult

PAGE_TITLE = "Coverage"
_WAIT_AT_EXIT_MS = 15_000

# Koyu temada okunur, yarı saydam arka planlar.
LINE_COLORS: dict[str, QColor] = {
    "covered": QColor(46, 125, 50, 110),
    "partial": QColor(249, 168, 37, 120),
    "missed": QColor(198, 40, 40, 130),
}
OUTCOME_LABELS = {
    "passed": "Geçti",
    "failed": "Başarısız",
    "error": "Hata",
    "timeout": "Zaman aşımı",
}
OUTCOME_COLORS = {
    "passed": "#69f0ae",
    "failed": "#ff5252",
    "error": "#ff5252",
    "timeout": "#ffab40",
}
_STATUS_COLORS = {"ok": "#69f0ae", "error": "#ff5252", "warn": "#ffab40", "info": ""}
FUNCTION_COLUMN_TIP = (
    "Satır ve dal kapsamasının birleşik yüzdesi (coverage.py). "
    "Üstteki 'Satır' yalnızca satır kapsamasıdır."
)
_STALE_NOTE = "Not: Kaynak kod veya testler değişti, bu sonuç eski olabilir. Yeniden çalıştırın."


def _readonly_table(headers: list[str]) -> QTableWidget:
    """Salt okunur, iki sütunlu tablo oluşturur."""
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    return table


def _cell(text: str, color: str | None = None, right: bool = False) -> QTableWidgetItem:
    """Salt okunur tablo hücresi; isteğe bağlı yazı rengi ve sağa hizalama."""
    item = QTableWidgetItem(text)
    if color:
        item.setForeground(QBrush(QColor(color)))
    if right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


class CoveragePage(BasePage):
    """Yüklenen kod ve testleri arka planda çalıştırıp kapsamayı gösterir."""

    run_completed = Signal(bool)  # çalıştırma bitti (True: başarılı)

    def __init__(
        self,
        state: AppState,
        service: CoverageService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(PAGE_TITLE, state, parent)
        self._service = service if service is not None else CoverageService()
        self._tasks = TaskRunner(self)
        self._running = False
        self._pending: tuple[str, list[TestCase]] | None = None  # çalışan işin girdisi
        self._shown: ExecutionResult | None = None  # görünümde gösterilen sonuç
        self._result_source = ""  # sonucun hesaplandığı kaynak
        self._result_tests: list[TestCase] = []  # sonucun hesaplandığı testler
        self._showing_problem = False

        self.run_button = QPushButton("Çalıştır")
        self.status_label = QLabel("")
        self.lines_label = QLabel()
        self.branches_label = QLabel()
        self.compilation_label = QLabel()
        self.time_label = QLabel()
        self.note_label = QLabel(_STALE_NOTE)
        self.note_label.setStyleSheet(f"color: {_STATUS_COLORS['warn']};")
        self.note_label.hide()

        self.source_view = QPlainTextEdit()
        self.source_view.setReadOnly(True)
        self.source_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        apply_monospace(self.source_view)
        self.function_table = _readonly_table(["Fonksiyon", "Kapsama %"])
        header = self.function_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.function_table.horizontalHeaderItem(1).setToolTip(FUNCTION_COLUMN_TIP)
        self.test_table = _readonly_table(["Test", "Sonuç"])
        fix_table_header(self.function_table)
        fix_table_header(self.test_table)

        top = QHBoxLayout()
        top.addWidget(self.run_button)
        for label in (
            self.lines_label,
            self.branches_label,
            self.compilation_label,
            self.time_label,
        ):
            top.addWidget(label)
        top.addStretch(1)

        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(self._titled("Fonksiyonlar", self.function_table))
        right.addWidget(self._titled("Test Sonuçları", self.test_table))
        body = QSplitter(Qt.Orientation.Horizontal)
        body.addWidget(self.source_view)
        body.addWidget(right)
        body.setStretchFactor(0, 3)
        body.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.status_label)
        layout.addWidget(self.note_label)
        layout.addWidget(body, 1)

        self.run_button.clicked.connect(self.run)
        self._clear_view()
        self._refresh_run_state()

    # --- çalıştırma ----------------------------------------------------------------------------

    def run(self) -> None:
        """Coverage'ı arka planda çalıştırır; girdi eksikse nedenini gösterir."""
        if self._running or self._tasks.busy:
            return
        if self._input_problem():
            self._refresh_run_state()
            return
        source, tests = self.state.source, list(self.state.tests)
        service = self._service

        def job(worker: Worker) -> ExecutionResult:
            return service.run(source, tests)

        self._running = True
        self._pending = (source, tests)
        self.run_button.setEnabled(False)
        self._set_status("Çalışıyor...", "info")
        self._tasks.start(job, on_finished=self._on_finished, on_failed=self._on_failed)

    def shutdown(self) -> None:
        """Pencere kapanırken çalışan iş bitene kadar (üst sınırla) bekler."""
        self._tasks.shutdown(timeout_ms=_WAIT_AT_EXIT_MS)

    @Slot(object)
    def _on_finished(self, result: object) -> None:
        """Başarılı sonucu ``AppState``'e yazar ve görünümü doldurur."""
        self._running = False
        source, tests = self._pending or (self.state.source, list(self.state.tests))
        self._pending = None
        self.state.execution_result = result  # type: ignore[assignment]
        self._shown = result  # type: ignore[assignment]
        self._result_source, self._result_tests = source, tests
        self._render(result, source, tests)  # type: ignore[arg-type]
        self._refresh_run_state()
        self._set_status("Tamamlandı.", "ok")
        self._update_note()
        self.run_completed.emit(True)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        """Hatayı (ServiceError ya da beklenmeyen) kırmızı mesajla gösterir."""
        self._running = False
        self._pending = None
        self._refresh_run_state()
        self._set_status(message, "error")
        self.run_completed.emit(False)

    # --- sayfa yaşam döngüsü -------------------------------------------------------------------

    def on_enter(self) -> None:
        """Düğme durumunu tazeler; önceki sonucu yeniden çizer, eskiyse not düşer."""
        self._refresh_run_state()
        result = self.state.execution_result
        if result is not self._shown:  # sonuç başka yerden değişti ya da sıfırlandı
            self._shown = result
            self._result_source, self._result_tests = self.state.source, list(self.state.tests)
            if result is None:
                self._clear_view()
        if result is not None:
            self._render(result, self._result_source, self._result_tests)
        self._update_note()

    # --- görünüm -------------------------------------------------------------------------------

    def _input_problem(self) -> str:
        """Çalıştırmayı engelleyen eksik girdiyi açıklar; yoksa boş metin."""
        if not self.state.source.strip():
            return "Kaynak kod yok. Önce 'Kod Yükle' sayfasında kaynak kodu yükleyin."
        if not self.state.tests:
            return "Test yok. Önce 'Kod Yükle' sayfasında test kodunu yükleyin."
        return ""

    def _refresh_run_state(self) -> None:
        """Çalışmıyorsa düğmeyi girdi durumuna göre açar/kapatır ve nedeni gösterir."""
        if self._running:
            return
        problem = self._input_problem()
        self.run_button.setEnabled(not problem)
        if problem:
            self._set_status(problem, "warn")
            self._showing_problem = True
        elif self._showing_problem:
            self._set_status("", "info")
            self._showing_problem = False

    def _set_status(self, message: str, kind: str) -> None:
        """Durum mesajını renkli gösterir (ok/error/warn/info)."""
        color = _STATUS_COLORS[kind]
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {color};" if color else "")
        self.status_label.setProperty("status", kind)
        if kind != "warn":
            self._showing_problem = False

    def _update_note(self) -> None:
        """Gösterilen sonuç mevcut kaynak/testlerle uyuşmuyorsa "eski" notunu gösterir."""
        stale = self._shown is not None and (
            self._result_source != self.state.source or self._result_tests != self.state.tests
        )
        self.note_label.setVisible(stale)

    def _set_summary(self, summary: logic.CoverageSummary) -> None:
        self.lines_label.setText(f"Satır: {summary.lines}")
        self.branches_label.setText(f"Dal: {summary.branches}")
        self.compilation_label.setText(f"Derleme: {summary.compilation}")
        self.time_label.setText(f"Süre: {summary.time}")

    def _clear_view(self) -> None:
        """Sonuç görünümünü boşaltır."""
        self._set_summary(logic.empty_summary())
        self.source_view.setPlainText("")
        self.source_view.setExtraSelections([])
        self.function_table.setRowCount(0)
        self.test_table.setRowCount(0)

    def _render(self, result: ExecutionResult, source: str, tests: list[TestCase]) -> None:
        """Özeti, renkli kaynak görünümünü ve iki tabloyu doldurur."""
        self._set_summary(logic.summary(result))
        self._render_source(result, source)

        rows = logic.function_rows(result)
        self.function_table.setRowCount(len(rows))
        for i, (name, percent) in enumerate(rows):
            self.function_table.setItem(i, 0, _cell(name))
            self.function_table.setItem(i, 1, _cell(f"{percent:.1f}%", right=True))

        outcomes = logic.outcome_rows(tests, result)
        self.test_table.setRowCount(len(outcomes))
        for i, (name, outcome) in enumerate(outcomes):
            label = OUTCOME_LABELS.get(outcome, outcome)
            cell = _cell(label, OUTCOME_COLORS.get(outcome))
            cell.setData(Qt.ItemDataRole.UserRole, outcome)
            self.test_table.setItem(i, 0, _cell(name))
            self.test_table.setItem(i, 1, cell)

    def _render_source(self, result: ExecutionResult, source: str) -> None:
        """Satır numaralı kaynağı gösterir; satırları durumuna göre boyar."""
        lines = logic.source_lines(source)
        width = len(str(len(lines)))
        self.source_view.setPlainText(
            "\n".join(f"{n:>{width}} │ {text}" for n, text in enumerate(lines, start=1))
        )
        document = self.source_view.document()
        selections = []
        for number, status in logic.line_statuses(result).items():
            block = document.findBlockByNumber(number - 1)
            if not block.isValid():
                continue
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(block)
            selection.format.setBackground(LINE_COLORS[status])
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selections.append(selection)
        self.source_view.setExtraSelections(selections)

    @staticmethod
    def _titled(title: str, widget: QWidget) -> QWidget:
        """Widget'ın üstüne başlık etiketi ekler."""
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(title))
        layout.addWidget(widget)
        return box
