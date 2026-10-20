"""Global tema (``gui.theme``): renk değerleri, kontrast, tema seçimi, ölçüler, geri dönüş yolları."""

from __future__ import annotations

import logging
from dataclasses import fields

import pytest
from PySide6.QtGui import QColor, QFontInfo, QImage, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from testzede.gui import styles, theme
from testzede.gui.app import _apply_theme

MIN_CONTRAST = 4.5


def _luminance(color: QColor) -> float:
    """WCAG göreli parlaklık."""

    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.redF())
        + 0.7152 * channel(color.greenF())
        + 0.0722 * channel(color.blueF())
    )


def _contrast(a: str | QColor, b: str | QColor) -> float:
    high, low = sorted((_luminance(QColor(a)), _luminance(QColor(b))), reverse=True)
    return (high + 0.05) / (low + 0.05)


# --- renk değerleri ----------------------------------------------------------------------------


def test_light_theme_uses_the_chosen_palette():
    """Seçenek A (Sakin Çivit), açık tema."""
    t = theme.LIGHT
    assert (t.background, t.surface, t.border) == ("#F5F6FA", "#FFFFFF", "#E3E7EF")
    assert (t.text, t.muted) == ("#1F2937", "#5B6474")
    assert (t.accent, t.on_accent, t.selection) == ("#4F5BD5", "#FFFFFF", "#E8EAFB")
    assert not t.dark and theme.DARK.dark


def test_every_color_is_a_valid_hex():
    for t in theme.THEMES.values():
        for field in fields(t):
            value = getattr(t, field.name)
            if isinstance(value, str) and value.startswith("#"):
                assert QColor(value).isValid(), (t.name, field.name)


@pytest.mark.parametrize("name", list(theme.THEMES))
def test_text_pairs_meet_wcag_aa(name):
    t = theme.THEMES[name]
    pairs = {
        "metin/zemin": (t.text, t.background),
        "metin/kart": (t.text, t.surface),
        "soluk/zemin": (t.muted, t.background),
        "soluk/kart": (t.muted, t.surface),
        "düğme yazısı/vurgu": (t.on_accent, t.accent),
        "düğme yazısı/üzerine gelince": (t.on_accent, t.accent_hover),
        "düğme yazısı/basılı": (t.on_accent, t.accent_pressed),
        "seçili yazı/seçili satır": (t.selection_text, t.selection),
        "metin/ilerleme dolgusu": (t.text, t.progress),
        "metin/ilerleme oluğu": (t.text, t.surface_alt),
        "ipucu": (t.surface, t.text),
    }
    for label, (fg, bg) in pairs.items():
        assert _contrast(fg, bg) >= MIN_CONTRAST, (name, label, fg, bg)


# --- tema seçimi -------------------------------------------------------------------------------


def test_light_is_the_default(monkeypatch):
    monkeypatch.delenv(theme.ENV_VAR, raising=False)
    assert theme.resolve() == theme.LIGHT_NAME
    monkeypatch.setenv(theme.ENV_VAR, "")
    assert theme.resolve() == theme.LIGHT_NAME


@pytest.mark.parametrize(
    ("value", "expected"),
    [("dark", "dark"), (" Dark ", "dark"), ("material", "material"), ("light", "light")],
)
def test_env_var_selects_the_theme(monkeypatch, value, expected):
    monkeypatch.setenv(theme.ENV_VAR, value)
    assert theme.resolve() == expected


def test_explicit_name_wins_over_env(monkeypatch):
    monkeypatch.setenv(theme.ENV_VAR, "dark")
    assert theme.resolve("light") == theme.LIGHT_NAME


def test_unknown_theme_falls_back_to_light_with_warning(monkeypatch, caplog):
    monkeypatch.setenv(theme.ENV_VAR, "mor")
    with caplog.at_level(logging.WARNING, logger="testzede"):
        assert theme.resolve() == theme.LIGHT_NAME
    assert "mor" in caplog.text


# --- uygulama ----------------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(theme.THEMES))
def test_apply_sets_fusion_palette_font_and_stylesheet(qtbot, app_theme, qapp, name):
    app_theme(name)
    t = theme.THEMES[name]
    # Stil sayfası varken qapp.style() Qt'nin sarmalayıcısıdır; SpacingStyle davranışından anlaşılır.
    margin = QStyle.PixelMetric.PM_LayoutLeftMargin
    assert qapp.style().pixelMetric(margin) == theme.SPACE[2]
    assert theme.SpacingStyle().baseStyle().name().lower() == "fusion"
    assert qapp.palette().color(QPalette.ColorRole.Window).name() == t.background.lower()
    assert qapp.palette().color(QPalette.ColorRole.Base).name() == t.surface.lower()
    assert qapp.font().families()[0] == "Segoe UI"
    assert qapp.font().pointSize() == theme.BODY_PT
    qss = qapp.styleSheet()
    assert f"border-radius: {theme.RADIUS_CONTROL}px" in qss
    assert f"border-radius: {theme.RADIUS_CARD}px" in qss
    assert "font-family" not in qss  # font QSS'te verilmez; setFont ezilmez
    assert "box-shadow" not in qss  # Qt QSS'te gölge yok; kenar + ton farkı kullanılır
    widget = QWidget()
    qtbot.addWidget(widget)
    assert styles.is_dark_theme(widget) == t.dark


