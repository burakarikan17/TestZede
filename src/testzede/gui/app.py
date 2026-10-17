"""Masaüstü uygulamasının girişi (``testzede gui``).

Yakalanmamış her istisna loglanır ve mesaj kutusunda gösterilir; uygulama
kapanmaz (Madde-1).
"""

from __future__ import annotations

import logging
import sys
import traceback
from types import TracebackType

from PySide6.QtWidgets import QApplication, QMessageBox

from testzede.gui.main_window import MainWindow

log = logging.getLogger("testzede")


def _excepthook(
    exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
) -> None:
    log.error("Yakalanmamış hata:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
    if QApplication.instance() is not None:
        QMessageBox.critical(None, "TestZede", f"Beklenmeyen hata: {exc}")


def _apply_theme(app: QApplication) -> None:
    try:
        from qt_material import apply_stylesheet

        apply_stylesheet(app, theme="light_blue.xml", invert_secondary=True)
    except Exception:  # tema yüklenemezse varsayılan görünümle devam
        log.warning("qt-material teması uygulanamadı", exc_info=True)


def main(argv: list[str] | None = None) -> int:
    """Uygulamayı açar; pencere kapanınca çıkış kodunu döndürür."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.excepthook = _excepthook
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    _apply_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
