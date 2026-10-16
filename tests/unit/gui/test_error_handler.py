"""Global hata yakalayıcı testleri."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from testzede.gui import error_handler
from testzede.logging_setup import Logger


@pytest.fixture
def log_file(tmp_path: Path):
    """Logger'ı geçici dosyaya yönlendirir."""
    Logger().reset()
    path = tmp_path / "test.log"
    Logger().configure(path)
    yield path
    Logger().reset()


def _flush() -> None:
    for handler in Logger().logger.handlers:
        handler.flush()


def test_logger_is_singleton() -> None:
    assert Logger() is Logger()


def test_exception_is_logged_and_does_not_raise(log_file: Path) -> None:
    try:
        raise ValueError("kullanıcı girdisi hatalı")
    except ValueError:
        exc_type, exc, tb = sys.exc_info()
    with patch.object(error_handler, "_show_dialog") as dialog:
        error_handler.handle_exception(exc_type, exc, tb)
    _flush()
    text = log_file.read_text(encoding="utf-8")
    assert "ValueError" in text and "kullanıcı girdisi hatalı" in text
    dialog.assert_called_once()


def test_keyboard_interrupt_uses_default_hook(log_file: Path) -> None:
    with (
        patch.object(sys, "__excepthook__") as default,
        patch.object(error_handler, "_show_dialog") as dialog,
    ):
        error_handler.handle_exception(KeyboardInterrupt, KeyboardInterrupt(), None)
    default.assert_called_once()
    dialog.assert_not_called()


def test_no_dialog_without_qapplication() -> None:
    with patch("PySide6.QtWidgets.QApplication.instance", return_value=None):
        error_handler._show_dialog(RuntimeError, RuntimeError("x"))


def test_dialog_shown_when_app_open() -> None:
    with (
        patch("PySide6.QtWidgets.QApplication.instance", return_value=object()),
        patch("PySide6.QtWidgets.QMessageBox.critical") as critical,
    ):
        error_handler._show_dialog(RuntimeError, RuntimeError("boom"))
    critical.assert_called_once()
    assert "boom" in critical.call_args.args[2]


def test_dialog_failure_does_not_propagate(log_file: Path) -> None:
    with (
        patch("PySide6.QtWidgets.QApplication.instance", return_value=object()),
        patch("PySide6.QtWidgets.QMessageBox.critical", side_effect=RuntimeError("qt")),
    ):
        error_handler._show_dialog(RuntimeError, RuntimeError("x"))


def test_install_replaces_excepthook(log_file: Path) -> None:
    original = sys.excepthook
    try:
        error_handler.install_global_handler()
        assert sys.excepthook is error_handler.handle_exception
    finally:
        sys.excepthook = original
