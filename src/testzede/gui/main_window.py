"""Ana pencere: solda menü, sağda sayfa yığını."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from testzede.gui.pages.base import BasePage
from testzede.gui.pages.placeholder import PlaceholderPage
from testzede.gui.state import AppState

MENU_ITEMS = (
    "Kod Yükle",
    "Test Üretimi",
    "Coverage",
    "Mutasyon",
    "Tahmin",
    "Toplu Test",
    "Raporlar",
    "Ayarlar",
)


class MainWindow(QMainWindow):
    """Menüden seçilen sayfayı gösterir; kayıtsız menüler yer tutucu sayfa gösterir."""

    def __init__(self, state: AppState | None = None) -> None:
        super().__init__()
        self.state = state if state is not None else AppState()
        self.setWindowTitle("TestZede")
        self.resize(1100, 700)

        self.menu = QListWidget()
        self.menu.setFixedWidth(200)
        self.menu.addItems(MENU_ITEMS)
        self.stack = QStackedWidget()

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.menu)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self._pages: dict[str, BasePage] = {}
        for name in MENU_ITEMS:
            page = PlaceholderPage(name, self.state)
            self._pages[name] = page
            self.stack.addWidget(page)

        self.menu.currentRowChanged.connect(self._on_row_changed)
        self.menu.setCurrentRow(0)

    def page(self, name: str) -> BasePage:
        """Menü adına karşılık gelen sayfayı döndürür."""
        return self._pages[name]

    def current_page(self) -> BasePage:
        """Şu an görünen sayfayı döndürür."""
        return self._pages[MENU_ITEMS[self.stack.currentIndex()]]

    def register_page(self, name: str, page: BasePage) -> None:
        """Menü öğesinin yer tutucusunu ``page`` ile değiştirir; bilinmeyen ada ``ValueError``."""
        if name not in MENU_ITEMS:
            raise ValueError(f"Bilinmeyen menü öğesi: {name}")
        index = MENU_ITEMS.index(name)
        old = self._pages[name]
        self.stack.removeWidget(old)
        old.deleteLater()
        self.stack.insertWidget(index, page)
        self._pages[name] = page
        current = self.menu.currentRow()
        self.stack.setCurrentIndex(current)
        if current == index:
            page.on_enter()

    def _on_row_changed(self, row: int) -> None:
        """Menü seçimi değişince sayfayı gösterir ve ``on_enter`` çağırır."""
        if row < 0:
            return
        self.stack.setCurrentIndex(row)
        self._pages[MENU_ITEMS[row]].on_enter()
