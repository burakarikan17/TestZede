"""Tüm sayfaların taban sınıfı."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from testzede.gui.state import AppState


class BasePage(QWidget):
    """Başlığı ve paylaşılan :class:`AppState` referansı olan sayfa."""

    def __init__(self, title: str, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self.state = state

    @property
    def title(self) -> str:
        """Sayfa başlığı (menüdeki ad ile aynıdır)."""
        return self._title

    def on_enter(self) -> None:
        """Sayfa açıldığında çağrılır; alt sınıflar verilerini burada tazeler."""
