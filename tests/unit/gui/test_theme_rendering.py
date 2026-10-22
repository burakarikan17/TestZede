"""Gerçek temalarla çizim testleri: monospace font ve başlık kırpılması.

İki tema denenir: uygulamanın açık teması (``light``) ve geri dönüş yolu olan qt-material
(``material``). qt-material genel ``* { font-family: Roboto }`` kuralıyla ``setFont``'u ezer ve
``QHeaderView::section { text-transform: uppercase }`` ile başlıkları, boyut hesabında
kullanılmayan BÜYÜK harfle çizer; ``styles`` düzeltmeleri bu yüzden vardır. Açık temada bu iki
kök neden yoktur (font QSS'te verilmez, başlıklar yazıldığı gibi çizilir).
Bu testler widget bayraklarına değil, temalı pencerede gerçekten çizilen sonuca
(font ölçüleri, ``grab`` pikselleri) bakar.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QFontMetricsF, QImage, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QTableWidget, QTableWidgetItem
from result_builders import make_result

from testzede.domain.models import MutationReport, RunStats, TestCase
from testzede.gui import styles, theme
from testzede.gui.main_window import PAGES, MainWindow
from testzede.gui.pages.coverage_page import CoveragePage
from testzede.gui.pages.mutation_page import MutationPage
from testzede.mutation.engine import MutationRun
from testzede.mutation.operators import generate_all

SOURCE = "def f(a):\n    if a > 0:\n        return 1\n    return 2\n"
# Tablo başlığı yatay iç boşluğu: qt-material ``padding: 0 24px``, açık tema ``HEADER_PADDING``.
PADDINGS = {theme.LIGHT_NAME: theme.HEADER_PADDING, theme.MATERIAL_NAME: 24}


@pytest.fixture(params=list(PADDINGS))
def themed(request, qtbot, app_theme) -> MainWindow:
    """Tema uygulanmış, sonuçları yüklenmiş, görünür ana pencere (``theme_name`` özniteliğiyle)."""
    app_theme(request.param)
    window = MainWindow()
    window.theme_name = request.param
    qtbot.addWidget(window)
    state = window.state
    state.source = SOURCE
    state.tests = [TestCase("t", "def test_t(): pass", "user")]
    state.execution_result = make_result(
        {1, 2, 3, 4}, {1, 2, 3}, {(2, 3), (2, 4)}, {(2, 3)}, {"f": 0.75}, {"t": "passed"}
    )
    returns_none = [m for m in generate_all(SOURCE) if m.operator == "RETURN_NONE" and m.line == 4]
    state.mutation_run = MutationRun(
        report=MutationReport(1, 0, 1, 0),
        stats=RunStats(1, 1, 0.5),
        survivors=generate_all(SOURCE)[:3] + returns_none,
    )
    window.resize(1200, 700)
    window.show()
    qtbot.waitExposed(window)
    for page in (CoveragePage, MutationPage):  # on_enter sonuçları çizer
        row = PAGES.index(page)
        window.nav.setCurrentRow(row)
        qtbot.wait(20)
    return window


@pytest.fixture
def material(app_theme) -> None:
    """Yalnızca qt-material: ``styles`` düzeltmelerinin kök nedenleri bu temadadır."""
    app_theme(theme.MATERIAL_NAME)


def _is_proportional(widget) -> bool:
    fm = widget.fontMetrics()
    return fm.horizontalAdvance("i") != fm.horizontalAdvance("W")


# --- monospace ---------------------------------------------------------------------------------


def test_four_code_views_are_really_monospace_under_the_theme(themed):
    code, coverage, mutation = (themed.page(n) for n in ("Kod Yükle", "Coverage", "Mutasyon"))
    views = {
        "kaynak editörü": code.editor,
        "test editörü": code.tests_editor,
        "coverage kaynak görünümü": coverage.source_view,
        "mutasyon fark alanı": mutation.diff_view,
    }
    for name, view in views.items():
        view.ensurePolished()
        fm = view.fontMetrics()
        assert QFontInfo(view.font()).fixedPitch(), name
        assert fm.horizontalAdvance("i") == fm.horizontalAdvance("W"), name


def test_monospace_fix_does_not_leak_to_other_widgets(themed):
    code, coverage = themed.page("Kod Yükle"), themed.page("Coverage")
    # Diğer widget'lar temanın arayüz fontuyla çizilir: qt-material'de Roboto, açık temada
    # theme.ui_font() (Segoe UI; yoksa sıradaki sans-serif).
    expected = (
        "Roboto"
        if themed.theme_name == theme.MATERIAL_NAME
        else QFontInfo(theme.ui_font()).family()
    )
    for widget in (code.status_label, coverage.run_button, coverage.function_table):
        widget.ensurePolished()
        assert _is_proportional(widget)
        assert QFontInfo(widget.font()).family() == expected


def test_without_the_fix_the_theme_overrides_set_font(qtbot, material):
    plain = QPlainTextEdit()
    qtbot.addWidget(plain)
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setFixedPitch(True)
    plain.setFont(font)
    plain.show()
    plain.ensurePolished()
    assert _is_proportional(plain)  # kök neden: tema setFont'u eziyor


def test_light_theme_keeps_set_font(qtbot, app_theme):
    """Açık tema fontu QSS'te vermez: düzeltmesiz editörde de ``setFont`` geçerli kalır."""
    app_theme(theme.LIGHT_NAME)
    styles._register_fallback_font()  # başsız ortamda da bir monospace font olsun
    plain = QPlainTextEdit()
    qtbot.addWidget(plain)
    plain.setFont(QFont("DejaVu Sans Mono"))
    plain.show()
    plain.ensurePolished()
    assert QFontInfo(plain.font()).family() == "DejaVu Sans Mono"
    assert not _is_proportional(plain)


