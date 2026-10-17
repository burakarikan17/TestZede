"""Uzun işlemleri ``QThread`` içinde çalıştıran işçi (Observer: sonuçlar Qt sinyalleriyle gelir).

GUI iş parçacığı asla bloklanmaz. İşin fırlattığı istisna ``failed`` sinyaliyle
mesaj olarak döner; uygulamaya sızmaz.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot

from testzede.services.errors import ServiceError

log = logging.getLogger(__name__)


class Worker(QObject):
    """``job(worker)`` çağrısını arka planda yapar.

    İş, ``worker.report(...)`` ile ilerleme bildirir ve ``worker.stop_requested()``
    ile durdurma isteğini sorar.
    """

    progress = Signal(object)  # job'ın report'a verdiği değer
    finished = Signal(object)  # job'ın dönüş değeri
    failed = Signal(str)  # kullanıcıya gösterilecek mesaj

    def __init__(self, job: Callable[[Worker], Any]) -> None:
        super().__init__()
        self._job = job
        self._stop = threading.Event()

    def report(self, value: object) -> None:
        self.progress.emit(value)

    def request_stop(self) -> None:
        self._stop.set()

    def stop_requested(self) -> bool:
        return self._stop.is_set()

    @Slot()
    def run(self) -> None:
        try:
            result = self._job(self)
        except ServiceError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # Madde-1: hiçbir hata GUI'yi düşürmez
            log.exception("Arka plan işi başarısız")
            self.failed.emit(f"Beklenmeyen hata: {exc}")
        else:
            self.finished.emit(result)


class TaskRunner(QObject):
    """Aynı anda tek bir ``Worker`` çalıştıran yardımcı; sayfalar bunu kullanır."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: Worker | None = None

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def start(
        self,
        job: Callable[[Worker], Any],
        *,
        on_finished: Callable[[object], None],
        on_failed: Callable[[str], None],
        on_progress: Callable[[object], None] | None = None,
    ) -> Worker:
        if self.busy:
            raise RuntimeError("Önceki iş bitmedi")
        thread = QThread()
        worker = Worker(job)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(on_finished)
        worker.failed.connect(on_failed)
        if on_progress is not None:
            worker.progress.connect(on_progress)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._cleanup)
        self._thread, self._worker = thread, worker
        thread.start()
        return worker

    def request_stop(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()

    def shutdown(self, timeout_ms: int = 30_000) -> None:
        """Pencere kapanırken: durdurma ister ve iş parçacığının bitmesini bekler."""
        thread = self._thread
        if thread is None:
            return
        self.request_stop()
        thread.quit()
        thread.wait(timeout_ms)

    @Slot()
    def _cleanup(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._thread = self._worker = None
