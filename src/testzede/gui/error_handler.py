"""Yakalanmamış istisnaları loglayan ve kullanıcıya gösteren global handler."""

from __future__ import annotations

import sys
from types import TracebackType

from testzede.logging_setup import Logger

_TITLE = "Beklenmeyen Hata"
_MESSAGE = (
    "Beklenmeyen bir hata oluştu, ancak uygulama çalışmaya devam ediyor.\n"
    "İşleminizi kontrol edip tekrar deneyin.\n\nAyrıntı: {detail}"
)


def _show_dialog(exc_type: type[BaseException], exc: BaseException) -> None:
    """Açık bir QApplication varsa hata penceresi gösterir; hiçbir şey fırlatmaz."""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is None:
            return
        detail = f"{exc_type.__name__}: {exc}"
        QMessageBox.critical(None, _TITLE, _MESSAGE.format(detail=detail))
    except Exception:  # noqa: BLE001 - hata penceresi asla ikinci bir çökme yaratmasın
        Logger().logger.exception("Hata penceresi gösterilemedi")


def handle_exception(
    exc_type: type[BaseException],
    exc: BaseException,
    tb: TracebackType | None,
) -> None:
    """``sys.excepthook`` yerine geçer: loglar ve kullanıcıya mesaj gösterir."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    try:
        Logger().logger.error("Yakalanmamış istisna", exc_info=(exc_type, exc, tb))
    except Exception:  # noqa: BLE001 - loglama hatası ikinci bir çökme yaratmasın
        print(f"{exc_type.__name__}: {exc}", file=sys.stderr)
    _show_dialog(exc_type, exc)


def install_global_handler() -> None:
    """``sys.excepthook``'u :func:`handle_exception` ile değiştirir."""
    Logger().configure()
    sys.excepthook = handle_exception
