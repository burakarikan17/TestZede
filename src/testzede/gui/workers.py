"""Uzun işlemleri GUI iş parçacığını bloklamadan çalıştıran worker."""

from __future__ import annotations

import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from testzede.logging_setup import Logger


class Worker(QObject):
    """Verilen callable'ı ``QThread`` içinde çalıştırır.

    Callable ``progress_callback(done, total)`` ve ``should_cancel()`` anahtar argümanlarıyla
    çağrılır. Sinyaller: ``progress(done, total)``, ``finished(sonuç)``, ``failed(mesaj)``.
    İptal edilen iş, callable'ın döndürdüğü (kısmi) sonuçla ``finished`` verir.
    """

    progress = Signal(int, int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[..., object]) -> None:
        super().__init__()
        self._fn = fn
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        """İptal bayrağını set eder; callable ``should_cancel()`` ile kontrol eder."""
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        """İptal istenip istenmediğini döndürür."""
        return self._cancelled.is_set()

    @Slot()
    def run(self) -> None:
        """Callable'ı çalıştırır; sonucu ``finished``, hatayı ``failed`` ile bildirir."""
        try:
            result = self._fn(progress_callback=self.progress.emit, should_cancel=self.is_cancelled)
        except Exception as exc:  # noqa: BLE001 - arka plan hatası arayüzü düşürmemeli
            Logger().logger.exception("Arka plan işlemi başarısız")
            self.failed.emit(str(exc) or type(exc).__name__)
        else:
            self.finished.emit(result)


def run_in_thread(worker: Worker) -> QThread:
    """``worker``'ı yeni bir ``QThread``'de başlatır; iş bitince iş parçacığı kendiliğinden durur.

    Dönen iş parçacığına ve worker'a çağıran sahip olmalıdır (referansı tutmalıdır).
    """
    owner_thread = QThread.currentThread()
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    # quit() iş parçacığı-güvenlidir; doğrudan bağlantı GUI olay döngüsünden bağımsız çalışır.
    direct = Qt.ConnectionType.DirectConnection
    worker.finished.connect(thread.quit, direct)
    worker.failed.connect(thread.quit, direct)
    # Bitince worker'ı çağıranın iş parçacığına geri ver (sahiplik uyarılarını önler).
    thread.finished.connect(lambda: worker.moveToThread(owner_thread), direct)
    thread.start()
    return thread
