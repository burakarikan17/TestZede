"""Uygulama ikonu: tema vurgu renginde yuvarlak köşeli kare üzerinde beyaz bir "Z".

İkon kodla çizilir (ikili dosya yok) ve her boyutta ayrı çizildiği için küçük boyutlarda da
keskin kalır. Windows'ta görev çubuğunun Python yerine TestZede ikonunu göstermesi için
uygulama kimliği ayrıca ayarlanır (:func:`set_app_identity`).
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication

APP_ID = "TestZede.TestZede"
SIZES = (16, 24, 32, 48, 64, 128, 256)
_TOP, _BOTTOM = QColor("#6C78F0"), QColor("#3A45AE")  # theme.LIGHT.accent çevresi


def draw_pixmap(size: int) -> QPixmap:
    """``size`` x ``size`` piksellik ikon görüntüsü."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = size * 0.04
    body = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    gradient = QLinearGradient(body.topLeft(), body.bottomRight())
    gradient.setColorAt(0.0, _TOP)
    gradient.setColorAt(1.0, _BOTTOM)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawRoundedRect(body, size * 0.22, size * 0.22)

    left, right = size * 0.22, size * 0.66
    top, bottom = size * 0.21, size * 0.65
    bar = size * 0.115  # üst ve alt çubuğun kalınlığı
    slant = (right - left) * 0.36  # çaprazın yatay kalınlığı
    z = QPainterPath()
    z.moveTo(left, top)
    z.lineTo(right, top)
    z.lineTo(right, top + bar)
    z.lineTo(left + slant, bottom - bar)
    z.lineTo(right, bottom - bar)
    z.lineTo(right, bottom)
    z.lineTo(left, bottom)
    z.lineTo(left, bottom - bar)
    z.lineTo(right - slant, top + bar)
    z.lineTo(left, top + bar)
    z.closeSubpath()
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawPath(z)

    if size >= 48:  # küçük boyutta okunmaz: sağ alttaki yeşil "geçti" işareti
        radius = size * 0.14
        center = QPointF(size * 0.75, size * 0.75)
        painter.setBrush(QColor("#1F9D55"))
        painter.setPen(QColor("#FFFFFF"))
        painter.drawEllipse(center, radius, radius)
        painter.setPen(Qt.PenStyle.NoPen)
        tick = QPainterPath()
        tick.moveTo(center.x() - radius * 0.5, center.y() + radius * 0.02)
        tick.lineTo(center.x() - radius * 0.12, center.y() + radius * 0.42)
        tick.lineTo(center.x() + radius * 0.55, center.y() - radius * 0.42)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(QColor("#FFFFFF"), size * 0.035)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(tick)
    painter.end()
    return pixmap


def make_icon() -> QIcon:
    """Tüm boyutları içeren uygulama ikonu."""
    icon = QIcon()
    for size in SIZES:
        icon.addPixmap(draw_pixmap(size))
    return icon


def set_app_identity(app: QApplication) -> None:
    """Pencere ikonunu ve (Windows'ta) görev çubuğu kimliğini ayarlar."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except (
            AttributeError,
            OSError,
        ):  # kimlik ayarlanamazsa yalnızca görev çubuğu ikonu etkilenir
            pass
    app.setApplicationName("TestZede")
    app.setWindowIcon(make_icon())
