"""qt-material temasının ezdiği iki ayarı, yalnızca ilgili widget'lar için geri alan stiller.

Tema genel bir ``* { font-family: Roboto }`` kuralı koyduğu için ``setFont`` ile verilen
monospace font çizimde ezilir. Ayrıca ``QHeaderView::section`` kuralındaki
``text-transform: uppercase`` başlıkları BÜYÜK harf çizer, ama ``ResizeToContents`` bölüm
genişliğini küçük harfli metne göre hesaplar; dar sütunlarda başlık kırpılır.

Durum renkleri (:func:`status_colors`) açık ve koyu tema için ayrı tanımlıdır. Her durum
yazı ve zemin rengini birlikte verir; ikisi birlikte uygulandığı için kontrast (WCAG,
>= 4.5:1) temanın kendi zemin ve yazı renklerinden bağımsızdır. İstisna tablo hücreleridir:
qt-material hücre zeminini çizdiği için orada yalnızca yazı rengi kullanılır; yazı renkleri
temanın tablo zeminine karşı da >= 4.5:1'dir.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QTableWidget, QWidget

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
    register_matplotlib_font("DejaVuSansMono.ttf")


def register_matplotlib_font(filename: str) -> None:
    """matplotlib'in paketlediği ``filename`` fontunu uygulamaya kaydeder; yoksa bir şey yapmaz."""
    spec = importlib.util.find_spec("matplotlib")
    if spec is None or not spec.submodule_search_locations:
        return
    root = Path(next(iter(spec.submodule_search_locations)))
    font = root / "mpl-data" / "fonts" / "ttf" / filename
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


@dataclass(frozen=True)
class StatusColor:
    """Bir durumun yazı (``fg``) ve zemin (``bg``) rengi; ikisi birlikte uygulanır."""

    fg: QColor
    bg: QColor


# durum -> (yazı, zemin). Satır vurguları: covered/partial/missed, added/removed.
# Test sonuçları: passed/failed/error/timeout. Durum etiketleri: ok/error/warning.
_LIGHT = {
    "covered": ("#1b5e20", "#c8e6c9"),
    "partial": ("#5d3a00", "#ffe0b2"),
    "missed": ("#8e0000", "#ffcdd2"),
    "passed": ("#1b5e20", "#e8f5e9"),
    "failed": ("#b71c1c", "#ffebee"),
    "timeout": ("#6d4100", "#fff3e0"),
}
_DARK = {
    "covered": ("#e8f5e9", "#1e5128"),
    "partial": ("#fff3e0", "#6b4a00"),
    "missed": ("#ffebee", "#7f1d1d"),
    "passed": ("#c8e6c9", "#173d22"),
    "failed": ("#ffcdd2", "#5a1a1a"),
    "timeout": ("#ffe0b2", "#4d3300"),
}
_ALIASES = {
    "added": "covered",
    "removed": "missed",
    "error": "failed",
    "ok": "passed",
    "warning": "timeout",
}


def is_dark_theme(widget: QWidget | None = None) -> bool:
    """Tema koyu mu: pencere zemininin parlaklığına bakar.

    qt-material uygulama paletinin ``Window`` rengini değiştirmez, zemini stil sayfasıyla
    verir; bu yüzden mümkünse stil sayfası uygulanmış (polish edilmiş) bir widget'ın paleti okunur.
    """
    if widget is not None:
        widget.ensurePolished()
        palette = widget.palette()
    else:
        palette = QGuiApplication.palette()
    return palette.color(QPalette.ColorRole.Window).lightness() < 128


def status_colors(widget: QWidget | None = None) -> dict[str, StatusColor]:
    """Geçerli temaya uygun durum renkleri (bkz. modül açıklaması)."""
    base = _DARK if is_dark_theme(widget) else _LIGHT
    colors = {name: StatusColor(QColor(fg), QColor(bg)) for name, (fg, bg) in base.items()}
    colors.update({alias: colors[name] for alias, name in _ALIASES.items()})
    return colors


def set_status_style(label: QLabel, color: StatusColor | None) -> None:
    """Etiketi durum rengiyle (yazı + zemin) çizer; ``None`` stili kaldırır."""
    if color is None:
        label.setStyleSheet("")
        return
    label.setStyleSheet(
        f"color: {color.fg.name()}; background-color: {color.bg.name()};"
        " padding: 2px 6px; border-radius: 3px;"
    )
