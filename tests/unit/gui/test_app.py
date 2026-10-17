from __future__ import annotations

import sys
import threading
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from testzede.gui import app as app_module
from testzede.gui.error_handler import handle_exception
from testzede.gui.main_window import MainWindow


@pytest.fixture(autouse=True)
def restore_hooks(monkeypatch):
    """Testlerin değiştirdiği global hook'ları geri yükler."""
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)


def test_apply_theme_success_on_real_application(qapp):
    assert app_module.apply_theme(qapp) is True
    assert qapp.styleSheet()


def test_apply_theme_falls_back_silently_when_theme_fails(qapp, monkeypatch):
    import qt_material

    def broken(*_args, **_kwargs):
        raise RuntimeError("tema yok")

    monkeypatch.setattr(qt_material, "apply_stylesheet", broken)
    assert app_module.apply_theme(qapp) is False  # istisna sızmaz


def test_apply_theme_falls_back_when_qt_material_cannot_be_imported(qapp, monkeypatch):
    monkeypatch.setitem(sys.modules, "qt_material", None)  # import ImportError verir
    assert app_module.apply_theme(qapp) is False


def test_main_wires_handlers_and_opens_main_window(qapp, monkeypatch):
    shown: list[MainWindow] = []
    monkeypatch.setattr(app_module, "apply_theme", lambda app: True)
    monkeypatch.setattr(MainWindow, "show", lambda self: shown.append(self))
    monkeypatch.setattr(QApplication, "exec", lambda self: 7)
    monkeypatch.setattr("testzede.logging_setup.Logger.configure", lambda self, path=None: None)

    assert app_module.main([]) == 7
    assert sys.excepthook is handle_exception
    assert threading.excepthook is not threading.__excepthook__
    assert len(shown) == 1 and isinstance(shown[0], MainWindow)
    shown[0].close()


def test_main_reuses_existing_application(qapp, monkeypatch):
    monkeypatch.setattr(app_module, "apply_theme", lambda app: True)
    monkeypatch.setattr(MainWindow, "show", lambda self: None)
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    monkeypatch.setattr("testzede.logging_setup.Logger.configure", lambda self, path=None: None)
    app_module.main([])
    assert QApplication.instance() is qapp


def test_thread_hook_forwards_to_global_handler_on_gui_thread(qapp, qtbot, monkeypatch):
    handled: list[tuple] = []
    gui_ident = threading.get_ident()
    idents: list[int] = []

    def fake_handler(exc_type, exc, tb):
        handled.append((exc_type, str(exc)))
        idents.append(threading.get_ident())

    monkeypatch.setattr(app_module, "handle_exception", fake_handler)
    app_module.install_thread_excepthook()

    def boom():
        raise ValueError("iş parçacığı hatası")

    thread = threading.Thread(target=boom)
    thread.start()
    thread.join()
    qtbot.waitUntil(lambda: bool(handled), timeout=2000)
    assert handled == [(ValueError, "iş parçacığı hatası")]
    assert idents == [gui_ident]  # diyalog GUI iş parçacığında açılır


def test_thread_hook_ignores_system_exit(qapp, qtbot, monkeypatch):
    handled: list[object] = []
    monkeypatch.setattr(app_module, "handle_exception", lambda *a: handled.append(a))
    app_module.install_thread_excepthook()
    threading.excepthook(
        SimpleNamespace(
            exc_type=SystemExit, exc_value=SystemExit(), exc_traceback=None, thread=None
        )
    )
    qtbot.wait(50)
    assert handled == []
