"""Açık/koyu tema düğmesi ve temalar arası yumuşak geçiş.

Düğmeye basınca pencerenin o anki görüntüsü üstte bırakılır, tema altta değişir ve eski
görüntü ``FADE_MS`` içinde saydamlaşarak kaybolur (çapraz geçiş). Tema ``gui.theme`` ile
uygulanır; çizilmiş durum renkleri :func:`styles.recolor` ile yeni temaya çevrilir.
qt-material (``TESTZEDE_THEME=material``) geri dönüş temasında düğme gizlidir.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QToolButton,
    QWidget,
)

from testzede.gui import styles, theme
from testzede.gui.pages.graph_canvas import GraphCanvas

FADE_MS = 300
ICON_SIZE = 18
TIP_TO_DARK = "Koyu temaya geç"
TIP_TO_LIGHT = "Açık temaya geç"


def _icon(kind: str, color: str) -> QIcon:
    """Ay (``moon``) ya da güneş (``sun``) ikonu; yüksek DPI için iki kat çizilir."""
    scale = 2
    size = ICON_SIZE * scale
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    c = size / 2
    if kind == "moon":
        disc = QPainterPath()
        disc.addEllipse(QPointF(c, c), size * 0.38, size * 0.38)
        bite = QPainterPath()
        bite.addEllipse(QPointF(c + size * 0.2, c - size * 0.16), size * 0.32, size * 0.32)
        painter.drawPath(disc.subtracted(bite))
    else:
        painter.drawEllipse(QPointF(c, c), size * 0.2, size * 0.2)
        painter.translate(c, c)
        for _ in range(8):
            painter.drawRoundedRect(
                QRectF(-size * 0.04, -size * 0.46, size * 0.08, size * 0.14), 2, 2
            )
            painter.rotate(45)
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return QIcon(pixmap)


class ThemeSwitch(QToolButton):
    """Açık ve koyu tema arasında geçiş yapan düğme (basılıyken koyu tema)."""

    theme_changed = Signal(str)  # yeni temanın adı

    def __init__(self, window: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._window = window
        self._overlay: QLabel | None = None
        self._animation: QPropertyAnimation | None = None
        self.setObjectName("themeSwitch")
        self.setCheckable(True)
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.setChecked(theme.current() == theme.DARK_NAME)
        self.setVisible(theme.current() != theme.MATERIAL_NAME)
        self._refresh_look()
        self.toggled.connect(self._on_toggled)

    @property
    def fading(self) -> bool:
        """Geçiş animasyonu sürüyor mu."""
        return self._overlay is not None

    def _refresh_look(self) -> None:
        dark = self.isChecked()
        palette = theme.DARK if dark else theme.LIGHT
        # Koyu temadayken güneş (açığa dön), açık temadayken ay (koyuya geç) gösterilir.
        self.setIcon(_icon("sun" if dark else "moon", palette.text))
        tip = TIP_TO_LIGHT if dark else TIP_TO_DARK
        self.setToolTip(tip)
        self.setAccessibleName(tip)

    def _on_toggled(self, dark: bool) -> None:
        self.switch(theme.DARK_NAME if dark else theme.LIGHT_NAME)

    def switch(self, name: str, animate: bool = True) -> None:
        """Temayı ``name`` yapar; ``animate`` ise eski görünüm yavaşça kaybolur."""
        app = QApplication.instance()
        if app is None or name == theme.current():
            return
        self._finish_fade()
        snapshot = self._window.grab() if animate and self._window.isVisible() else None
        old = styles.status_colors(self._window)
        theme.apply(app, name)
        new = styles.status_colors(self._window)
        styles.recolor(self._window, old, new)
        for canvas in self._window.findChildren(GraphCanvas):  # grafik zemini temaya uyar
            canvas.refresh_theme()
        self.blockSignals(True)
        self.setChecked(name == theme.DARK_NAME)
        self.blockSignals(False)
        self._refresh_look()
        if snapshot is not None:
            self._fade_out(snapshot)
        self.theme_changed.emit(name)

    def _fade_out(self, snapshot: QPixmap) -> None:
        overlay = QLabel(self._window)
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        overlay.setPixmap(snapshot)
        overlay.setGeometry(self._window.rect())
        effect = QGraphicsOpacityEffect(overlay)
        effect.setOpacity(1.0)
        overlay.setGraphicsEffect(effect)
        overlay.show()
        overlay.raise_()
        animation = QPropertyAnimation(effect, b"opacity", overlay)
        animation.setDuration(FADE_MS)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        animation.finished.connect(self._finish_fade)
        self._overlay, self._animation = overlay, animation
        animation.start()

    def _finish_fade(self) -> None:
        """Süren geçişi bitirir (art arda basılırsa önceki görüntü hemen kaldırılır)."""
        if self._animation is not None:
            self._animation.finished.disconnect(self._finish_fade)
            self._animation.stop()
        if self._overlay is not None:
            self._overlay.hide()
            self._overlay.deleteLater()
        self._overlay, self._animation = None, None
