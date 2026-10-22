from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

from testzede.gui.main_window import MainWindow
from testzede.gui.pages import code_page as code_page_module
from testzede.gui.pages.code_page import CodePage, check_source, read_source_file
from testzede.gui.state import AppState

VALID = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
BROKEN = "def f(a):\n    return (a +\n"


@pytest.fixture
def page(qtbot) -> CodePage:
    widget = CodePage(AppState())
    qtbot.addWidget(widget)
    return widget


def _type(page: CodePage, text: str) -> None:
    page.editor.setPlainText(text)


# --- read_source_file --------------------------------------------------------------------------


def test_read_source_file_reads_utf8(tmp_path):
    path = tmp_path / "a.py"
    path.write_text("# Türkçe: çğıöşü\nx = 1\n", encoding="utf-8")
    assert read_source_file(path) == "# Türkçe: çğıöşü\nx = 1\n"


def test_read_source_file_strips_utf8_bom(tmp_path):
    path = tmp_path / "bom.py"
    path.write_bytes(b"\xef\xbb\xbfx = 1\n")
    assert read_source_file(path) == "x = 1\n"


def test_read_source_file_invalid_utf8_gives_clear_error(tmp_path):
    path = tmp_path / "latin.py"
    path.write_bytes("# şş".encode("cp1254") + b"\nx = 1\n")
    with pytest.raises(ValueError, match="UTF-8"):
        read_source_file(path)


def test_read_source_file_missing_file(tmp_path):
    with pytest.raises(ValueError, match="bulunamadı"):
        read_source_file(tmp_path / "yok.py")


def test_read_source_file_directory(tmp_path):
    with pytest.raises(ValueError, match="klasör|izniniz"):  # Windows'ta PermissionError olur
        read_source_file(tmp_path)


@pytest.mark.parametrize(
    ("error", "expected"),
    [(PermissionError("x"), "izniniz yok"), (OSError("disk hatası"), "okunamadı: disk hatası")],
)
def test_read_source_file_os_errors(monkeypatch, tmp_path, error, expected):
    def boom(self, *args, **kwargs):
        raise error

    monkeypatch.setattr(Path, "read_text", boom)
    with pytest.raises(ValueError, match=expected):
        read_source_file(tmp_path / "a.py")


# --- check_source ------------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "\n\t\n"])
def test_check_source_blank_is_invalid(text):
    result = check_source(text)
    assert not result.ok and "boş" in result.message


def test_check_source_lists_top_level_functions_only():
    src = (
        "def a(): pass\n"
        "class C:\n    def method(self): pass\n"
        "def b():\n    def inner(): pass\n"
        "async def c(): pass\n"
    )
    result = check_source(src)
    assert result.ok and result.functions == ["a", "b"]
    assert "a, b" in result.message


def test_check_source_without_functions():
    result = check_source("x = 1")
    assert result.ok and result.functions == []
    assert "bulunamadı" in result.message


def test_check_source_syntax_error_reports_line():
    result = check_source("x = 1\ny = (\n")
    assert not result.ok
    assert result.line is not None and result.message.startswith(f"Satır {result.line}:")


def test_check_source_null_byte_is_invalid():
    assert not check_source("x = 1\x00").ok


# --- sayfa -------------------------------------------------------------------------------------


def test_editor_is_monospace_and_preloaded_from_state(qtbot):
    widget = CodePage(AppState(source="x = 1"))
    qtbot.addWidget(widget)
    assert widget.editor.toPlainText() == "x = 1"
    assert widget.editor.font().fixedPitch()
    assert widget.title == "Kod Yükle"


def test_valid_code_updates_state_and_lists_functions(page):
    _type(page, VALID)
    qtbot_click = page.validate_button
    qtbot_click.click()
    assert page.state.source == VALID
    assert page.status_label.property("status") == "ok"
    assert "add, sub" in page.status_label.text()
    assert page.colors["ok"].fg.name() in page.status_label.styleSheet()


def test_syntax_error_does_not_update_state_and_shows_line(page):
    _type(page, BROKEN)
    page.validate_button.click()
    assert page.state.source == ""
    assert page.status_label.property("status") == "error"
    assert page.status_label.text().startswith("Satır ")
    assert page.colors["error"].fg.name() in page.status_label.styleSheet()
    assert "Önceki geçerli kod" not in page.status_label.text()  # korunacak bir şey yok


def test_syntax_error_keeps_previous_valid_source(page):
    _type(page, VALID)
    page.validate()
    _type(page, "def f(:\n    pass")
    page.validate()
    assert page.state.source == VALID
    assert "Satır 1" in page.status_label.text()
    assert "Önceki geçerli kod korunuyor" in page.status_label.text()


def test_error_line_number_points_at_the_error(page):
    _type(page, "x = 1\ny = 2\nz = = 3\n")
    page.validate()
    assert "Satır 3" in page.status_label.text()


def test_empty_code_is_invalid_and_keeps_previous_source(page):
    _type(page, VALID)
    page.validate()
    _type(page, "")
    result = page.validate()
    assert not result.ok
    assert page.state.source == VALID
    assert page.status_label.property("status") == "error"
    assert "boş" in page.status_label.text()


def test_empty_code_on_fresh_page_leaves_state_empty(page):
    page.validate()
    assert page.state.source == ""
    assert page.status_label.property("status") == "error"


