"""Kod Yükle sayfasının "Test Kodu" sekmesi ve ``module_name`` davranışı."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

from testzede.gui.pages.code_page import CodePage
from testzede.gui.state import AppState

TESTS_OK = (
    "from calc import add\n\n"
    "def test_a():\n    assert add(1, 2) == 3\n\n"
    "def test_b():\n    assert add(0, 0) == 0\n"
)
CALC = "def add(a, b):\n    return a + b\n"
BROKEN = "def f(a):\n    return (a +\n"


@pytest.fixture
def page(qtbot) -> CodePage:
    widget = CodePage(AppState())
    qtbot.addWidget(widget)
    return widget


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_page_has_source_and_test_tabs(page):
    assert page.tabs.count() == 2
    assert [page.tabs.tabText(i) for i in range(2)] == ["Kaynak Kod", "Test Kodu"]
    assert page.tests_editor.font().fixedPitch()
    assert page.tabs.widget(0).isAncestorOf(page.editor)
    assert page.tabs.widget(1).isAncestorOf(page.tests_editor)


def test_valid_tests_fill_app_state_and_show_green_summary(page):
    page.tests_editor.setPlainText(TESTS_OK)
    assert page.validate_tests() is True
    assert [t.name for t in page.state.tests] == ["test_a", "test_b"]
    assert all(t.origin == "user" for t in page.state.tests)
    assert page.tests_status_label.text() == "2 test bulundu: test_a, test_b"
    assert page.tests_status_label.property("status") == "ok"
    assert "#69f0ae" in page.tests_status_label.styleSheet()


def test_validate_tests_button_click(page, qtbot):
    page.tests_editor.setPlainText(TESTS_OK)
    qtbot.mouseClick(page.tests_validate_button, Qt.MouseButton.LeftButton)
    assert len(page.state.tests) == 2


def test_test_syntax_error_keeps_previous_tests_and_shows_line(page):
    page.tests_editor.setPlainText(TESTS_OK)
    page.validate_tests()
    old = page.state.tests
    page.tests_editor.setPlainText("def test_a():\n    assert (1 +\n")
    assert page.validate_tests() is False
    assert page.state.tests is old
    text = page.tests_status_label.text()
    assert text.startswith("Satır 2") and "Önceki geçerli testler korunuyor" in text
    assert page.tests_status_label.property("status") == "error"
    assert "#ff5252" in page.tests_status_label.styleSheet()


def test_test_error_on_fresh_page_leaves_tests_empty(page):
    page.tests_editor.setPlainText("def test_a(:")
    assert page.validate_tests() is False
    assert page.state.tests == []
    assert "Önceki" not in page.tests_status_label.text()


def test_code_without_tests_is_an_error(page):
    page.tests_editor.setPlainText("x = 1")
    assert page.validate_tests() is False
    assert "Test fonksiyonu bulunamadı" in page.tests_status_label.text()
    assert page.state.tests == []


def test_blank_tests_are_an_error(page):
    assert page.validate_tests() is False
    assert "boş" in page.tests_status_label.text()


def test_test_editor_validates_automatically_after_delay(page, qtbot):
    page.tests_editor.setPlainText(TESTS_OK)
    assert page.state.tests == []
    qtbot.waitUntil(lambda: len(page.state.tests) == 2, timeout=3000)


def test_source_validation_does_not_flag_empty_test_editor(page):
    page.editor.setPlainText(CALC)
    page.validate()
    assert page.tests_status_label.text() == ""  # test sekmesi boşken hata gösterilmez


# --- module_name -------------------------------------------------------------------------------


def test_pasted_code_leaves_module_name_none(page):
    page.editor.setPlainText(CALC)
    page.validate()
    assert page.state.source == CALC and page.state.module_name is None


def test_opening_a_source_file_sets_module_name_to_the_stem(page, tmp_path):
    assert page.load_file(_write(tmp_path, "calc.py", CALC))
    assert page.state.module_name == "calc"
    page.load_file(_write(tmp_path, "other.py", "x = 1\n"))
    assert page.state.module_name == "other"


def test_invalid_source_file_does_not_change_module_name_or_source(page, tmp_path):
    page.load_file(_write(tmp_path, "calc.py", CALC))
    page.load_file(_write(tmp_path, "broken.py", BROKEN))
    assert page.state.module_name == "calc"
    assert page.state.source == CALC


def test_unreadable_source_file_does_not_change_module_name(page, tmp_path):
    assert page.load_file(tmp_path / "yok.py") is False
    assert page.state.module_name is None


def test_open_dialog_sets_module_name(page, tmp_path, monkeypatch):
    path = _write(tmp_path, "calc.py", CALC)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    page.open_button.click()
    assert page.state.module_name == "calc"


def test_tests_use_module_name_to_redirect_imports(page, tmp_path):
    page.load_file(_write(tmp_path, "calc.py", CALC))
    assert page.load_tests_file(_write(tmp_path, "test_calc.py", TESTS_OK))
    assert "from target import add" in page.state.tests[0].code
    assert "from calc import" not in page.state.tests[0].code


def test_changing_source_revalidates_tests_with_new_module_name(page, tmp_path):
    page.tests_editor.setPlainText(TESTS_OK)
    page.validate_tests()
    assert "from calc import add" in page.state.tests[0].code  # modül adı henüz bilinmiyor
    page.load_file(_write(tmp_path, "calc.py", CALC))
    assert "from target import add" in page.state.tests[0].code
    assert page.tests_status_label.property("status") == "ok"


def test_invalid_source_does_not_revalidate_tests(page):
    page.tests_editor.setPlainText(TESTS_OK)
    page.validate_tests()
    before = page.state.tests
    page.editor.setPlainText(BROKEN)
    page.validate()
    assert page.state.tests is before


# --- test dosyası açma -------------------------------------------------------------------------


def test_load_tests_file_success(page, tmp_path):
    assert page.load_tests_file(_write(tmp_path, "test_x.py", TESTS_OK)) is True
    assert page.tests_editor.toPlainText() == TESTS_OK
    assert len(page.state.tests) == 2


def test_load_tests_file_failure_is_shown_and_keeps_tests(page, tmp_path):
    page.tests_editor.setPlainText(TESTS_OK)
    page.validate_tests()
    old = page.state.tests
    assert page.load_tests_file(tmp_path / "yok.py") is False
    assert "bulunamadı" in page.tests_status_label.text()
    assert page.tests_status_label.property("status") == "error"
    assert page.state.tests is old and page.tests_editor.toPlainText() == TESTS_OK


def test_load_tests_file_with_bad_encoding(page, tmp_path):
    path = tmp_path / "bad.py"
    path.write_bytes(b"def test_a():\n    x = '\xff'\n")
    assert page.load_tests_file(path) is False
    assert "UTF-8" in page.tests_status_label.text()


def test_tests_open_button_uses_file_dialog(page, tmp_path, monkeypatch):
    path = _write(tmp_path, "test_x.py", TESTS_OK)
    seen: dict[str, str] = {}

    def fake_dialog(parent, caption, directory, file_filter):
        seen["caption"] = caption
        return str(path), ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", fake_dialog)
    page.tests_open_button.click()
    assert seen["caption"] == "Test dosyası seç"
    assert len(page.state.tests) == 2


def test_cancelled_tests_dialog_changes_nothing(page, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    page.tests_editor.setPlainText("keep")
    page.tests_open_button.click()
    assert page.tests_editor.toPlainText() == "keep"


# --- on_enter ----------------------------------------------------------------------------------


def test_on_enter_after_reset_clears_test_editor_and_status(page):
    page.tests_editor.setPlainText(TESTS_OK)
    page.validate_tests()
    page.state.reset()
    page.on_enter()
    assert page.tests_editor.toPlainText() == ""
    assert page.tests_status_label.text() == ""
    assert page.state.tests == []


def test_on_enter_keeps_test_draft_when_nothing_changed(page):
    page.tests_editor.setPlainText(TESTS_OK)
    page.validate_tests()
    page.tests_editor.setPlainText("draft")
    page.on_enter()
    assert page.tests_editor.toPlainText() == "draft"
    assert len(page.state.tests) == 2


def test_on_enter_with_empty_unchanged_state_keeps_draft(page):
    page.tests_editor.setPlainText("draft")
    page.on_enter()
    assert page.tests_editor.toPlainText() == "draft"
