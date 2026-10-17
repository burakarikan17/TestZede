"""Mutasyon sayfası: mutasyon skoru ve hayatta kalan mutantlar."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont, QFontDatabase, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from testzede.domain.models import TestCase
from testzede.gui.pages import mutation_logic as logic
from testzede.gui.pages.base import BasePage
from testzede.gui.state import AppState
from testzede.gui.workers import Worker, run_in_thread
from testzede.mutation.engine import MutationEngine
from testzede.services.mutation_service import MutationService

if TYPE_CHECKING:
    from testzede.mutation.engine import MutationRun

PAGE_TITLE = "Mutasyon"
DEFAULT_MAX_MUTANTS = 100
_WAIT_AT_EXIT_MS = 30_000
_STATUS_COLORS = {"ok": "#69f0ae", "error": "#ff5252", "warn": "#ffab40", "info": ""}
_DIFF_COLORS = {"+": QColor(46, 125, 50, 110), "-": QColor(198, 40, 40, 130)}
_STALE_NOTE = "Not: Kaynak kod veya testler değişti, bu sonuç eski olabilir. Yeniden çalıştırın."

ServiceFactory = Callable[[int], MutationService]


def default_service_factory(max_mutants: int) -> MutationService:
    """Gerçek motorla (en fazla ``max_mutants`` mutant) bir ``MutationService`` kurar."""
    return MutationService(MutationEngine(max_mutants=max_mutants))


class MutationPage(BasePage):
    """Mutasyon analizini arka planda çalıştırır; hayatta kalan mutantları farklarıyla gösterir."""

    run_completed = Signal(bool)  # çalıştırma bitti (True: sonuç var; False: hata)

    def __init__(
        self,
        state: AppState,
        service_factory: ServiceFactory | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(PAGE_TITLE, state, parent)
        self._service_factory = service_factory or default_service_factory
        self._worker: Worker | None = None
        self._thread: QThread | None = None
        self._pending: tuple[str, list[TestCase]] | None = None  # çalışan işin girdisi
        self._cancel_requested = False
        self._last_progress: tuple[int, int] | None = None
        self._shown: MutationRun | None = None  # görünümde gösterilen sonuç
        self._result_source = ""  # sonucun hesaplandığı kaynak
        self._result_tests: list[TestCase] = []  # sonucun hesaplandığı testler
        self._survivors: list = []  # tablo satırlarıyla aynı sırada
        self._showing_problem = False

        self.max_spin = QSpinBox()
        self.max_spin.setRange(1, 1000)
        self.max_spin.setValue(DEFAULT_MAX_MUTANTS)
        self.run_button = QPushButton("Çalıştır")
        self.cancel_button = QPushButton("İptal")
        self.cancel_button.setEnabled(False)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status_label = QLabel("")
        self.note_label = QLabel(_STALE_NOTE)
        self.note_label.setStyleSheet(f"color: {_STATUS_COLORS['warn']};")
        self.note_label.hide()
        self.score_label = QLabel()
        self.killed_label = QLabel()
        self.survived_label = QLabel()
        self.timeout_label = QLabel()
        self.skipped_label = QLabel()
        self.compilation_label = QLabel()
        self.time_label = QLabel()

        self.survivors_table = QTableWidget(0, 3)
        self.survivors_table.setHorizontalHeaderLabels(["Operatör", "Satır", "Açıklama"])
        self.survivors_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.survivors_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.survivors_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.survivors_table.verticalHeader().setVisible(False)
        header = self.survivors_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        self.diff_view = QPlainTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        self.diff_view.setFont(font)
        self.diff_view.setPlaceholderText("Farkı görmek için bir hayatta kalan mutant seçin")

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Maksimum mutant:"))
        controls.addWidget(self.max_spin)
        controls.addWidget(self.run_button)
        controls.addWidget(self.cancel_button)
        controls.addWidget(self.progress_bar, 1)
        summary = QHBoxLayout()
        for label in (
            self.score_label,
            self.killed_label,
            self.survived_label,
            self.timeout_label,
            self.skipped_label,
            self.compilation_label,
            self.time_label,
        ):
            summary.addWidget(label)
        summary.addStretch(1)
        body = QSplitter(Qt.Orientation.Horizontal)
        body.addWidget(self._titled("Hayatta Kalan Mutantlar", self.survivors_table))
        body.addWidget(self._titled("Fark (orijinal → mutant)", self.diff_view))
        body.setStretchFactor(0, 2)
        body.setStretchFactor(1, 3)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addLayout(summary)
        layout.addWidget(self.status_label)
        layout.addWidget(self.note_label)
        layout.addWidget(body, 1)

        self.run_button.clicked.connect(self.run)
        self.cancel_button.clicked.connect(self.cancel)
        self.survivors_table.itemSelectionChanged.connect(self._on_selection_changed)
        app = QApplication.instance()
        if app is not None:  # uygulama kapanırken çalışan iş güvenle durdurulur
            app.aboutToQuit.connect(self._stop_worker)
        self._clear_view()
        self._refresh_run_state()

    # --- çalıştırma ----------------------------------------------------------------------------

    def run(self) -> None:
        """Mutasyon analizini arka planda başlatır; girdi eksikse nedenini gösterir."""
        if self._thread is not None:
            return
        if self._input_problem():
            self._refresh_run_state()
            return
        source, tests = self.state.source, list(self.state.tests)
        service = self._service_factory(self.max_spin.value())

        def job(progress_callback, should_cancel):
            return service.run_detailed(
                source, tests, progress_callback=progress_callback, should_cancel=should_cancel
            )

        self._pending = (source, tests)
        self._cancel_requested = False
        self._last_progress = None
        self.progress_bar.setRange(0, 0)  # taban test koşusu sürerken belirsiz ilerleme
        self.run_button.setEnabled(False)
        self.max_spin.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._set_status("Çalışıyor...", "info")
        worker = Worker(job)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        self._worker = worker
        self._thread = run_in_thread(worker)

    def cancel(self) -> None:
        """Çalışan analizi iptal ister; motor o ana kadarki sonucu döndürür."""
        if self._worker is None:
            return
        self._cancel_requested = True
        self._worker.cancel()
        self.cancel_button.setEnabled(False)
        self._set_status("İptal ediliyor...", "info")

    @Slot(int, int)
    def _on_progress(self, done: int, total: int) -> None:
        """İlerleme çubuğunu günceller."""
        self._last_progress = (done, total)
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(done)

    @Slot(object)
    def _on_finished(self, run: object) -> None:
        """Sonucu (iptalde kısmi sonucu) ``AppState``'e yazar ve görünümü doldurur."""
        self._join_thread()
        source, tests = self._pending or (self.state.source, list(self.state.tests))
        self._pending = None
        progress = self._last_progress
        cancelled = self._cancel_requested and (progress is None or progress[0] < progress[1])
        self.state.mutation_run = run  # type: ignore[assignment]
        self._shown = run  # type: ignore[assignment]
        self._result_source, self._result_tests = source, tests
        self._render(run, source)  # type: ignore[arg-type]
        self._finish_progress(cancelled)
        self._refresh_run_state()
        if cancelled:
            done = progress[0] if progress else 0
            total = f"/{progress[1]}" if progress else ""
            self._set_status(f"İptal edildi. {done}{total} mutant işlendi.", "warn")
        else:
            self._set_status("Tamamlandı.", "ok")
        self._update_note()
        self.run_completed.emit(True)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        """Hatayı (ServiceError ya da beklenmeyen) kırmızı mesajla gösterir."""
        self._join_thread()
        self._pending = None
        self._finish_progress(cancelled=True)
        self._refresh_run_state()
        self._set_status(message, "error")
        self.run_completed.emit(False)

    @Slot()
    def _stop_worker(self) -> None:
        """Uygulama kapanırken çalışan işi iptal eder ve (üst sınırla) bitmesini bekler."""
        if self._thread is not None:
            if self._worker is not None:
                self._worker.cancel()
            self._thread.wait(_WAIT_AT_EXIT_MS)

    def _join_thread(self) -> None:
        """Biten iş parçacığını bekler ve referanslarını bırakır."""
        if self._thread is not None:
            self._thread.wait(5000)
        self._thread = None
        self._worker = None
        self.cancel_button.setEnabled(False)

    def _finish_progress(self, cancelled: bool) -> None:
        """Çalışma bitince ilerleme çubuğunu son durumuna getirir."""
        if self._last_progress is None:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0 if cancelled else 1)
        elif not cancelled:
            done, total = self._last_progress
            self.progress_bar.setRange(0, max(total, 1))
            self.progress_bar.setValue(done)

    # --- sayfa yaşam döngüsü -------------------------------------------------------------------

    def on_enter(self) -> None:
        """Düğme durumunu tazeler; önceki sonucu yeniden çizer, eskiyse not düşer."""
        self._refresh_run_state()
        run = self.state.mutation_run
        if run is not self._shown:  # sonuç başka yerden değişti ya da sıfırlandı
            self._shown = run
            self._result_source, self._result_tests = self.state.source, list(self.state.tests)
            if run is None:
                self._clear_view()
        if run is not None:
            self._render(run, self._result_source)
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
        """Çalışmıyorsa düğmeleri girdi durumuna göre ayarlar ve nedeni gösterir."""
        if self._thread is not None:
            return
        problem = self._input_problem()
        self.run_button.setEnabled(not problem)
        self.max_spin.setEnabled(True)
        self.cancel_button.setEnabled(False)
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

    def _set_summary(self, s: logic.MutationSummary) -> None:
        self.score_label.setText(f"Skor: {s.score}")
        self.killed_label.setText(f"Öldürülen: {s.killed}")
        self.survived_label.setText(f"Hayatta kalan: {s.survived}")
        self.timeout_label.setText(f"Zaman aşımı: {s.timeout}")
        self.skipped_label.setText(f"Atlanan (kapsanmamış): {s.skipped}")
        self.compilation_label.setText(f"Derleme: {s.compilation}")
        self.time_label.setText(f"Test süresi: {s.time}")

    def _clear_view(self) -> None:
        """Sonuç görünümünü boşaltır."""
        self._set_summary(logic.empty_summary())
        self._survivors = []
        self.survivors_table.setRowCount(0)
        self.diff_view.setPlainText("")
        self.diff_view.setExtraSelections([])

    def _render(self, run: MutationRun, source: str) -> None:
        """Özeti ve hayatta kalan mutant tablosunu doldurur."""
        self._set_summary(logic.summary_texts(run))
        self._survivors = logic.sorted_survivors(run)
        rows = logic.survivor_rows(run)
        self.survivors_table.setRowCount(len(rows))
        for i, (operator, line, description) in enumerate(rows):
            line_item = QTableWidgetItem(str(line))
            line_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.survivors_table.setItem(i, 0, QTableWidgetItem(operator))
            self.survivors_table.setItem(i, 1, line_item)
            self.survivors_table.setItem(i, 2, QTableWidgetItem(description))
        self.diff_view.setPlainText("")
        self.diff_view.setExtraSelections([])

    @Slot()
    def _on_selection_changed(self) -> None:
        """Seçilen hayatta kalan mutantın farkını gösterir."""
        rows = self.survivors_table.selectionModel().selectedRows()
        if not rows or rows[0].row() >= len(self._survivors):
            self.diff_view.setPlainText("")
            self.diff_view.setExtraSelections([])
            return
        mutant = self._survivors[rows[0].row()]
        diff = logic.mutant_diff(self._result_source, mutant.source)
        self.diff_view.setPlainText(diff or "Fark yok.")
        selections = []
        document = self.diff_view.document()
        for number, text in enumerate(diff.splitlines()):
            color = _DIFF_COLORS.get(text[:1])
            block = document.findBlockByNumber(number)
            if color is None or not block.isValid():
                continue
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(block)
            selection.format.setBackground(color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selections.append(selection)
        self.diff_view.setExtraSelections(selections)

    @staticmethod
    def _titled(title: str, widget: QWidget) -> QWidget:
        """Widget'ın üstüne başlık etiketi ekler."""
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(title))
        layout.addWidget(widget)
        return box
