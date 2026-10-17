from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel

from testzede.gui.main_window import MENU_ITEMS, MainWindow
from testzede.gui.pages.base import BasePage
from testzede.gui.pages.placeholder import PlaceholderPage
from testzede.gui.state import AppState

EXPECTED_MENU = [
    "Kod Yükle",
    "Test Üretimi",
    "Coverage",
    "Mutasyon",
    "Tahmin",
    "Toplu Test",
    "Raporlar",
    "Ayarlar",
]


class RecordingPage(BasePage):
    """``on_enter`` çağrılarını sayan sayfa."""

    def __init__(self, title: str, state: AppState) -> None:
        super().__init__(title, state)
        self.entered = 0

    def on_enter(self) -> None:
        self.entered += 1


@pytest.fixture
def window(qtbot) -> MainWindow:
    win = MainWindow()
    qtbot.addWidget(win)
    return win


def test_window_opens_with_eight_menu_items(window):
    assert [window.menu.item(i).text() for i in range(window.menu.count())] == EXPECTED_MENU
    assert list(MENU_ITEMS) == EXPECTED_MENU
    assert window.stack.count() == 8
    assert window.windowTitle() == "TestZede"


def test_first_page_is_shown_initially(window):
    assert window.menu.currentRow() == 0
    assert window.stack.currentIndex() == 0
    assert window.current_page().title == "Kod Yükle"


@pytest.mark.parametrize("row", range(8))
def test_selecting_menu_row_shows_matching_page(window, row):
    window.menu.setCurrentRow(row)
    page = window.current_page()
    assert window.stack.currentIndex() == row
    assert window.stack.currentWidget() is page
    assert page.title == EXPECTED_MENU[row]


def test_unregistered_menus_show_placeholder_with_title_and_soon_label(window):
    window.menu.setCurrentRow(3)
    page = window.stack.currentWidget()
    assert isinstance(page, PlaceholderPage)
    texts = {label.text() for label in page.findChildren(QLabel)}
    assert texts == {"Mutasyon", "Yakında"}


def test_pages_share_the_window_state(window):
    assert all(window.page(name).state is window.state for name in MENU_ITEMS)
    state = AppState(source="x = 1")
    assert MainWindow(state).state is state


def test_register_page_replaces_placeholder(window):
    page = RecordingPage("Coverage", window.state)
    window.register_page("Coverage", page)
    assert window.stack.count() == 8
    assert window.page("Coverage") is page
    window.menu.setCurrentRow(2)
    assert window.stack.currentWidget() is page
    # Diğer menüler hâlâ yer tutucu.
    assert isinstance(window.page("Mutasyon"), PlaceholderPage)
    window.menu.setCurrentRow(3)
    assert isinstance(window.stack.currentWidget(), PlaceholderPage)


def test_on_enter_called_when_menu_selected(window):
    page = RecordingPage("Mutasyon", window.state)
    window.register_page("Mutasyon", page)
    assert page.entered == 0
    window.menu.setCurrentRow(3)
    assert page.entered == 1
    window.menu.setCurrentRow(0)
    window.menu.setCurrentRow(3)
    assert page.entered == 2


def test_registering_the_current_page_shows_it_and_calls_on_enter(window):
    page = RecordingPage("Kod Yükle", window.state)
    window.register_page("Kod Yükle", page)
    assert window.stack.currentWidget() is page
    assert page.entered == 1


def test_registering_other_page_keeps_current_page_visible(window):
    window.menu.setCurrentRow(5)
    current = window.stack.currentWidget()
    window.register_page("Coverage", RecordingPage("Coverage", window.state))
    assert window.stack.currentWidget() is current
    assert window.menu.currentRow() == 5


def test_register_unknown_menu_raises(window):
    with pytest.raises(ValueError, match="Bilinmeyen menü"):
        window.register_page("Yok", RecordingPage("Yok", window.state))
