"""Ana pencere: solda sayfa listesi, sağda seçili sayfa; sağ üstte açık/koyu tema düğmesi.

Yeni sayfa ``PAGES``'e eklenir. Her sayfa :class:`BasePage`'den türer ve
paylaşılan :class:`AppState`'i alır; sayfa açıldığında ``on_enter()`` çağrılır.
Arka planda iş çalıştıranlar ``shutdown()`` tanımlar (pencere kapanırken çağrılır).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from testzede.gui.pages.base import BasePage
from testzede.gui.pages.batch_page import BatchPage
from testzede.gui.pages.call_graph_page import CallGraphPage
from testzede.gui.pages.code_page import CodePage
from testzede.gui.pages.coverage_page import CoveragePage
from testzede.gui.pages.metrics_page import MetricsPage
from testzede.gui.pages.mutation_page import MutationPage
from testzede.gui.pages.rl_page import RLPage
from testzede.gui.state import AppState
from testzede.gui.theme_switch import ThemeSwitch

PageFactory = Callable[[AppState], BasePage]

# Sayfalar ARCHITECTURE.md §6'daki sırayla eklenir. Tahmin sayfası sahibi tarafından
# (opsiyonel) buraya eklenecek.
PAGES: tuple[PageFactory, ...] = (
    CodePage,
    CallGraphPage,
    MetricsPage,
    CoveragePage,
    RLPage,
    MutationPage,
    BatchPage,
)


class MainWindow(QMainWindow):
    def __init__(self, state: AppState | None = None, pages: Sequence[PageFactory] = PAGES) -> None:
        super().__init__()
        self.state = state if state is not None else AppState()
        self.setWindowTitle("TestZede")
        self.resize(1200, 780)
        self.nav = QListWidget()
        self.nav.ensurePolished()  # satır yükseklikleri temanın iç boşluklarıyla hesaplansın
        self.nav.setFixedWidth(200)
        self.stack = QStackedWidget()
        self.pages: list[BasePage] = []
        for factory in pages:
            page = factory(self.state)
            self.pages.append(page)
            self.stack.addWidget(page)
            self.nav.addItem(page.title)
        self.nav.currentRowChanged.connect(self._on_row_changed)
        self.nav.setCurrentRow(0)

        self.theme_switch = ThemeSwitch(self)
        top_bar = QHBoxLayout()
        top_bar.addStretch(1)
        top_bar.addWidget(self.theme_switch)

        body = QHBoxLayout()
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(top_bar)
        layout.addLayout(body, 1)
        self.setCentralWidget(central)

    def page(self, title: str) -> BasePage:
        """Başlığı verilen sayfa."""
        for page in self.pages:
            if page.title == title:
                return page
        raise KeyError(title)

    def _on_row_changed(self, row: int) -> None:
        if row < 0:
            return
        self.stack.setCurrentIndex(row)
        self.pages[row].on_enter()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.setCursor(Qt.CursorShape.WaitCursor)
        for page in self.pages:
            shutdown = getattr(page, "shutdown", None)
            if callable(shutdown):
                shutdown()
        super().closeEvent(event)
