"""Sağ üstteki açık/koyu tema düğmesi: konum, geçiş animasyonu, renklerin yeni temaya çevrilmesi."""

from __future__ import annotations

import pytest
from matplotlib.colors import to_rgba
from PySide6.QtCore import QPoint
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QWidget,
)
from result_builders import make_result

from testzede.domain.models import TestCase
from testzede.gui import styles, theme
from testzede.gui.main_window import PAGES, MainWindow
from testzede.gui.pages.call_graph_page import PAGE_TITLE as CALL_GRAPH
from testzede.gui.pages.coverage_page import CoveragePage
from testzede.gui.pages.graph_canvas import palette_for
from testzede.gui.theme_switch import FADE_MS, TIP_TO_DARK, TIP_TO_LIGHT, ThemeSwitch

SOURCE = "def f(a):\n    if a > 0:\n        return 1\n    return 2\n"
COVERAGE = PAGES.index(CoveragePage)


@pytest.fixture
def window(qtbot, app_theme) -> MainWindow:
    """Açık temalı, Coverage sonucu çizilmiş, görünür ana pencere."""
    app_theme(theme.LIGHT_NAME)
    win = MainWindow()
    qtbot.addWidget(win)
    state = win.state
    state.source = SOURCE
    state.tests = [TestCase("t_ok", "def t_ok(): pass", "user")]
    state.execution_result = make_result(
        {1, 2, 3, 4}, {1, 2, 3}, {(2, 3), (2, 4)}, {(2, 3)}, {"f": 0.75}, {"t_ok": "passed"}
    )
    win.resize(1200, 700)
    win.show()
    qtbot.waitExposed(win)
    win.nav.setCurrentRow(COVERAGE)
    qtbot.wait(20)
    return win


def _wait_fade(qtbot, switch: ThemeSwitch) -> None:
    qtbot.waitUntil(lambda: not switch.fading, timeout=FADE_MS * 5)


# --- yer ve görünüm ----------------------------------------------------------------------------


def test_switch_sits_in_the_top_right_corner(window):
    switch = window.theme_switch
    top_left = switch.mapTo(window, QPoint(0, 0))
    right = top_left.x() + switch.width()
    assert window.width() - right <= 2 * theme.SPACE[3]  # sağ kenara yakın
    assert top_left.y() <= theme.SPACE[3]  # üst kenarda
    nav_top = window.nav.mapTo(window, QPoint(0, 0)).y()
    assert top_left.y() + switch.height() <= nav_top  # menü ve sayfaların üstünde, onları örtmez
    assert switch.isVisible()


def test_switch_does_not_change_page_names_or_order(window):
    titles = [window.nav.item(i).text() for i in range(window.nav.count())]
    assert titles == [page.title for page in window.pages]


def test_tooltip_and_accessible_name_follow_the_state(qtbot, window):
    switch = window.theme_switch
    assert not switch.isChecked()
    assert switch.toolTip() == switch.accessibleName() == TIP_TO_DARK
    switch.click()
    assert switch.isChecked()
    assert switch.toolTip() == switch.accessibleName() == TIP_TO_LIGHT
    _wait_fade(qtbot, switch)


# --- geçiş -------------------------------------------------------------------------------------


def test_click_switches_to_dark_with_a_fade_and_back(qtbot, window):
    switch = window.theme_switch
    page = window.page("Coverage")
    switch.click()
    assert theme.current() == theme.DARK_NAME
    assert styles.is_dark_theme(page)
    assert switch.fading  # eski görünüm üstte, saydamlaşarak kayboluyor
    overlay = switch._overlay
    assert overlay.geometry() == window.rect()
    _wait_fade(qtbot, switch)
    assert switch._overlay is None

    switch.click()
    assert theme.current() == theme.LIGHT_NAME
    assert not styles.is_dark_theme(page)
    _wait_fade(qtbot, switch)


