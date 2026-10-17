"""RL Test Üretimi sayfası (US-3, US-4).

Sol: test edilecek kod. Sağ: RL'nin ürettiği testler. Alt şerit: Test Case
Statistics, Branch Count, Tested Line Count, Coverage Rate.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from testzede.gui.pages.base import BasePage
from testzede.gui.state import AppState
from testzede.gui.worker import TaskRunner, Worker
from testzede.services import rl_service
from testzede.services.errors import ServiceError

PAGE_TITLE = "RL Test Üretimi"
_MONO_FALLBACKS = ("Menlo", "Consolas", "DejaVu Sans Mono", "Courier New")


def _mono_editor(read_only: bool = False) -> QPlainTextEdit:
    editor = QPlainTextEdit()
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    editor.setFont(font)
    # qt-material fontu stil sayfasıyla ezer; eş aralıklı fontu stil sayfasında da belirt.
    families = ", ".join(f"'{name}'" for name in (font.family(), *_MONO_FALLBACKS))
    editor.setStyleSheet(f"font-family: {families}, monospace;")
    editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    editor.setReadOnly(read_only)
    return editor


class StatTile(QFrame):
    """Alt şeritteki tek istatistik kutusu: başlık + değer + açıklama."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        self.title = QLabel(title)
        self.value = QLabel("-")
        self.value.setObjectName("statValue")
        self.value.setStyleSheet("font-size: 18pt; font-weight: 600;")
        self.detail = QLabel("")
        for label in (self.title, self.value, self.detail):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)

    def set(self, value: str, detail: str = "") -> None:
        self.value.setText(value)
        self.detail.setText(detail)


