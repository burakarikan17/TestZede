"""Masaüstü uygulamasının girişi (``testzede gui``).

Yakalanmamış her istisna ``gui.error_handler`` ile loglanır ve mesaj kutusunda
gösterilir; uygulama kapanmaz (Madde-1).
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from testzede.gui.error_handler import install_global_handler
from testzede.gui.main_window import MainWindow
from testzede.logging_setup import Logger


def _apply_theme(app: QApplication) -> None:
    try:
        from qt_material import apply_stylesheet

        apply_stylesheet(app, theme="light_blue.xml", invert_secondary=True)
    except Exception:  # noqa: BLE001 - tema yüklenemezse varsayılan görünümle devam
        Logger().logger.warning("qt-material teması uygulanamadı", exc_info=True)


def main(argv: list[str] | None = None) -> int:
    """Uygulamayı açar; pencere kapanınca çıkış kodunu döndürür."""
    install_global_handler()
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    _apply_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
