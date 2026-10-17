"""qt-material temasının ezdiği iki ayarı, yalnızca ilgili widget'lar için geri alan stiller.

Tema genel bir ``* { font-family: Roboto }`` kuralı koyduğu için ``setFont`` ile verilen
monospace font çizimde ezilir. Ayrıca ``QHeaderView::section`` kuralındaki
``text-transform: uppercase`` başlıkları BÜYÜK harf çizer, ama ``ResizeToContents`` bölüm
genişliğini küçük harfli metne göre hesaplar; dar sütunlarda başlık kırpılır.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import QPlainTextEdit, QTableWidget

MONO_FAMILIES = '"Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace'
MONO_QSS = f"QPlainTextEdit {{ font-family: {MONO_FAMILIES}; }}"
HEADER_QSS = "QHeaderView::section { text-transform: none; }"

_fallback_registered = False


def _register_fallback_font() -> None:
    """matplotlib'in paketlediği DejaVu Sans Mono'yu uygulamaya kaydeder (bir kez).

    Sistemde listedeki hiçbir monospace font yoksa (başsız ortam, sade Linux) kod
    görünümleri yine de sabit genişlikli fontla çizilir.
    """
    global _fallback_registered
    if _fallback_registered or QGuiApplication.instance() is None:
        return
    _fallback_registered = True
    spec = importlib.util.find_spec("matplotlib")
    if spec is None or not spec.submodule_search_locations:
        return
    root = Path(next(iter(spec.submodule_search_locations)))
    font = root / "mpl-data" / "fonts" / "ttf" / "DejaVuSansMono.ttf"
    if font.is_file():
        QFontDatabase.addApplicationFont(str(font))


def apply_monospace(editor: QPlainTextEdit) -> None:
    """Editörü temadan bağımsız olarak monospace fontla çizer (yalnızca bu widget)."""
    _register_fallback_font()
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setFixedPitch(True)
    editor.setFont(font)  # tema yokken de doğru font
    editor.setStyleSheet(MONO_QSS)  # tema varken genel font-family kuralını ezer


def fix_table_header(table: QTableWidget) -> None:
    """Tablonun başlıklarını küçük/büyük harf farkı yüzünden kırpılmayacak şekilde çizer.

    Tablonun mevcut stylesheet'ini korur; yalnızca bu tabloyu etkiler.
    """
    current = table.styleSheet()
    if HEADER_QSS not in current:
        table.setStyleSheet(f"{current} {HEADER_QSS}".strip())
