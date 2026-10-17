"""Ana pencere: solda sayfa listesi, sağda seçili sayfa.

Yeni sayfa ``PAGES``'e eklenir. Her sayfa ``title`` taşır; arka planda iş
çalıştıranlar ``shutdown()`` tanımlar (pencere kapanırken çağrılır).
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
    QWidget,
)

from testzede.gui.pages.batch_page import BatchPage
from testzede.gui.pages.rl_page import RLPage

PageFactory = Callable[[], QWidget]

# Diğer sayfalar (Kod Yükle, Çağrı Grafiği, Metrikler, Coverage, Mutasyon, Tahmin)
# sahipleri tarafından buraya eklenir.
PAGES: tuple[PageFactory, ...] = (RLPage, BatchPage)


class MainWindow(QMainWindow):
    def __init__(self, pages: Sequence[PageFactory] = PAGES) -> None:
        super().__init__()
        self.setWindowTitle("TestZede")
        self.resize(1200, 780)
        self.nav = QListWidget()
        self.nav.setFixedWidth(200)
        self.stack = QStackedWidget()
        self.pages: list[QWidget] = []
        for factory in pages:
            page = factory()
            self.pages.append(page)
            self.stack.addWidget(page)
            self.nav.addItem(getattr(page, "title", type(page).__name__))
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(self.nav)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

    def page(self, title: str) -> QWidget:
        """Başlığı verilen sayfa (sayfalar arası veri aktarımı için)."""
        for page in self.pages:
            if getattr(page, "title", None) == title:
                return page
        raise KeyError(title)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.setCursor(Qt.CursorShape.WaitCursor)
        for page in self.pages:
            shutdown = getattr(page, "shutdown", None)
            if callable(shutdown):
                shutdown()
        super().closeEvent(event)
