"""Coverage sayfası fonksiyon tablosu başlığı: sütun boyutlandırma ve açıklama."""

from __future__ import annotations

from PySide6.QtWidgets import QHeaderView
from result_builders import make_result

from testzede.domain.models import TestCase
from testzede.gui.pages.coverage_page import FUNCTION_COLUMN_TIP, CoveragePage
from testzede.gui.state import AppState


def _page(qtbot) -> CoveragePage:
    page = CoveragePage(
        AppState(source="x = 1", tests=[TestCase("t", "def test_t(): pass", "user")])
    )
    qtbot.addWidget(page)
    return page


def test_percent_column_header_has_explanatory_tooltip(qtbot):
    page = _page(qtbot)
    item = page.function_table.horizontalHeaderItem(1)
    assert item.text() == "Kapsama %"
    assert item.toolTip() == FUNCTION_COLUMN_TIP
    assert "birleşik yüzdesi" in item.toolTip()
    assert "'Satır' yalnızca satır kapsamasıdır" in item.toolTip()


def test_function_table_columns_resize_policy(qtbot):
    page = _page(qtbot)
    header = page.function_table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.ResizeToContents


def test_percent_header_text_is_not_clipped(qtbot):
    page = _page(qtbot)
    page.resize(900, 500)
    page.show()
    qtbot.waitExposed(page)
    header = page.function_table.horizontalHeader()
    needed = header.fontMetrics().horizontalAdvance("Kapsama %")
    assert header.sectionSize(1) >= needed
    # Sonuç yüklenince de başlık kesilmez.
    page._render(make_result(per_function={"f": 0.5}), "x = 1", [])
    assert header.sectionSize(1) >= needed
