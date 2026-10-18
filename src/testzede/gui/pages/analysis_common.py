"""Çağrı Grafiği ve Metrikler sayfalarının ortak parçaları.

* :class:`SourcePicker`: analiz edilecek kodu seçtirir: "Kod Yükle" sayfasındaki kod ya da
  bir HumanEval görevi (US-1: "HumanEval veri setinden alınan bir kod").
* :class:`AnalysisPage`: kaynağı seçip hesabı arka planda çalıştıran, sonucu gösteren ve
  kaynak değişince "eski" notunu düşen sayfa tabanı. Alt sınıflar yalnızca hesabı
  (``_compute``) ve görünümü (``_render``) tanımlar.

İki sayfa da ``AppState``'i yalnızca okur; diğer sayfaların verisini değiştirmez.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from testzede.gui.pages.base import BasePage
from testzede.gui.state import AppState
from testzede.gui.styles import StatusColor, set_status_style, status_colors
from testzede.gui.worker import TaskRunner, Worker
from testzede.services.analysis_service import AnalysisService, SampleTask

log = logging.getLogger(__name__)

MODE_CODE = "code"
MODE_TASK = "task"
_WAIT_AT_EXIT_MS = 15_000
# Durum türü -> ``styles.status_colors`` anahtarı ("info" renksizdir).
_STATUS_KINDS = {"ok": "ok", "error": "error", "warn": "warning"}
STALE_NOTE = "Not: Kaynak kod değişti, bu sonuç eski olabilir. Yeniden oluşturun."
DOWNLOAD_HINT = (
    "HumanEval indirilmemiş. Terminalde çalıştırın: testzede download --dataset humaneval"
)


def show_status(
    label: QLabel, colors: dict[str, StatusColor], message: str, kind: str = "info"
) -> None:
    """Durum etiketini türüne göre renkli gösterir (``ok``/``error``/``warn``/``info``)."""
    key = _STATUS_KINDS.get(kind)
    label.setText(message)
    set_status_style(label, colors[key] if message and key else None)
    label.setProperty("status", kind)


class SourcePicker(QWidget):
    """Analiz edilecek kodu seçtirir: "Kod Yükle" sayfasındaki kod ya da HumanEval görevi."""

    changed = Signal()  # seçilen kaynak değişti
    tasks_loaded = Signal(bool)  # HumanEval listesi yüklendi (True) ya da yüklenemedi (False)

    def __init__(
        self, state: AppState, service: AnalysisService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.state = state
        self._service = service
        self.colors = status_colors(self)
        self._tasks = TaskRunner(self)
        self._samples: Sequence[SampleTask] = ()
        self._samples_loaded = False

        self.code_radio = QRadioButton("Kod Yükle sayfasındaki kod")
        self.task_radio = QRadioButton("HumanEval görevi:")
        self.task_box = QComboBox()
        self.task_box.setMinimumContentsLength(32)
        self.task_box.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.task_box.setEnabled(False)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.code_radio.setChecked(True)
        self._refresh_availability()

        row = QHBoxLayout()
        row.addWidget(self.code_radio)
        row.addWidget(self.task_radio)
        row.addWidget(self.task_box)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        layout.addWidget(self.hint)

        self.task_radio.toggled.connect(self._on_task_toggled)
        self.task_box.currentIndexChanged.connect(self._on_task_chosen)
        self._refresh_hint()

    # --- seçilen kaynak ------------------------------------------------------------------------

    @property
    def mode(self) -> str:
        """``MODE_CODE`` ya da ``MODE_TASK``."""
        return MODE_TASK if self.task_radio.isChecked() else MODE_CODE

    def _current_task(self) -> SampleTask | None:
        index = self.task_box.currentIndex()
        if self.mode == MODE_TASK and 0 <= index < len(self._samples):
            return self._samples[index]
        return None

    def source(self) -> str:
        """Seçili kaynağın metni (henüz seçili/yüklü kaynak yoksa boş)."""
        if self.mode == MODE_CODE:
            return self.state.source
        task = self._current_task()
        return task.source if task else ""

    def label(self) -> str:
        """Kaynağın kısa adı: ``"Kod Yükle"`` ya da ``"HumanEval/12"``."""
        task = self._current_task()
        return task.uid if task else "Kod Yükle"

    def problem(self) -> str:
        """Analizi engelleyen eksikliği açıklar; yoksa boş metin."""
        if self.source().strip():
            return ""
        if self.mode == MODE_CODE:
            return "Kaynak kod yok. Önce 'Kod Yükle' sayfasında kod yükleyin ya da bir HumanEval görevi seçin."
        if self._samples_loaded:
            return "Bir HumanEval görevi seçin."
        return "HumanEval görevleri yükleniyor..."

    # --- HumanEval listesi ---------------------------------------------------------------------

    def _refresh_availability(self) -> None:
        """HumanEval verisi diskte yoksa seçenek kapalı kalır ve nedeni ipucunda yazar."""
        available = self._service.humaneval_available()
        self.task_radio.setEnabled(available or self.task_radio.isChecked())
        self.task_radio.setToolTip("" if available else DOWNLOAD_HINT)

    def _on_task_toggled(self, checked: bool) -> None:
        if checked and not self._samples_loaded:
            self._load_samples()
        self.task_box.setEnabled(checked and self._samples_loaded)
        self._refresh_hint()
        self.changed.emit()

    def _on_task_chosen(self, _index: int) -> None:
        if self.mode == MODE_TASK:
            self._refresh_hint()
            self.changed.emit()

    def _load_samples(self) -> None:
        if self._tasks.busy:
            return
        service = self._service
        self.hint.setText("HumanEval görevleri yükleniyor...")

        def job(worker: Worker) -> list[SampleTask]:
            return list(service.humaneval_tasks())

        self._tasks.start(
            job, on_finished=self._on_samples_loaded, on_failed=self._on_samples_failed
        )

    @Slot(object)
    def _on_samples_loaded(self, samples: object) -> None:
        self._samples = list(samples)  # type: ignore[call-overload]
        self._samples_loaded = True
        self.task_box.blockSignals(True)
        self.task_box.clear()
        self.task_box.addItems([task.label for task in self._samples])
        self.task_box.blockSignals(False)
        self.task_box.setEnabled(self.task_radio.isChecked())
        self._refresh_hint()
        self.tasks_loaded.emit(True)
        if self.task_radio.isChecked():
            self.changed.emit()  # ilk görev artık kullanılabilir

    @Slot(str)
    def _on_samples_failed(self, message: str) -> None:
        self.code_radio.setChecked(True)  # kullanılamayan kaynaktan geri dön
        show_status(self.hint, self.colors, message, "error")
        self.tasks_loaded.emit(False)

    # --- yaşam döngüsü -------------------------------------------------------------------------

    def on_enter(self) -> None:
        """Sayfa açılınca: veri sonradan indirildiyse seçeneği açar, ipucunu tazeler."""
        self._refresh_availability()
        self._refresh_hint()

    def shutdown(self) -> None:
        """Pencere kapanırken çalışan yüklemeyi bekler."""
        self._tasks.shutdown(timeout_ms=_WAIT_AT_EXIT_MS)

    def _refresh_hint(self) -> None:
        if self.mode == MODE_CODE:
            lines = len(self.state.source.splitlines())
            if self.state.source.strip():
                show_status(self.hint, self.colors, f"Kod Yükle sayfasındaki kod ({lines} satır).")
            else:
                show_status(self.hint, self.colors, "Kod Yükle sayfasında henüz kod yok.", "warn")
            return
        task = self._current_task()
        if task is not None:
            show_status(self.hint, self.colors, f"{task.uid}: {task.entry_point} fonksiyonu.")
        elif self._samples_loaded:
            show_status(self.hint, self.colors, "Bir HumanEval görevi seçin.", "warn")
        else:
            show_status(self.hint, self.colors, "HumanEval görevleri yükleniyor...")


class AnalysisPage(BasePage):
    """Kaynağı seçtirip hesabı arka planda çalıştıran sayfa tabanı.

    Alt sınıflar ``_compute`` (iş parçacığında çalışır; Qt nesnesine dokunmaz) ve
    ``_render`` tanımlar; gövdeyi ``body_layout`` altına koyar.
    """

    run_completed = Signal(bool)  # hesap bitti (True: başarılı)

    def __init__(
        self,
        title: str,
        run_text: str,
        state: AppState,
        service: AnalysisService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, state, parent)
        self.colors = status_colors(self)  # tema çalışırken değişmez
        self._service = service if service is not None else AnalysisService()
        self._tasks = TaskRunner(self)
        self._running = False
        self._pending: tuple[str, str] | None = None  # çalışan işin (kaynak, ad) girdisi
        self._shown_source: str | None = None  # görünümde gösterilen sonucun kaynağı
        self._showing_problem = False

        self.picker = SourcePicker(state, self._service)
        self.run_button = QPushButton(run_text)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.note_label = QLabel(STALE_NOTE)
        set_status_style(self.note_label, self.colors["warning"])
        self.note_label.hide()

        top = QHBoxLayout()
        top.addWidget(self.run_button)
        top.addWidget(self.status_label, 1)
        self.body_layout = QVBoxLayout()
        layout = QVBoxLayout(self)
        layout.addWidget(self.picker)
        layout.addLayout(top)
        layout.addWidget(self.note_label)
        layout.addLayout(self.body_layout, 1)

        self.run_button.clicked.connect(self.run)
        self.picker.changed.connect(self._on_source_changed)

    # --- alt sınıfların tanımladıkları ---------------------------------------------------------

    def _compute(self, source: str) -> object:
        """Hesabı yapar (arka plan iş parçacığı); hata durumunda ``ServiceError`` fırlatır."""
        raise NotImplementedError

    def _render(self, result: object, label: str) -> None:
        """Sonucu görünüme yazar."""
        raise NotImplementedError

    # --- çalıştırma ----------------------------------------------------------------------------

    def run(self) -> None:
        """Hesabı arka planda çalıştırır; girdi eksikse nedenini gösterir."""
        if self._running or self._tasks.busy:
            return
        if self.picker.problem():
            self._refresh_run_state()
            return
        source, label = self.picker.source(), self.picker.label()

        def job(worker: Worker) -> object:
            return self._compute(source)

        self._running = True
        self._pending = (source, label)
        self.run_button.setEnabled(False)
        self._set_status("Hesaplanıyor...", "info")
        self._tasks.start(job, on_finished=self._on_finished, on_failed=self._on_failed)

    def shutdown(self) -> None:
        """Pencere kapanırken çalışan işlerin bitmesini (üst sınırla) bekler."""
        self.picker.shutdown()
        self._tasks.shutdown(timeout_ms=_WAIT_AT_EXIT_MS)

    @Slot(object)
    def _on_finished(self, result: object) -> None:
        self._running = False
        source, label = self._pending or (self.picker.source(), self.picker.label())
        self._pending = None
        try:
            self._render(result, label)
        except Exception as exc:  # Madde-1: gösterim hatası düğmeyi kilitlemez, uygulamayı düşürmez
            log.exception("Analiz sonucu gösterilemedi")
            self._refresh_run_state()
            self._set_status(f"Sonuç gösterilemedi: {exc}", "error")
            self.run_completed.emit(False)
            return
        self._shown_source = source
        self._refresh_run_state()
        self._set_status("Tamamlandı.", "ok")
        self._update_note()
        self.run_completed.emit(True)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._running = False
        self._pending = None
        self._refresh_run_state()
        self._set_status(message, "error")
        self.run_completed.emit(False)

    # --- sayfa yaşam döngüsü -------------------------------------------------------------------

    def on_enter(self) -> None:
        """Seçiciyi ve düğme durumunu tazeler; kaynak değiştiyse eski-sonuç notunu gösterir."""
        self.picker.on_enter()
        self._refresh_run_state()
        self._update_note()

    def _on_source_changed(self) -> None:
        self._refresh_run_state()
        self._update_note()

    # --- görünüm -------------------------------------------------------------------------------

    def _refresh_run_state(self) -> None:
        """Çalışmıyorsa düğmeyi girdi durumuna göre açar/kapatır ve nedeni gösterir."""
        if self._running:
            return
        problem = self.picker.problem()
        self.run_button.setEnabled(not problem)
        if problem:
            self._set_status(problem, "warn")
            self._showing_problem = True
        elif self._showing_problem:
            self._set_status("", "info")
            self._showing_problem = False

    def _set_status(self, message: str, kind: str) -> None:
        show_status(self.status_label, self.colors, message, kind)
        if kind != "warn":
            self._showing_problem = False

    def _update_note(self) -> None:
        """Gösterilen sonuç seçili kaynakla uyuşmuyorsa "eski" notunu gösterir."""
        stale = self._shown_source is not None and self._shown_source != self.picker.source()
        self.note_label.setVisible(stale)
