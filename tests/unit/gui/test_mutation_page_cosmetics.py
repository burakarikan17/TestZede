"""Mutasyon sayfası kozmetik davranışları: sütun boyutları, fark hizası, seçim rengi."""

from __future__ import annotations

import ast

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView

from testzede.domain.models import MutationReport, RunStats, TestCase
from testzede.gui.app import apply_theme
from testzede.gui.pages import mutation_logic as logic
from testzede.gui.pages.coverage_page import CoveragePage
from testzede.gui.pages.mutation_page import SELECTION_BG, SELECTION_FG, MutationPage
from testzede.gui.state import AppState
from testzede.gui.styles import HEADER_QSS, MONO_QSS
from testzede.mutation.engine import MutationRun
from testzede.mutation.operators import generate_all

SOURCE = "def f(a):\n    if a > 0:\n        return 1\n    return 2\n"
TESTS = [TestCase("t", "def test_t(): pass", "user")]


def _page_with_result(qtbot) -> MutationPage:
    run = MutationRun(
        report=MutationReport(total=5, killed=3, survived=2, timeout=0),
        stats=RunStats(generated=1, compiled=1, execution_time_s=0.5),
        survivors=generate_all(SOURCE)[:3],
    )
    state = AppState(source=SOURCE, tests=list(TESTS), mutation_run=run)
    page = MutationPage(state)
    qtbot.addWidget(page)
    page.on_enter()
    return page


def _luminance(color: QColor) -> float:
    """WCAG göreli parlaklık."""

    def channel(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.redF())
        + 0.7152 * channel(color.greenF())
        + 0.0722 * channel(color.blueF())
    )


def _contrast(a: QColor, b: QColor) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# --- sütun boyutlandırma -----------------------------------------------------------------------


def test_survivor_table_column_resize_modes(qtbot):
    page = _page_with_result(qtbot)
    header = page.survivors_table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.ResizeToContents
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.ResizeToContents
    assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.Stretch


def test_survivor_table_headers_are_not_clipped(qtbot):
    page = _page_with_result(qtbot)
    page.resize(900, 500)
    page.show()
    qtbot.waitExposed(page)
    header = page.survivors_table.horizontalHeader()
    for column, text in enumerate(["Operatör", "Satır", "Açıklama"]):
        assert header.sectionSize(column) >= header.fontMetrics().horizontalAdvance(text)


def test_survivor_table_matches_coverage_table_resize_style(qtbot):
    page = _page_with_result(qtbot)
    coverage = CoveragePage(AppState())
    qtbot.addWidget(coverage)
    first_stretch = QHeaderView.ResizeMode.Stretch
    assert coverage.function_table.horizontalHeader().sectionResizeMode(0) == first_stretch
    assert page.survivors_table.horizontalHeader().sectionResizeMode(2) == first_stretch


# --- fark hizası -------------------------------------------------------------------------------


@pytest.mark.parametrize("index", range(3))
def test_diff_marker_column_keeps_code_indentation_aligned(index):
    mutant = generate_all(SOURCE)[index]
    diff = logic.mutant_diff(SOURCE, mutant.source)
    original = ast.unparse(ast.parse(SOURCE)).splitlines()
    mutated = mutant.source.splitlines()
    for line in diff.splitlines():
        marker, code = line[0], line[1:]  # her satır tek karakterlik işaret sütunuyla başlar
        assert marker in " -+"
        if marker == "-":
            assert code in original
        elif marker == "+":
            assert code in mutated
        else:  # bağlam satırı da işaret sütunu (boşluk) taşır, kod girintisi bozulmaz
            assert code in original and code in mutated


def test_context_lines_start_with_exactly_one_marker_space():
    diff = logic.mutant_diff("def f(a):\n    return a + 1\n", "def f(a):\n    return a - 1")
    context, removed, added = diff.splitlines()
    assert context == " def f(a):"
    assert removed.index("return") == added.index("return") == 5
    assert context.index("def") == 1  # `return` 4 boşluk girintili: 1 işaret + 4 girinti


# --- seçili satır rengi ------------------------------------------------------------------------


def test_selection_colors_have_strong_contrast():
    assert _contrast(QColor(SELECTION_BG), QColor(SELECTION_FG)) >= 7
    assert _luminance(QColor(SELECTION_BG)) < 0.1  # koyu zemin


def test_selection_style_applies_only_to_the_survivor_table(qtbot):
    page = _page_with_result(qtbot)
    qss = page.survivors_table.styleSheet()
    assert "item:selected" in qss and SELECTION_BG in qss and SELECTION_FG in qss
    assert ":!active" in qss  # odak kaybolunca da okunur kalır
    assert page.styleSheet() == ""
    assert page.diff_view.styleSheet() == MONO_QSS  # yalnızca monospace düzeltmesi, seçim stili yok
    coverage = CoveragePage(AppState())
    qtbot.addWidget(coverage)
    assert coverage.function_table.styleSheet() == HEADER_QSS  # yalnızca başlık düzeltmesi


def test_selected_row_is_painted_dark_with_the_real_theme(qtbot, qapp):
    assert apply_theme(qapp)
    try:
        page = _page_with_result(qtbot)
        page.resize(900, 500)
        page.show()
        qtbot.waitExposed(page)
        table = page.survivors_table
        table.selectRow(0)
        qtbot.wait(50)
        rect = table.visualItemRect(table.item(0, 2))
        selected = table.viewport().grab().toImage().pixelColor(rect.center().x(), rect.top() + 2)
        assert selected.name() == SELECTION_BG
        assert _contrast(selected, QColor(SELECTION_FG)) >= 7
    finally:
        qapp.setStyleSheet("")
