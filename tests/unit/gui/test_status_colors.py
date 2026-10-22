"""Durum renkleri: uygulamanın açık (varsayılan) ve koyu temasında, ayrıca geri dönüş yolu olan
qt-material (light_blue) temasında gerçek çizim.

Her durum için çizilen zemin pikseli ve o bölgedeki en belirgin yazı pikseli okunur; WCAG
kontrast oranı en az 4.5:1 olmalıdır (normal metin, AA).
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QLabel, QPlainTextEdit
from result_builders import make_result

from testzede.domain.models import MutationReport, RunStats, TestCase
from testzede.gui import styles, theme
from testzede.gui.main_window import PAGES, MainWindow
from testzede.gui.pages.code_page import CodePage
from testzede.gui.pages.coverage_page import CoveragePage
from testzede.gui.pages.mutation_page import MutationPage
from testzede.mutation.engine import MutationRun
from testzede.mutation.operators import generate_all

SOURCE = "def f(a):\n    if a > 0:\n        return 1\n    return 2\n"
TESTS = [
    TestCase(name, f"def {name}(): pass", "user") for name in ("t_ok", "t_bad", "t_slow", "t_err")
]
MIN_CONTRAST = 4.5
# MainWindow.nav satırları (sayfa sırası değişse de doğru kalsın diye sınıftan bulunur)
CODE, COVERAGE, MUTATION = (PAGES.index(c) for c in (CodePage, CoveragePage, MutationPage))


def _luminance(color: QColor) -> float:
    """WCAG göreli parlaklık."""

    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.redF())
        + 0.7152 * channel(color.greenF())
        + 0.0722 * channel(color.blueF())
    )


def _contrast(a: QColor, b: QColor) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _ink(img: QImage, bg: QColor, left: int, top: int, right: int, bottom: int) -> QColor:
    """Bölgede zemine göre en yüksek kontrastlı piksel: çizilen yazının rengi."""
    pixels = (
        img.pixelColor(x, y)
        for x in range(max(left, 0), min(right, img.width()))
        for y in range(max(top, 0), min(bottom, img.height()))
    )
    return max(pixels, key=lambda color: _contrast(color, bg))


@pytest.fixture(params=[theme.LIGHT_NAME, theme.DARK_NAME, theme.MATERIAL_NAME])
def themed(request, qtbot, app_theme):
    """Temalı, sonuçları yüklenmiş, görünür ana pencere ve tema adı."""
    app_theme(request.param)
    window = MainWindow()
    qtbot.addWidget(window)
    state = window.state
    state.source = SOURCE
    state.tests = list(TESTS)
    state.execution_result = make_result(
        {1, 2, 3, 4},
        {1, 2, 3},
        {(2, 3), (2, 4)},
        {(2, 3)},
        {"f": 0.75},
        {"t_ok": "passed", "t_bad": "failed", "t_slow": "timeout"},  # t_err: sonuç yok -> hata
    )
    state.mutation_run = MutationRun(
        report=MutationReport(3, 0, 3, 0),
        stats=RunStats(1, 1, 0.5),
        survivors=generate_all(SOURCE)[:3],
    )
    window.resize(1200, 700)
    window.show()
    qtbot.waitExposed(window)
    for row in (COVERAGE, MUTATION):  # on_enter sonuçları çizer
        window.nav.setCurrentRow(row)
        qtbot.wait(20)
    return window, request.param


def _editor_rows(view: QPlainTextEdit, numbers: list[int]) -> dict[int, tuple[QColor, QColor]]:
    """Editör satırlarının çizilen (yazı, zemin) renkleri; zemin satırın sağ ucundan okunur."""
    img = view.viewport().grab().toImage()
    out = {}
    for number in numbers:
        block = view.document().findBlockByNumber(number)
        rect = view.blockBoundingGeometry(block).translated(view.contentOffset()).toRect()
        top = rect.top() + 1
        bottom = rect.top() + view.fontMetrics().lineSpacing() - 1
        bg = img.pixelColor(img.width() - 3, (top + bottom) // 2)
        out[number] = (_ink(img, bg, 0, top, img.width(), bottom), bg)
    return out


def _label_colors(label: QLabel) -> tuple[QColor, QColor]:
    """Etiketin çizilen (yazı, zemin) renkleri; zemin sol iç boşluktan okunur."""
    img = label.grab().toImage()
    bg = img.pixelColor(3, img.height() // 2)
    return _ink(img, bg, 0, 0, img.width(), img.height()), bg


def test_theme_is_detected_from_the_rendered_window(themed):
    window, name = themed
    for row in (CODE, COVERAGE, MUTATION):
        assert styles.is_dark_theme(window.pages[row]) == (name == theme.DARK_NAME)


def test_every_status_pair_meets_wcag_aa_on_paper(themed):
    window, _ = themed
    for name, color in window.page("Coverage").colors.items():
        assert _contrast(color.fg, color.bg) >= MIN_CONTRAST, name


def test_coverage_line_highlights_are_drawn_and_readable(themed):
    window, _ = themed
    page = window.page("Coverage")
    colors = page.colors
    expected = {0: "covered", 1: "partial", 2: "covered", 3: "missed"}
    assert len(page.source_view.extraSelections()) == 4
    for number, (ink, bg) in _editor_rows(page.source_view, list(expected)).items():
        status = expected[number]
        assert bg.name() == colors[status].bg.name(), status  # vurgu gerçekten çizildi
        assert _contrast(ink, bg) >= MIN_CONTRAST, status


def test_coverage_outcome_cells_are_readable(themed):
    """Hücrelerde yalnızca yazı rengi var; zemin temanın tablo zeminidir (stil sayfası çizer)."""
    window, _ = themed
    page = window.page("Coverage")
    table = page.test_table
    img = table.viewport().grab().toImage()
    for row, outcome in enumerate(("passed", "failed", "timeout", "error")):
        rect = table.visualItemRect(table.item(row, 1))
        bg = img.pixelColor(rect.left() + 2, rect.top() + 2)
        ink = _ink(img, bg, rect.left(), rect.top(), rect.right(), rect.bottom())
        assert _contrast(ink, bg) >= MIN_CONTRAST, outcome
        # Çizilen yazı durum rengidir (temanın varsayılan yazı rengi değil).
        assert _contrast(ink, page.colors[outcome].fg) < 1.5, outcome


def test_mutation_diff_lines_are_readable(themed):
    window, _ = themed
    page = window.page("Mutasyon")
    page.survivors_table.selectRow(0)
    lines = page.diff_view.toPlainText().splitlines()
    marked = {
        i: ("added" if line[0] == "+" else "removed")
        for i, line in enumerate(lines)
        if line[:1] in "+-" and line[:3] not in ("+++", "---")
    }
    assert set(marked.values()) == {"added", "removed"}
    for number, (ink, bg) in _editor_rows(page.diff_view, list(marked)).items():
        assert bg.name() == page.colors[marked[number]].bg.name(), lines[number]
        assert _contrast(ink, bg) >= MIN_CONTRAST, lines[number]


@pytest.mark.parametrize("kind", ["ok", "error", "warn"])
def test_coverage_and_mutation_status_labels_are_readable(themed, kind):
    window, _ = themed
    for title in ("Coverage", "Mutasyon"):
        page = window.page(title)
        page._set_status("Durum mesajı örneği", kind)
        ink, bg = _label_colors(page.status_label)
        assert _contrast(ink, bg) >= MIN_CONTRAST, (title, kind)


def test_stale_notes_are_readable(themed):
    window, _ = themed
    for title in ("Coverage", "Mutasyon"):
        note = window.page(title).note_label
        note.show()
        ink, bg = _label_colors(note)
        assert _contrast(ink, bg) >= MIN_CONTRAST, title


def test_code_page_status_labels_are_readable(themed):
    window, _ = themed
    page = window.page("Kod Yükle")
    for source, status in (("def f(:\n", "error"), (SOURCE, "ok")):
        page.editor.setPlainText(source)
        page.validate()
        assert page.status_label.property("status") == status
        ink, bg = _label_colors(page.status_label)
        assert bg.name() == page.colors[status].bg.name(), status
        assert _contrast(ink, bg) >= MIN_CONTRAST, status


def test_info_status_has_no_color(themed):
    window, _ = themed
    page = window.page("Coverage")
    page._set_status("Çalışıyor...", "info")
    assert page.status_label.styleSheet() == ""
