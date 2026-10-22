"""Uygulamanın global teması: renk, font ve boşluk değerlerinden QSS ve ``QPalette`` üretir.

Tema ``TESTZEDE_THEME`` ortam değişkeniyle seçilir:

* boş ya da ``light``: açık tema (varsayılan),
* ``dark``: koyu tema,
* ``material``: eski qt-material ``light_blue`` teması (geri dönüş yolu).

Stil Fusion'dır; boşluklar (layout kenar ve aralıkları) bir ``QProxyStyle`` ile verilir, bu
yüzden sayfa kodu değişmeden her sayfaya uygulanır. QSS'te gölge olmadığı için kartlar
1 px kenar ve zemin tonu farkıyla ayrılır. Font QSS'te değil uygulama fontunda verilir;
böylece ``setFont`` ile verilen (ör. monospace) fontlar ezilmez.

Durum renkleri (geçti/hata/uyarı) burada değil :mod:`testzede.gui.styles` içindedir.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPalette, QPolygonF
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle, QStyleFactory

from testzede.gui import styles
from testzede.logging_setup import Logger

ENV_VAR = "TESTZEDE_THEME"
LIGHT_NAME, DARK_NAME, MATERIAL_NAME = "light", "dark", "material"

# Boşluk ölçeği (px) ve ölçüler.
SPACE = (4, 8, 12, 16, 24)
RADIUS_CONTROL = 8  # giriş kutusu, düğme
RADIUS_CARD = 12  # tablo, editör, sekme paneli, menü
CONTROL_HEIGHT = 32  # düğme ve giriş kutularının en küçük yüksekliği
HEADER_PADDING = 12  # tablo başlığının yatay iç boşluğu
ARROW_SIZE = (8, 5)  # açılır kutu / sayı kutusu oku (px)
BODY_PT = 10
HEADING_PT = 12
UI_FAMILIES = ("Segoe UI", "Helvetica Neue", "Noto Sans", "DejaVu Sans", "Arial")


@dataclass(frozen=True)
class Theme:
    """Bir temanın renkleri; tüm ana yazı/zemin çiftleri WCAG AA (>= 4.5:1) sağlar."""

    name: str
    dark: bool
    background: str  # pencere zemini
    surface: str  # kart, tablo, giriş kutusu zemini
    surface_alt: str  # üzerine gelme, ilerleme çubuğu oluğu
    border: str
    border_strong: str  # kaydırma çubuğu tutamacı
    text: str
    muted: str  # soluk metin (tablo başlığı, sekme)
    accent: str  # düğme zemini
    on_accent: str  # düğme yazısı
    accent_hover: str
    accent_pressed: str
    selection: str  # seçili satır / menü öğesi
    selection_text: str
    progress: str  # ilerleme çubuğu dolgusu (üstünde metin yazar)
    disabled_bg: str
    disabled_text: str


LIGHT = Theme(
    name=LIGHT_NAME,
    dark=False,
    background="#F5F6FA",
    surface="#FFFFFF",
    surface_alt="#EEF0F6",
    border="#E3E7EF",
    border_strong="#C9CFDB",
    text="#1F2937",
    muted="#5B6474",
    accent="#4F5BD5",
    on_accent="#FFFFFF",
    accent_hover="#4350C2",
    accent_pressed="#3A45AE",
    selection="#E8EAFB",
    selection_text="#1F2937",
    progress="#C3C8F7",
    disabled_bg="#ECEEF3",
    disabled_text="#8A92A0",
)

DARK = Theme(
    name=DARK_NAME,
    dark=True,
    background="#171B23",
    surface="#1F2430",
    surface_alt="#262C39",
    border="#2C3340",
    border_strong="#404959",
    text="#E6E9EF",
    muted="#9AA3B2",
    accent="#8B93F0",
    on_accent="#171B23",
    accent_hover="#9DA4F3",
    accent_pressed="#7880E6",
    selection="#2E3460",
    selection_text="#E6E9EF",
    progress="#4A5296",
    disabled_bg="#232834",
    disabled_text="#6B7383",
)

THEMES = {LIGHT_NAME: LIGHT, DARK_NAME: DARK}


_LAYOUT_METRICS = {
    QStyle.PixelMetric.PM_LayoutLeftMargin: SPACE[2],
    QStyle.PixelMetric.PM_LayoutTopMargin: SPACE[2],
    QStyle.PixelMetric.PM_LayoutRightMargin: SPACE[2],
    QStyle.PixelMetric.PM_LayoutBottomMargin: SPACE[2],
    QStyle.PixelMetric.PM_LayoutHorizontalSpacing: SPACE[2],
    QStyle.PixelMetric.PM_LayoutVerticalSpacing: SPACE[1],
}


class SpacingStyle(QProxyStyle):
    """Fusion; layout kenar boşluğu ve aralıkları boşluk ölçeğinden (``SPACE``) gelir."""

    def __init__(self) -> None:
        super().__init__(QStyleFactory.create("Fusion"))

    def pixelMetric(self, metric, option=None, widget=None) -> int:
        value = _LAYOUT_METRICS.get(metric)
        return value if value is not None else super().pixelMetric(metric, option, widget)


def ui_font() -> QFont:
    """Gövde fontu: Segoe UI (yoksa sıradaki sans-serif), ``BODY_PT`` punto.

    Sistemde listedeki fontların hiçbiri yoksa (başsız ortam) matplotlib'in DejaVu Sans'ı
    kaydedilir; arayüz yine orantılı bir fontla çizilir.
    """
    if not any(family in QFontDatabase.families() for family in UI_FAMILIES):
        styles.register_matplotlib_font("DejaVuSans.ttf")
    font = QFont()
    font.setFamilies(list(UI_FAMILIES))
    font.setPointSize(BODY_PT)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    return font


def build_palette(theme: Theme) -> QPalette:
    """Temanın ``QPalette``'i; ``styles.is_dark_theme`` ``Window`` rengini okur."""
    role = QPalette.ColorRole
    palette = QPalette()
    colors = {
        role.Window: theme.background,
        role.WindowText: theme.text,
        role.Base: theme.surface,
        role.AlternateBase: theme.surface_alt,
        role.Text: theme.text,
        role.Button: theme.surface,
        role.ButtonText: theme.text,
        role.BrightText: theme.on_accent,
        role.Highlight: theme.selection,
        role.HighlightedText: theme.selection_text,
        role.PlaceholderText: theme.muted,
        role.ToolTipBase: theme.text,
        role.ToolTipText: theme.surface,
        role.Link: theme.accent,
        role.Light: theme.surface,
        role.Midlight: theme.surface_alt,
        role.Mid: theme.border_strong,
        role.Dark: theme.border_strong,
        role.Shadow: theme.border_strong,
    }
    for color_role, value in colors.items():
        palette.setColor(color_role, QColor(value))
    disabled = QPalette.ColorGroup.Disabled
    for color_role in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(disabled, color_role, QColor(theme.disabled_text))
    palette.setColor(disabled, role.Button, QColor(theme.disabled_bg))
    return palette