def test_fallback_font_is_registered_once(themed):
    families = QFontDatabase.families()
    assert "DejaVu Sans Mono" in families
    styles._register_fallback_font()  # tekrar çağrı zararsız
    assert QFontDatabase.families().count("DejaVu Sans Mono") == 1


# --- fark alanında hiza ------------------------------------------------------------------------


def _row_rect(view: QPlainTextEdit, number: int):
    block = view.document().findBlockByNumber(number)
    rect = view.blockBoundingGeometry(block).translated(view.contentOffset()).toRect()
    # Son blok belgenin alt kenar boşluğunu da kapsar; satır vurgusu orada bitmiş olur.
    rect.setHeight(min(rect.height(), view.fontMetrics().lineSpacing()))
    return rect


def _char_x(view: QPlainTextEdit, number: int, column: int) -> int:
    block = view.document().findBlockByNumber(number)
    cursor = QTextCursor(block)
    cursor.setPosition(block.position() + column)
    return view.cursorRect(cursor).x()


def _glyph_mask(img: QImage, x: int, width: int, rect) -> list[list[bool]]:
    """Satır zemininden parlaklığı belirgin farklı pikselleri (yazı) işaretler; dikeyde yazıya kırpılır.

    Fark mutlak alınır: açık temada yazı zeminden koyu, koyu temada açıktır. Komşu satırların
    zemini sayılmasın diye yalnızca satırın içi taranır (yuvarlamaya karşı 1 piksel pay bırakılır);
    boş üst/alt satırlar atılır.
    """
    # Zemin, aynı satırda yazıdan hemen önceki (boşluk) hücrenin ortasından okunur.
    bg = img.pixelColor(x - width // 12, rect.center().y()).lightness()
    rows = [
        [abs(img.pixelColor(px, py).lightness() - bg) > 60 for px in range(x, x + width)]
        for py in range(rect.top() + 1, rect.bottom())
    ]
    inked = [i for i, row in enumerate(rows) if any(row)]
    return rows[inked[0] : inked[-1] + 1] if inked else []


def _mismatch(a: list[list[bool]], b: list[list[bool]]) -> float:
    """İki maske arasında farklı piksellerin oranı."""
    if len(a) != len(b):
        return 1.0
    total = sum(len(row) for row in a)
    return (
        sum(p != q for ra, rb in zip(a, b, strict=True) for p, q in zip(ra, rb, strict=True))
        / total
    )


def test_diff_marker_and_code_columns_line_up_when_rendered(themed):
    page = themed.page("Mutasyon")
    target = next(
        r
        for r in range(page.survivors_table.rowCount())
        if page.survivors_table.item(r, 0).text() == "RETURN_NONE"
        and page.survivors_table.item(r, 1).text() == "4"
    )
    page.survivors_table.selectRow(target)
    view = page.diff_view
    themed.repaint()
    lines = view.toPlainText().splitlines()
    removed = next(i for i, line in enumerate(lines) if line == "-    return 2")
    added = next(i for i, line in enumerate(lines) if line == "+    return None")
    context = next(i for i, line in enumerate(lines) if line == "         return 1")

    cw = view.fontMetrics().horizontalAdvance("W")
    assert cw == view.fontMetrics().horizontalAdvance("i")
    # `return` iki farklı işaretli satırda da 5. sütunda: aynı x; 4 girinti + 1 işaret sütunu.
    assert _char_x(view, removed, 5) == _char_x(view, added, 5)
    # Glif genişliği kesirli olabilir (macOS'ta Menlo ~7.8 px); 4 sütunluk kayma yuvarlamayla 1 px oynar.
    advance = QFontMetricsF(view.font()).horizontalAdvance("W")
    shift = _char_x(view, context, 9) - _char_x(view, removed, 5)  # 8 girinti + işaret
    assert abs(shift - 4 * advance) <= 1

    # Çizilen piksellerde de aynı: iki satırdaki "return" sözcüğünün glif maskesi özdeş.
    img = view.viewport().grab().toImage()
    x = _char_x(view, removed, 5)
    mask_removed = _glyph_mask(img, x, 6 * cw, _row_rect(view, removed))
    mask_added = _glyph_mask(img, x, 6 * cw, _row_rect(view, added))
    assert any(any(row) for row in mask_removed)  # gerçekten yazı çizilmiş
    # Kenar yumuşatma kırmızı/yeşil zeminde birkaç pikseli farklı yapar: küçük fark kabul edilir,
    # ama bir karakter kaydırılmış hizalama açıkça büyük fark verir (testin duyarlılığı).
    shifted = _glyph_mask(img, x + cw, 6 * cw, _row_rect(view, added))
    assert _mismatch(mask_removed, mask_added) < 0.08
    assert _mismatch(mask_removed, shifted) > 0.25


# --- tablo başlıkları --------------------------------------------------------------------------


def _header_text_extent(header, section: int) -> tuple[int, int] | None:
    """Başlık bölümünde çizilen metnin yatay sınırları (bölüme göre), yoksa ``None``."""
    img = header.grab().toImage()
    x0, width = header.sectionViewportPosition(section), header.sectionSize(section)
    bg = img.pixelColor(x0 + 3, 3)
    xs = [
        x - x0
        for x in range(x0 + 2, x0 + width - 2)
        for y in range(4, img.height() - 4)
        if abs(img.pixelColor(x, y).red() - bg.red())
        + abs(img.pixelColor(x, y).green() - bg.green())
        + abs(img.pixelColor(x, y).blue() - bg.blue())
        > 120
    ]
    return (min(xs), max(xs)) if xs else None


def _our_tables(window: MainWindow) -> dict[str, QTableWidget]:
    coverage, mutation = window.page("Coverage"), window.page("Mutasyon")
    return {
        "Coverage fonksiyon": coverage.function_table,
        "Coverage test": coverage.test_table,
        "Mutasyon": mutation.survivors_table,
    }


def test_header_text_is_fully_drawn_in_our_three_tables(themed):
    padding = PADDINGS[themed.theme_name]
    for name, table in _our_tables(themed).items():
        header = table.horizontalHeader()
        header.ensurePolished()
        for column in range(table.columnCount()):
            text = table.horizontalHeaderItem(column).text()
            advance = header.fontMetrics().horizontalAdvance(text)
            extent = _header_text_extent(header, column)
            assert extent is not None, (name, text)
            left, right = extent
            width = header.sectionSize(column)
            # Metin, padding içindeki metin alanına sığar (kırpılmaz) ...
            assert left >= padding - 1 and right <= width - padding + 1, (name, text, extent, width)
            # ... ve BÜYÜK harfe çevrilmeden, ölçülen genişlikte çizilir.
            assert right - left <= advance + 3, (name, text, right - left, advance)


def test_header_section_is_wide_enough_for_the_drawn_text(themed):
    padding = PADDINGS[themed.theme_name]
    for name, table in _our_tables(themed).items():
        header = table.horizontalHeader()
        for column in range(table.columnCount()):
            text = table.horizontalHeaderItem(column).text()
            assert header.sectionSize(
                column
            ) - 2 * padding >= header.fontMetrics().horizontalAdvance(text), (name, text)


def _unfixed_table(qtbot) -> QTableWidget:
    """``fix_table_header`` uygulanmamış, dar sütunlu, görünür tablo."""
    from PySide6.QtWidgets import QHeaderView

    table = QTableWidget(1, 2)
    qtbot.addWidget(table)
    table.setHorizontalHeaderLabels(["Operatör", "Satır"])
    table.setItem(0, 0, QTableWidgetItem("x"))
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.resize(500, 200)
    table.show()
    qtbot.waitExposed(table)
    table.horizontalHeader().ensurePolished()
    return table


def _clipped_headers(table: QTableWidget, padding: int) -> list[str]:
    """BÜYÜK harf çizildiği (ölçülenden geniş) ya da iç boşluğa taştığı için kırpılan başlıklar."""
    header = table.horizontalHeader()
    clipped = []
    for column, text in enumerate(["Operatör", "Satır"]):
        left, right = _header_text_extent(header, column)
        advance = header.fontMetrics().horizontalAdvance(text)
        if right - left > advance + 3 or right > header.sectionSize(column) - padding:
            clipped.append(text)
    return clipped


def test_unfixed_table_shows_the_uppercase_clipping_root_cause(qtbot, material):
    """Kontrol: qt-material'de düzeltmesiz başlık BÜYÜK harf çizilir ve dar sütunda taşar."""
    clipped = _clipped_headers(_unfixed_table(qtbot), PADDINGS[theme.MATERIAL_NAME])
    assert clipped, "tema başlığı artık BÜYÜK harf çizmiyor olabilir; düzeltme gereksiz kalabilir"


def test_light_theme_draws_unfixed_headers_as_written(qtbot, app_theme):
    """Açık temada kök neden yok: düzeltmesiz başlık da yazıldığı gibi, kırpılmadan çizilir."""
    app_theme(theme.LIGHT_NAME)
    assert _clipped_headers(_unfixed_table(qtbot), PADDINGS[theme.LIGHT_NAME]) == []


# --- styles birim testleri ---------------------------------------------------------------------


def test_fix_table_header_is_idempotent_and_keeps_existing_style(qtbot):
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)
    table.setStyleSheet("QTableWidget { gridline-color: red; }")
    styles.fix_table_header(table)
    styles.fix_table_header(table)
    assert table.styleSheet().count(styles.HEADER_QSS) == 1
    assert "gridline-color: red" in table.styleSheet()


def test_apply_monospace_sets_font_and_scoped_stylesheet(qtbot):
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    styles.apply_monospace(editor)
    assert editor.font().fixedPitch()
    assert editor.styleSheet() == styles.MONO_QSS
    assert '"DejaVu Sans Mono"' in styles.MONO_QSS and "Consolas" in styles.MONO_QSS