def test_fade_goes_from_opaque_to_transparent(qtbot, window):
    switch = window.theme_switch
    switch.click()
    effect = switch._overlay.graphicsEffect()
    assert effect.opacity() == pytest.approx(1.0, abs=0.05)
    qtbot.wait(FADE_MS // 2)
    if switch.fading:  # yavaş makinede animasyon bitmiş olabilir
        assert 0.0 < effect.opacity() < 1.0
    _wait_fade(qtbot, switch)


def test_rapid_clicks_leave_no_overlay_behind(qtbot, window):
    switch = window.theme_switch
    for _ in range(3):
        switch.click()
    assert theme.current() == theme.DARK_NAME  # tek sayıda basış: koyu
    _wait_fade(qtbot, switch)
    qtbot.wait(20)  # deleteLater
    overlays = [w for w in window.findChildren(QLabel) if w.pixmap() and not w.pixmap().isNull()]
    assert overlays == []


def test_switch_without_animation_applies_at_once(window):
    switch = window.theme_switch
    switch.switch(theme.DARK_NAME, animate=False)
    assert theme.current() == theme.DARK_NAME and switch.isChecked() and not switch.fading


def test_switch_is_hidden_under_the_material_fallback(qtbot, app_theme):
    app_theme(theme.MATERIAL_NAME)
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()
    assert not win.theme_switch.isVisible()


def test_switch_starts_checked_when_the_app_starts_dark(qtbot, app_theme):
    app_theme(theme.DARK_NAME)
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.theme_switch.isChecked()
    assert win.theme_switch.toolTip() == TIP_TO_LIGHT


# --- çizilmiş renklerin yeni temaya çevrilmesi -------------------------------------------------


def test_drawn_status_colors_follow_the_theme(qtbot, window):
    page = window.page("Coverage")
    page._set_status("Durum mesajı örneği", "ok")
    window.theme_switch.click()
    dark = styles.status_colors(page)
    # Sayfanın renk sözlüğü (sonraki çizimler) yeni temada
    assert page.colors["passed"].fg == dark["passed"].fg
    # Çizilmiş durum etiketi
    assert dark["ok"].bg.name() in page.status_label.styleSheet()
    # Tablo hücresi (yalnızca yazı rengi)
    cell = page.test_table.item(0, 1)
    assert cell.foreground().color() == dark["passed"].fg
    # Kaynak görünümündeki satır vurguları
    backgrounds = {s.format.background().color().name() for s in page.source_view.extraSelections()}
    assert backgrounds <= {dark[k].bg.name() for k in ("covered", "partial", "missed")}
    _wait_fade(qtbot, window.theme_switch)


def test_call_graph_is_redrawn_with_the_new_background(qtbot, window):
    canvas = window.page(CALL_GRAPH).canvas
    window.theme_switch.click()
    assert canvas.figure.get_facecolor() == to_rgba(palette_for(True).background)
    window.theme_switch.click()
    assert canvas.figure.get_facecolor() == to_rgba(palette_for(False).background)
    _wait_fade(qtbot, window.theme_switch)


# --- styles.recolor birim testleri -------------------------------------------------------------


def _maps() -> tuple[dict, dict]:
    light = {k: styles.StatusColor(QColor(fg), QColor(bg)) for k, (fg, bg) in styles._LIGHT.items()}
    dark = {k: styles.StatusColor(QColor(fg), QColor(bg)) for k, (fg, bg) in styles._DARK.items()}
    for alias, name in styles._ALIASES.items():
        light[alias], dark[alias] = light[name], dark[name]
    return light, dark


def test_recolor_maps_each_status_to_its_counterpart(qtbot):
    light, dark = _maps()
    root = QWidget()
    qtbot.addWidget(root)
    labels = {}
    for key in ("covered", "passed", "missed", "timeout"):  # aynı yazı rengi farklı zemin dahil
        label = QLabel(key, root)
        styles.set_status_style(label, light[key])
        labels[key] = label
    plain = QLabel("renksiz", root)
    table = QTableWidget(3, 1, root)
    for row, key in enumerate(("passed", "failed", "timeout")):
        item = QTableWidgetItem(key)
        item.setForeground(QBrush(light[key].fg))
        table.setItem(row, 0, item)
    editor = QPlainTextEdit("a\nb", root)
    selection = QTextEdit.ExtraSelection()
    selection.format.setBackground(light["missed"].bg)
    selection.format.setForeground(light["missed"].fg)
    editor.setExtraSelections([selection])
    root.colors = dict(light)

    styles.recolor(root, light, dark)

    for key, label in labels.items():
        assert dark[key].fg.name() in label.styleSheet(), key
        assert dark[key].bg.name() in label.styleSheet(), key
    assert plain.styleSheet() == ""
    for row, key in enumerate(("passed", "failed", "timeout")):
        assert table.item(row, 0).foreground().color() == dark[key].fg, key
    redrawn = editor.extraSelections()  # liste tutulmazsa format nesnesi silinir
    fmt = redrawn[0].format
    assert fmt.background().color() == dark["missed"].bg
    assert fmt.foreground().color() == dark["missed"].fg
    assert root.colors["passed"].fg == dark["passed"].fg


def test_recolor_leaves_unrelated_cells_alone(qtbot):
    light, dark = _maps()
    table = QTableWidget(2, 1)
    qtbot.addWidget(table)
    table.setItem(0, 0, QTableWidgetItem("varsayılan"))
    custom = QTableWidgetItem("özel")
    custom.setForeground(QBrush(QColor("#123456")))
    table.setItem(1, 0, custom)
    styles.recolor(table, light, dark)
    assert table.item(1, 0).foreground().color().name() == "#123456"
    assert table.item(0, 0).foreground().style().name == "NoBrush"