def arrow_images(theme: Theme, folder: Path | None = None) -> dict[str, str]:
    """Açılır kutu ve sayı kutusu okları: temanın soluk metin renginde PNG dosyaları.

    QSS alt kontrolleri biçimlenince Fusion okları çizmez; Qt'nin hazır ok resimleri de
    siyahtır (koyu temada görünmez). Oklar bu yüzden geçici klasöre çizilir.
    """
    folder = folder or Path(tempfile.gettempdir()) / "testzede-theme"
    folder.mkdir(parents=True, exist_ok=True)
    w, h = ARROW_SIZE[0] * 2, ARROW_SIZE[1] * 2  # yüksek DPI için iki kat
    shapes = {
        "down": (QPointF(0, 0), QPointF(w, 0), QPointF(w / 2, h)),
        "up": (QPointF(0, h), QPointF(w, h), QPointF(w / 2, 0)),
    }
    paths = {}
    for name, points in shapes.items():
        image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.muted))
        painter.drawPolygon(QPolygonF(list(points)))
        painter.end()
        path = folder / f"{theme.name}-arrow-{name}.png"
        image.save(str(path))
        paths[name] = path.as_posix()
    return paths


def build_qss(theme: Theme, arrows: dict[str, str] | None = None) -> str:
    """Temanın uygulama geneli stil sayfası (font ve gölge içermez)."""
    t = theme
    arrows = arrows if arrows is not None else arrow_images(theme)
    s1, s2, s3, s4, s5 = SPACE
    # Düğme/giriş: içerik + 2 * dikey iç boşluk + 2 * 1 px kenar = CONTROL_HEIGHT
    content = CONTROL_HEIGHT - 2 * (s1 + 2) - 2
    return f"""
QToolTip {{
    color: {t.surface}; background-color: {t.text};
    border: none; border-radius: {s1}px; padding: {s1}px {s2}px;
}}

QPushButton {{
    color: {t.on_accent}; background-color: {t.accent};
    border: 1px solid {t.accent}; border-radius: {RADIUS_CONTROL}px;
    padding: {s1 + 2}px {s4}px; min-height: {content}px;
}}
QPushButton:hover {{ background-color: {t.accent_hover}; border-color: {t.accent_hover}; }}
QPushButton:pressed {{ background-color: {t.accent_pressed}; border-color: {t.accent_pressed}; }}
QPushButton:focus {{ border-color: {t.text}; }}
QPushButton:disabled {{
    color: {t.disabled_text}; background-color: {t.disabled_bg}; border-color: {t.disabled_bg};
}}

QLineEdit, QSpinBox, QComboBox {{
    color: {t.text}; background-color: {t.surface};
    border: 1px solid {t.border}; border-radius: {RADIUS_CONTROL}px;
    padding: {s1 + 2}px {s2}px; min-height: {content}px;
    selection-background-color: {t.selection}; selection-color: {t.selection_text};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {t.accent}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    color: {t.disabled_text}; background-color: {t.disabled_bg};
}}
QSpinBox {{ padding-right: {s5}px; }}
QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right;
    width: {s5}px; border: none;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    subcontrol-origin: border; width: {s5}px; border: none; background: transparent;
}}
QSpinBox::up-button {{ subcontrol-position: top right; }}
QSpinBox::down-button {{ subcontrol-position: bottom right; }}
QComboBox::down-arrow, QSpinBox::down-arrow {{
    image: url({arrows["down"]}); width: {ARROW_SIZE[0]}px; height: {ARROW_SIZE[1]}px;
}}
QSpinBox::up-arrow {{
    image: url({arrows["up"]}); width: {ARROW_SIZE[0]}px; height: {ARROW_SIZE[1]}px;
}}
QComboBox QAbstractItemView {{
    color: {t.text}; background-color: {t.surface};
    border: 1px solid {t.border}; outline: 0;
    selection-background-color: {t.selection}; selection-color: {t.selection_text};
}}

QPlainTextEdit, QTextEdit {{
    color: {t.text}; background-color: {t.surface};
    border: 1px solid {t.border}; border-radius: {RADIUS_CARD}px; padding: {s1}px;
    selection-background-color: {t.selection}; selection-color: {t.selection_text};
}}
QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {t.accent}; }}

QTableWidget, QTableView {{
    color: {t.text}; background-color: {t.surface};
    border: 1px solid {t.border}; border-radius: {RADIUS_CARD}px;
    gridline-color: {t.border}; outline: 0;
    selection-background-color: {t.selection}; selection-color: {t.selection_text};
}}
QTableWidget::item, QTableView::item {{ padding: 0 {s2}px; }}
QHeaderView {{ background-color: transparent; border: none; }}
QHeaderView::section {{
    color: {t.muted}; background-color: {t.surface};
    border: none; border-bottom: 1px solid {t.border};
    padding: {s2}px {HEADER_PADDING}px;
}}
QTableCornerButton::section {{ background-color: {t.surface}; border: none; }}

QListWidget {{
    color: {t.text}; background-color: {t.surface};
    border: 1px solid {t.border}; border-radius: {RADIUS_CARD}px;
    padding: {s2}px; outline: 0;
}}
QListWidget::item {{
    color: {t.text}; padding: {s2}px {s3}px; margin: 1px 0; border-radius: {RADIUS_CONTROL}px;
}}
QListWidget::item:hover {{ background-color: {t.surface_alt}; }}
QListWidget::item:selected {{ color: {t.selection_text}; background-color: {t.selection}; }}

QTabWidget::pane {{
    background-color: {t.surface}; border: 1px solid {t.border};
    border-radius: {RADIUS_CARD}px; top: -1px;
}}
QTabBar::tab {{
    color: {t.muted}; background-color: transparent;
    border: none; border-bottom: 2px solid transparent;
    padding: {s2}px {s4}px; margin-right: {s1}px;
}}
QTabBar::tab:hover {{ color: {t.text}; }}
QTabBar::tab:selected {{ color: {t.text}; border-bottom-color: {t.accent}; }}

QProgressBar {{
    color: {t.text}; background-color: {t.surface_alt};
    border: none; border-radius: {RADIUS_CONTROL}px; text-align: center; min-height: {s4}px;
}}
QProgressBar::chunk {{ background-color: {t.progress}; border-radius: {RADIUS_CONTROL}px; }}

QCheckBox, QRadioButton {{ color: {t.text}; spacing: {s2}px; }}

QSplitter::handle {{ background-color: transparent; }}
QSplitter::handle:horizontal {{ width: {s2}px; }}
QSplitter::handle:vertical {{ height: {s2}px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: {s1}px 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px {s1}px; }}
QScrollBar::handle:vertical {{
    background: {t.border_strong}; border-radius: 3px; min-height: {s5}px;
}}
QScrollBar::handle:horizontal {{
    background: {t.border_strong}; border-radius: 3px; min-width: {s5}px;
}}
QScrollBar::handle:hover {{ background: {t.muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QToolButton {{
    background-color: transparent; border: 1px solid transparent;
    border-radius: {RADIUS_CONTROL}px; padding: {s1}px;
}}
QToolButton:hover {{ background-color: {t.surface_alt}; border-color: {t.border}; }}
QToolButton:checked {{ background-color: {t.selection}; border-color: {t.border}; }}

QFrame[frameShape="StyledPanel"] {{
    background-color: {t.surface}; border: 1px solid {t.border}; border-radius: {RADIUS_CARD}px;
}}

QLabel[role="heading"] {{ font-size: {HEADING_PT}pt; font-weight: 600; }}
"""


def resolve(name: str | None = None) -> str:
    """Tema adı: verilen ad, yoksa ``TESTZEDE_THEME``, o da yoksa açık tema."""
    value = (name if name is not None else os.environ.get(ENV_VAR, "")).strip().lower()
    if not value:
        return LIGHT_NAME
    if value == MATERIAL_NAME or value in THEMES:
        return value
    Logger().logger.warning("Bilinmeyen tema %r; açık tema kullanılıyor", value)
    return LIGHT_NAME


_current: str | None = None


def current() -> str | None:
    """En son uygulanan temanın adı; henüz tema uygulanmadıysa ``None``."""
    return _current


def apply(app: QApplication, name: str | None = None) -> str:
    """Temayı uygulamaya uygular ve uygulanan temanın adını döndürür."""
    global _current
    resolved = resolve(name)
    if resolved == MATERIAL_NAME:
        from qt_material import apply_stylesheet

        apply_stylesheet(app, theme="light_blue.xml", invert_secondary=True)
    else:
        theme = THEMES[resolved]
        app.setStyle(SpacingStyle())
        app.setPalette(build_palette(theme))
        app.setFont(ui_font())
        app.setStyleSheet(build_qss(theme))
    _current = resolved
    return resolved
