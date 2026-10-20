import os

import pytest

# CI'da ekran yok; Qt'yi ekransız çalıştır (QApplication oluşmadan önce ayarlanmalı).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def app_theme(qapp):
    """Temayı adıyla uygulayan fonksiyon; test bitince uygulamanın görünümü geri yüklenir.

    Yeni tema stil, palet ve fontu da değiştirdiği için yalnızca stil sayfasını
    temizlemek yetmez; sonraki testler temasız uygulamayla başlamalı.
    """
    from PySide6.QtGui import QFont, QPalette
    from PySide6.QtWidgets import QStyleFactory

    from testzede.gui import theme
    from testzede.gui.app import _apply_theme

    style, palette, font = qapp.style().name(), QPalette(qapp.palette()), QFont(qapp.font())
    current = theme._current

    def apply(name: str) -> None:
        _apply_theme(qapp, name)

    yield apply
    qapp.setStyleSheet("")
    qapp.setStyle(QStyleFactory.create(style))
    qapp.setPalette(palette)
    qapp.setFont(font)
    theme._current = current
