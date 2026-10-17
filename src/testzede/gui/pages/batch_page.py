"""Toplu Test sayfası (US-6): hedef seçimi, ilerleme çubuğu, sonuç tablosu ve rapor."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from testzede.gui.pages.base import BasePage
from testzede.gui.state import AppState
from testzede.gui.worker import TaskRunner, Worker
from testzede.services import batch_service
from testzede.services.batch_service import FORMATS, BatchOutcome, UnitResult

PAGE_TITLE = "Toplu Test"

COLUMNS = (
    "Birim",
    "Durum",
    "Test",
    "Satır %",
    "Branch %",
    "Derlenme %",
    "Süre (s)",
    "Hata",
)


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}"


def _row(result: UnitResult) -> list[str]:
    cov, stats = result.coverage, result.stats
    branch = cov.covered_branches / cov.total_branches if cov and cov.total_branches else None
    compile_rate = stats.compilation_rate if stats and stats.generated else None
    return [
        result.uid,
        "hata" if result.error else "tamam",
        str(result.test_count),
        _percent(cov.line_rate if cov else None),
        _percent(branch),
        _percent(compile_rate),
        f"{stats.execution_time_s:.2f}" if stats else "-",
        result.error or "",
    ]


class BatchPage(BasePage):
    """Toplu test sayfası."""

    def __init__(
        self,
        state: AppState | None = None,
        parent: QWidget | None = None,
        *,
        data_dir: Path = Path("data"),
        reports_root: Path = Path("reports"),
    ) -> None:
        super().__init__(PAGE_TITLE, state if state is not None else AppState(), parent)
        self.data_dir = data_dir
        self.reports_root = reports_root
        self._tasks = TaskRunner(self)
        self._report_dir: Path | None = None
        self._failed = 0
        self._stopping = False

        self.target_box = QComboBox()
        self.refresh_button = QPushButton("Yenile")
        self.limit_box = QSpinBox()
        self.limit_box.setRange(0, 100_000)
        self.limit_box.setSpecialValueText("tümü")
        self.limit_box.setToolTip("Veri seti başına ilk N birim (deneme çalıştırmaları için)")
        self.format_checks = {name: QCheckBox(name.upper()) for name in FORMATS}
        for check in self.format_checks.values():
            check.setChecked(True)
        self.start_button = QPushButton("Başlat")
        self.stop_button = QPushButton("Durdur")
        self.stop_button.setEnabled(False)
        self.open_button = QPushButton("Rapor Klasörünü Aç")
        self.open_button.setEnabled(False)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Hedef:"))
        controls.addWidget(self.target_box, 1)
        controls.addWidget(self.refresh_button)
        controls.addWidget(QLabel("Birim sınırı:"))
        controls.addWidget(self.limit_box)
        for check in self.format_checks.values():
            controls.addWidget(check)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)

        self.progress = QProgressBar()
        self.progress.setFormat("%v / %m")
        self.status = QLabel("Bir hedef seçip Başlat'a basın.")
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        # qt-material başlıkları büyük harfe çevirir; içerik genişliği bunu hesaba katmaz.
        header.setMinimumSectionSize(140)
        header.setStretchLastSection(True)

        footer = QHBoxLayout()
        footer.addWidget(self.status, 1)
        footer.addWidget(self.open_button)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.progress)
        layout.addWidget(self.table, 1)
        layout.addLayout(footer)

        self.refresh_button.clicked.connect(self.refresh_targets)
        self.start_button.clicked.connect(self._start)
        self.stop_button.clicked.connect(self._stop)
        self.open_button.clicked.connect(self._open_reports)
        self.refresh_targets()

    # ---- dış kullanım -------------------------------------------------------------

    @Slot()
    def refresh_targets(self) -> None:
        """Diskteki split ve veri setlerini yeniden tarar; bulunamayanlar seçilemez."""
        current = self.target_box.currentData()
        self.target_box.clear()
        first_available = -1
        for target in batch_service.targets(self.data_dir):
            self.target_box.addItem(target.label, target)
            index = self.target_box.count() - 1
            if not target.available:
                self.target_box.model().item(index).setEnabled(False)
            elif first_available < 0:
                first_available = index
            if current is not None and target.name == current.name and target.available:
                first_available = index
        if first_available >= 0:
            self.target_box.setCurrentIndex(first_available)
        self.start_button.setEnabled(first_available >= 0 and not self._tasks.busy)
        if first_available < 0:
            self.status.setText(
                "Veri bulunamadı. Önce 'testzede download' ve 'testzede make-splits' çalıştırın."
            )

    def shutdown(self) -> None:
        self._tasks.shutdown(timeout_ms=60_000)

    # ---- olaylar -----------------------------------------------------------------

    @Slot()
    def _start(self) -> None:
        target = self.target_box.currentData()
        if self._tasks.busy or target is None or not target.available:
            return
        formats = [name for name, check in self.format_checks.items() if check.isChecked()]
        if not formats:
            QMessageBox.warning(self, self.title, "En az bir rapor biçimi seçin.")
            return
        limit = self.limit_box.value() or None
        data_dir, reports_root = self.data_dir, self.reports_root

        def job(worker: Worker) -> BatchOutcome:
            return batch_service.run(
                target,
                data_dir=data_dir,
                reports_root=reports_root,
                limit=limit,
                formats=formats,
                progress=lambda done, total, result: worker.report((done, total, result)),
                should_stop=worker.stop_requested,
            )

        self.table.setRowCount(0)
        self.progress.setRange(0, 0)
        self._failed = 0
        self._stopping = False
        self._set_running(True, f"{target.name}: birimler yükleniyor…")
        self._tasks.start(
            job,
            on_finished=self._on_finished,
            on_failed=self._on_failed,
            on_progress=self._on_progress,
        )

    @Slot()
    def _stop(self) -> None:
        self._stopping = True
        self._tasks.request_stop()
        self.stop_button.setEnabled(False)
        self.status.setText("Durduruluyor: mevcut birim bitince çalıştırma kesilecek…")

    @Slot(object)
    def _on_progress(self, value: tuple[int, int, UnitResult]) -> None:
        done, total, result = value
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self._failed += bool(result.error)
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, text in enumerate(_row(result)):
            item = QTableWidgetItem(text)
            if column not in (0, 1, len(COLUMNS) - 1):
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, column, item)
        self.table.scrollToBottom()
        if not self._stopping:  # durdurma mesajı ekranda kalsın
            self.status.setText(f"{done}/{total} birim, {self._failed} hatalı · son: {result.uid}")

    @Slot(object)
    def _on_finished(self, outcome: BatchOutcome) -> None:
        paths = [path for items in outcome.reports.values() for path in items]
        self._report_dir = paths[0].parent.parent if paths else None
        failed = sum(1 for r in outcome.results if r.error)
        prefix = "Durduruldu" if outcome.stopped else "Bitti"
        where = f" Raporlar: {self._report_dir}" if self._report_dir else ""
        self._set_running(False, f"{prefix}: {len(outcome.results)} birim, {failed} hatalı.{where}")
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 1)
            self.progress.setValue(1 if not outcome.stopped else 0)
        self.open_button.setEnabled(self._report_dir is not None)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self._set_running(False, "Çalıştırma başarısız.")
        QMessageBox.warning(self, self.title, message)

    @Slot()
    def _open_reports(self) -> None:
        if self._report_dir is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._report_dir.resolve())))

    def _set_running(self, running: bool, message: str) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        for widget in (self.target_box, self.refresh_button, self.limit_box):
            widget.setEnabled(not running)
        for check in self.format_checks.values():
            check.setEnabled(not running)
        self.status.setText(message)