def test_ui_font_is_proportional_even_without_system_fonts(qapp):
    """Başsız ortamda listedeki fontlar yoksa DejaVu Sans'a düşer; monospace olmaz."""
    info = QFontInfo(theme.ui_font())
    assert not info.fixedPitch(), info.family()


def test_material_fallback_applies_qt_material(app_theme, qapp):
    app_theme(theme.MATERIAL_NAME)
    assert "Roboto" in qapp.styleSheet()
    margin = QStyle.PixelMetric.PM_LayoutLeftMargin
    assert qapp.style().pixelMetric(margin) != theme.SPACE[2]  # boşluk ölçeği uygulanmaz


def test_apply_theme_keeps_the_default_look_when_the_theme_fails(monkeypatch, app_theme, qapp):
    def broken(app, name=None):
        raise RuntimeError("bozuk tema")

    monkeypatch.setattr(theme, "apply", broken)
    _apply_theme(qapp, theme.LIGHT_NAME)  # istisna dışarı sızmaz
    assert qapp.styleSheet() == ""


# --- ölçüler -----------------------------------------------------------------------------------


@pytest.mark.parametrize("factory", [QPushButton, QLineEdit, QComboBox, QSpinBox])
def test_controls_are_at_least_32px_high(qtbot, app_theme, factory):
    app_theme(theme.LIGHT_NAME)
    widget = factory()
    qtbot.addWidget(widget)
    widget.show()
    widget.ensurePolished()
    assert widget.sizeHint().height() >= theme.CONTROL_HEIGHT, factory.__name__


def test_layout_spacing_follows_the_scale(qtbot, app_theme, qapp):
    app_theme(theme.LIGHT_NAME)
    style = qapp.style()
    assert style.pixelMetric(QStyle.PixelMetric.PM_LayoutLeftMargin) in theme.SPACE
    assert style.pixelMetric(QStyle.PixelMetric.PM_LayoutHorizontalSpacing) in theme.SPACE
    widget = QWidget()
    qtbot.addWidget(widget)
    layout = QVBoxLayout(widget)
    layout.addWidget(QLabel("a"))
    margins = layout.contentsMargins()
    assert margins.left() == margins.top() == theme.SPACE[2]


def test_arrow_images_are_drawn_in_the_muted_color(tmp_path, qapp):
    for t in theme.THEMES.values():
        paths = theme.arrow_images(t, tmp_path)
        for name in ("up", "down"):
            image = QImage(paths[name])
            assert not image.isNull(), (t.name, name)
            center = image.pixelColor(image.width() // 2, image.height() // 2)
            assert center.name() == t.muted.lower(), (t.name, name)
            assert image.pixelColor(0, image.height() // 2).alpha() < 255  # kenarlar saydam


# --- durum renklerinin anlamı (STD: yeşil "Kod geçerli", kırmızı hata) ---------------------------


def _hue(color: QColor) -> int:
    return color.hslHue()


@pytest.mark.parametrize("name", list(theme.THEMES))
def test_status_colors_keep_their_meaning_and_contrast(qtbot, app_theme, name):
    app_theme(name)
    widget = QWidget()
    qtbot.addWidget(widget)
    colors = styles.status_colors(widget)
    for key in ("ok", "passed", "covered", "added"):
        assert 90 <= _hue(colors[key].bg) <= 150, key  # yeşil
    for key in ("error", "failed", "missed", "removed"):
        hue = _hue(colors[key].bg)
        assert hue <= 15 or hue >= 340, key  # kırmızı
    for key in ("warning", "timeout", "partial"):
        assert 20 <= _hue(colors[key].bg) <= 45, key  # turuncu
    t = theme.THEMES[name]
    for key, color in colors.items():
        assert _contrast(color.fg, color.bg) >= MIN_CONTRAST, key
        # Tablo hücrelerinde yalnızca yazı rengi kullanılır: kart zeminine karşı da okunur.
        assert _contrast(color.fg, t.surface) >= MIN_CONTRAST, key
