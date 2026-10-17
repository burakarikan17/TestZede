"""Uygulama girişi: tema, global hata yakalama ve ana pencere."""

from __future__ import annotations

import sys
import threading
from collections.abc import Sequence
from types import TracebackType

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QApplication

from testzede.gui.error_handler import handle_exception, install_global_handler
from testzede.gui.main_window import MainWindow
from testzede.gui.pages.code_page import PAGE_TITLE, CodePage
from testzede.logging_setup import Logger

THEME = "dark_teal.xml"


def apply_theme(app: QApplication) -> bool:
    """qt-material temasını uygular; yüklenemezse sessizce varsayılana düşer (``False``)."""
    try:
        from qt_material import apply_stylesheet

        apply_stylesheet(app, theme=THEME)
    except Exception:  # noqa: BLE001 - tema olmasa da uygulama açılmalı
        Logger().logger.warning("Tema yüklenemedi, varsayılan görünüm kullanılıyor", exc_info=True)
        return False
    return True


class _ThreadErrorBridge(QObject):
    """Diğer iş parçacıklarındaki hataları GUI iş parçacığına taşır (diyalog orada açılır)."""

    raised = Signal(object, object, object)

    def __init__(self) -> None:
        super().__init__()
        self.raised.connect(self._on_raised)

    @Slot(object, object, object)
    def _on_raised(
        self, exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
    ) -> None:
        handle_exception(exc_type, exc, tb)


_bridge: _ThreadErrorBridge | None = None


def install_thread_excepthook() -> None:
    """``threading.excepthook``'u aynı işleyiciye bağlar; hata GUI iş parçacığında gösterilir."""
    global _bridge
    _bridge = _ThreadErrorBridge()
    bridge = _bridge

    def hook(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        bridge.raised.emit(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = hook


def create_main_window() -> MainWindow:
    """Ana pencereyi kurar ve hazır sayfaları kaydeder."""
    window = MainWindow()
    window.register_page(PAGE_TITLE, CodePage(window.state))
    return window


def main(argv: Sequence[str] | None = None) -> int:
    """GUI'yi başlatır ve çıkış kodunu döndürür."""
    app = QApplication.instance() or QApplication(list(argv if argv is not None else sys.argv))
    apply_theme(app)
    install_global_handler()
    install_thread_excepthook()
    window = create_main_window()
    window.show()
    return app.exec()