class RLPage(BasePage):
    """RL ile test üretim sayfası."""

    def __init__(self, state: AppState | None = None, parent: QWidget | None = None) -> None:
        super().__init__(PAGE_TITLE, state if state is not None else AppState(), parent)
        self._tasks = TaskRunner(self)
        self._result: rl_service.GenerationResult | None = None

        self.open_button = QPushButton("Dosya Aç…")
        self.function_box = QComboBox()
        self.function_box.setMinimumContentsLength(20)
        self.generate_button = QPushButton("Testleri Üret")
        self.save_button = QPushButton("Testleri Kaydet…")
        self.save_button.setEnabled(False)
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)  # belirsiz ilerleme
        self.busy.setMaximumWidth(160)
        self.busy.hide()
        self.status = QLabel("Kodu yapıştırın ya da bir .py dosyası açın.")

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.open_button)
        toolbar.addWidget(QLabel("Fonksiyon:"))
        toolbar.addWidget(self.function_box)
        toolbar.addWidget(self.generate_button)
        toolbar.addWidget(self.busy)
        toolbar.addStretch(1)
        toolbar.addWidget(self.save_button)

        self.source_edit = _mono_editor()
        self.source_edit.setPlaceholderText("def f(x):\n    ...")
        self.test_list = QListWidget()
        self.test_view = _mono_editor(read_only=True)
        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(self.test_list)
        right.addWidget(self.test_view)
        right.setSizes([150, 350])
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.source_edit)
        splitter.addWidget(right)
        splitter.setSizes([500, 500])

        self.tile_tests = StatTile("Test Case Statistics")
        self.tile_branches = StatTile("Branch Count")
        self.tile_lines = StatTile("Tested Line Count")
        self.tile_rate = StatTile("Coverage Rate")
        strip = QGridLayout()
        for column, tile in enumerate(
            (self.tile_tests, self.tile_branches, self.tile_lines, self.tile_rate)
        ):
            strip.addWidget(tile, 0, column)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.status)
        layout.addLayout(strip)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(400)
        self._refresh_timer.timeout.connect(self._refresh_functions)
        self.source_edit.textChanged.connect(self._refresh_timer.start)
        self.open_button.clicked.connect(self._open_file)
        self.generate_button.clicked.connect(self._generate)
        self.save_button.clicked.connect(self._save_tests)
        self.test_list.currentRowChanged.connect(self._show_test)
        self._clear_stats()

    # ---- dış kullanım -------------------------------------------------------------

    def set_source(self, source: str) -> None:
        """Kod Yükle sayfası (ya da testler) kodu buradan verir."""
        self.source_edit.setPlainText(source)
        self._refresh_functions()

    def shutdown(self) -> None:
        self._tasks.shutdown()

    # ---- olaylar -----------------------------------------------------------------

    @Slot()
    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Python dosyası aç", "", "Python (*.py)")
        if not path:
            return
        try:
            self.set_source(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            self._error(f"Dosya okunamadı: {exc}")

    @Slot()
    def _refresh_functions(self) -> None:
        current = self.function_box.currentText()
        self.function_box.clear()
        source = self.source_edit.toPlainText()
        if not source.strip():
            self.status.setText("Kodu yapıştırın ya da bir .py dosyası açın.")
            return
        try:
            names = rl_service.list_functions(source)
        except ServiceError as exc:
            self.status.setText(str(exc))
            return
        self.function_box.addItems(names)
        if current in names:
            self.function_box.setCurrentText(current)
        self.status.setText(
            f"{len(names)} test edilebilir fonksiyon bulundu."
            if names
            else "Parametre alan üst düzey bir fonksiyon bulunamadı."
        )

    @Slot()
    def _generate(self) -> None:
        if self._tasks.busy:
            return
        source = self.source_edit.toPlainText()
        entry_point = self.function_box.currentText()
        if not entry_point:
            self._error("Önce test edilecek fonksiyonu seçin.")
            return

        def job(_: Worker) -> rl_service.GenerationResult:
            return rl_service.generate(source, entry_point)

        self._set_busy(True, f"{entry_point} için testler üretiliyor…")
        self._tasks.start(job, on_finished=self._on_finished, on_failed=self._on_failed)

    @Slot(object)
    def _on_finished(self, result: rl_service.GenerationResult) -> None:
        self._set_busy(False, f"{len(result.tests)} test üretildi ({result.steps} adım).")
        self._result = result
        self.test_list.clear()
        self.test_list.addItems([test.name for test in result.tests])
        if result.tests:
            self.test_list.setCurrentRow(0)
        else:
            self.test_view.setPlainText("")
        self.save_button.setEnabled(bool(result.tests))
        self._show_stats(result)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._set_busy(False, "Üretim başarısız.")
        self._error(message)

    @Slot(int)
    def _show_test(self, row: int) -> None:
        if self._result is None or not 0 <= row < len(self._result.tests):
            self.test_view.setPlainText("")
            return
        self.test_view.setPlainText(self._result.tests[row].code)

    @Slot()
    def _save_tests(self) -> None:
        if self._result is None:
            return
        name = f"test_{self._result.unit.entry_point}.py"
        path, _ = QFileDialog.getSaveFileName(self, "Testleri kaydet", name, "Python (*.py)")
        if not path:
            return
        try:
            Path(path).write_text(rl_service.tests_module(self._result), encoding="utf-8")
        except OSError as exc:
            self._error(f"Dosya yazılamadı: {exc}")
            return
        self.status.setText(f"Kaydedildi: {path} (test edilen kod yanında target.py olmalı)")

    # ---- yardımcılar -------------------------------------------------------------

    def _set_busy(self, busy: bool, message: str) -> None:
        self.busy.setVisible(busy)
        for widget in (self.generate_button, self.open_button, self.function_box):
            widget.setEnabled(not busy)
        self.source_edit.setReadOnly(busy)
        self.status.setText(message)

    def _clear_stats(self) -> None:
        for tile in (self.tile_tests, self.tile_branches, self.tile_lines, self.tile_rate):
            tile.set("-")

    def _show_stats(self, result: rl_service.GenerationResult) -> None:
        stats = result.stats
        self.tile_tests.set(
            str(len(result.tests)),
            f"üretilen {stats.generated}, derlenen {stats.compiled} "
            f"(%{stats.compilation_rate * 100:.0f})",
        )
        cov = result.coverage
        if cov is None:
            for tile in (self.tile_branches, self.tile_lines, self.tile_rate):
                tile.set("-", "ölçülemedi")
            return
        self.tile_branches.set(f"{cov.covered_branches} / {cov.total_branches}", "kapsanan")
        self.tile_lines.set(f"{cov.covered_lines} / {cov.total_lines}", "kapsanan")
        branch = f", branch %{result.branch_rate * 100:.0f}" if cov.total_branches else ""
        self.tile_rate.set(f"%{cov.line_rate * 100:.0f}", f"satır{branch}")

    def _error(self, message: str) -> None:
        QMessageBox.warning(self, self.title, message)