def test_text_change_validates_automatically_after_a_short_delay(page, qtbot):
    _type(page, VALID)
    assert page.state.source == ""  # gecikme dolmadan doğrulanmaz
    qtbot.waitUntil(lambda: page.state.source == VALID, timeout=3000)
    assert page.status_label.property("status") == "ok"


def test_rapid_typing_restarts_the_delay(page, qtbot):
    page.editor.setPlainText("x = 1")
    page.editor.setPlainText("y = 2")
    qtbot.waitUntil(lambda: page.state.source == "y = 2", timeout=3000)


def test_validate_button_click_works_through_mouse(page, qtbot):
    _type(page, "x = 1")
    qtbot.mouseClick(page.validate_button, Qt.MouseButton.LeftButton)
    assert page.state.source == "x = 1"


# --- on_enter ----------------------------------------------------------------------------------


def test_on_enter_syncs_editor_with_externally_changed_state(page):
    page.state.source = "def g(): pass"
    page.on_enter()
    assert page.editor.toPlainText() == "def g(): pass"
    assert page.status_label.property("status") == "ok"
    assert "g" in page.status_label.text()


def test_on_enter_clears_editor_after_state_reset(page):
    _type(page, VALID)
    page.validate()
    page.state.reset()
    page.on_enter()
    assert page.editor.toPlainText() == ""
    assert page.state.source == ""


def test_on_enter_keeps_unsaved_draft_when_state_is_unchanged(page):
    _type(page, VALID)
    page.validate()
    _type(page, "def broken(:")
    page.on_enter()
    assert page.editor.toPlainText() == "def broken(:"
    assert page.state.source == VALID


def test_on_enter_does_not_trigger_delayed_revalidation(page, qtbot):
    page.state.source = "x = 1"
    page.on_enter()
    qtbot.wait(600)  # gecikmeli doğrulama zaten durdu; durum bozulmaz
    assert page.state.source == "x = 1"


# --- dosya açma --------------------------------------------------------------------------------


def test_load_file_success_fills_editor_and_state(page, tmp_path):
    path = tmp_path / "prog.py"
    path.write_text(VALID, encoding="utf-8")
    assert page.load_file(path) is True
    assert page.editor.toPlainText() == VALID
    assert page.state.source == VALID
    assert "add, sub" in page.status_label.text()


def test_load_file_failure_is_shown_on_page_not_raised(page, tmp_path):
    _type(page, VALID)
    page.validate()
    assert page.load_file(tmp_path / "yok.py") is False
    assert "bulunamadı" in page.status_label.text()
    assert page.status_label.property("status") == "error"
    assert page.state.source == VALID and page.editor.toPlainText() == VALID


def test_load_file_with_bad_encoding_shows_error(page, tmp_path):
    path = tmp_path / "bad.py"
    path.write_bytes(b"x = '\xff'\n")
    assert page.load_file(path) is False
    assert "UTF-8" in page.status_label.text()
    assert page.state.source == ""


def test_load_file_with_syntax_error_loads_text_but_keeps_state(page, tmp_path):
    path = tmp_path / "broken.py"
    path.write_text(BROKEN, encoding="utf-8")
    assert page.load_file(path) is True  # okundu; hata doğrulamada gösterilir
    assert page.editor.toPlainText() == BROKEN
    assert page.state.source == ""
    assert page.status_label.property("status") == "error"


def test_open_button_uses_file_dialog(page, tmp_path, monkeypatch):
    path = tmp_path / "prog.py"
    path.write_text("x = 1\n", encoding="utf-8")
    seen: dict[str, str] = {}

    def fake_dialog(parent, caption, directory, file_filter):
        seen["filter"] = file_filter
        return str(path), "Python (*.py)"

    monkeypatch.setattr(QFileDialog, "getOpenFileName", fake_dialog)
    page.open_button.click()
    assert seen["filter"] == "Python (*.py)"
    assert page.state.source == "x = 1\n"


def test_cancelled_file_dialog_changes_nothing(page, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    _type(page, "x = 1")
    page.open_button.click()
    assert page.editor.toPlainText() == "x = 1"


def test_unexpected_error_in_dialog_flow_is_a_value_error_only(page, monkeypatch, tmp_path):
    monkeypatch.setattr(
        code_page_module, "read_source_file", lambda path: (_ for _ in ()).throw(ValueError("x"))
    )
    assert page.load_file(tmp_path / "a.py") is False
    assert page.status_label.text() == "x"


# --- ana pencere entegrasyonu ------------------------------------------------------------------


def test_main_window_registers_code_page_under_kod_yukle(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert isinstance(window.page("Kod Yükle"), CodePage)
    assert window.page("Kod Yükle").state is window.state
    assert window.stack.currentWidget() is window.page("Kod Yükle")


def test_menu_return_syncs_code_page_with_external_state_change(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    code = window.page("Kod Yükle")
    window.nav.setCurrentRow(1)
    window.state.source = "def other(): pass"
    window.nav.setCurrentRow(0)
    assert code.editor.toPlainText() == "def other(): pass"


def test_check_source_overly_nested_code_is_invalid_not_a_crash():
    result = check_source("x = " + "+ 1 " * 20000)
    assert not result.ok and result.message.startswith("Kod geçerli değil")
