"""Henüz yazılmamış sayfalar için yer tutucu."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from testzede.gui.pages.base import BasePage
from testzede.gui.state import AppState


class PlaceholderPage(BasePage):
    """Yalnızca sayfa başlığını ve "Yakında" etiketini gösterir."""

    def __init__(self, title: str, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(title, state, parent)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        font = heading.font()
        font.setPointSize(20)
        heading.setFont(font)
        soon = QLabel("Yakında")
        soon.setObjectName("comingSoon")
        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(soon)
        layout.addStretch(1)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
