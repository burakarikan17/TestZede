"""Çağrı grafiği çizimi (matplotlib) ve ``GraphCanvas`` bileşeni."""

from __future__ import annotations

import pytest
from matplotlib.backend_bases import MouseEvent
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import to_rgba
from matplotlib.figure import Figure
from qt_material import apply_stylesheet

from testzede.gui.pages.graph_canvas import (
    DARK,
    EMPTY_GRAPH,
    KIND_STYLES,
    LIGHT,
    PLACEHOLDER,
    GraphCanvas,
    draw_call_graph,
    nearest_node,
    palette_for,
)
from testzede.services.analysis_service import AnalysisService

SOURCE = (
    "import math\n"
    "def fact(n):\n    return 1 if n < 2 else n * fact(n - 1)\n"
    "def main(x):\n    print(len(str(fact(x))), math.sqrt(x))\n"
    "main(3)\n"
)
VIEW = AnalysisService().call_graph(SOURCE)


def new_axes():
    figure = Figure(figsize=(8, 5), layout="constrained")
    FigureCanvasAgg(figure)
    return figure, figure.add_subplot(111)


def arrows(ax):
    return [p for p in ax.patches if p.__class__.__name__ == "FancyArrowPatch"]


def is_highlight(patch, palette) -> bool:
    return tuple(patch.get_edgecolor()[:3]) == tuple(to_rgba(palette.highlight)[:3])


# ---- çizim ---------------------------------------------------------------------------


def test_every_edge_gets_an_arrow_and_every_node_a_label():
    _, ax = new_axes()
    draw_call_graph(ax, VIEW, dark=False)
    assert len(arrows(ax)) == len(VIEW.edges)
    assert sorted(t.get_text() for t in ax.texts) == sorted(n.label for n in VIEW.nodes)


def test_legend_lists_only_the_kinds_present():
    _, ax = new_axes()
    draw_call_graph(ax, VIEW, dark=False)
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert labels == [style.label for style in KIND_STYLES.values()]  # dört tür de var
    only_functions = AnalysisService().call_graph("def a():\n    b()\n\ndef b():\n    pass\n")
    _, ax = new_axes()
    draw_call_graph(ax, only_functions, dark=False)
    assert [t.get_text() for t in ax.get_legend().get_texts()] == ["Fonksiyon"]


def test_kinds_differ_by_shape_not_only_by_color():
    assert len({style.marker for style in KIND_STYLES.values()}) == len(KIND_STYLES)
    assert len({style.color for style in KIND_STYLES.values()}) == len(KIND_STYLES)


def test_recursion_is_drawn_as_a_loop_arrow():
    _, ax = new_axes()
    draw_call_graph(ax, VIEW, dark=False)
    loops = [p for p in arrows(ax) if p._posA_posB[0][0] != p._posA_posB[1][0]]
    # özyineleme halkası dışındaki oklar farklı düğümlere gider; halka aynı y'de yan yana iki nokta
    assert len(arrows(ax)) == len(VIEW.edges)
    assert any(p._posA_posB[0][1] == p._posA_posB[1][1] for p in loops)


def test_no_view_shows_the_placeholder_and_empty_graph_the_explanation():
    _, ax = new_axes()
    draw_call_graph(ax, None, dark=False)
    assert [t.get_text() for t in ax.texts] == [PLACEHOLDER]
    draw_call_graph(ax, AnalysisService().call_graph("x = 1\n"), dark=False)
    assert [t.get_text() for t in ax.texts] == [EMPTY_GRAPH]
    assert not arrows(ax)


@pytest.mark.parametrize("dark", [False, True])
def test_theme_palette_is_applied(dark):
    figure, ax = new_axes()
    draw_call_graph(ax, VIEW, dark=dark)
    palette = palette_for(dark)
    assert palette is (DARK if dark else LIGHT)
    assert figure.get_facecolor() == to_rgba(palette.background)
    assert {t.get_color() for t in ax.texts} == {palette.text}


def test_text_has_enough_contrast_in_both_themes():
    def luminance(hex_color: str) -> float:
        channels = []
        for c in to_rgba(hex_color)[:3]:
            channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    for palette in (LIGHT, DARK):
        hi, lo = sorted((luminance(palette.text), luminance(palette.background)), reverse=True)
        assert (hi + 0.05) / (lo + 0.05) >= 7.0, palette


# ---- seçim ---------------------------------------------------------------------------


def test_selection_highlights_incident_edges_and_dims_the_rest():
    _, ax = new_axes()
    draw_call_graph(ax, VIEW, dark=False, selected="fact")
    for patch, (caller, callee) in zip(arrows(ax), VIEW.edges, strict=True):
        incident = "fact" in (caller, callee)
        assert is_highlight(patch, LIGHT) == incident, (caller, callee)
        assert (patch.get_alpha() == 1.0) == incident
    alphas = {c.get_alpha() for c in ax.collections}
    assert 1.0 in alphas and any(a is not None and a < 1.0 for a in alphas)  # sönük düğüm var


def test_selected_node_gets_a_ring_and_neighbours_stay_bright():
    _, plain = new_axes()
    draw_call_graph(plain, VIEW, dark=False)
    _, picked = new_axes()
    draw_call_graph(picked, VIEW, dark=False, selected="fact")
    assert len(picked.collections) > len(plain.collections)
    dimmed = [c for c in picked.collections if c.get_alpha() not in (None, 1.0)]
    assert dimmed  # fact ile ilgisiz düğümler sönük


def test_unknown_selection_is_ignored():
    _, ax = new_axes()
    draw_call_graph(ax, VIEW, dark=False, selected="yok")
    assert not any(is_highlight(p, LIGHT) for p in arrows(ax))


def test_keep_limits_preserves_zoom():
    _, ax = new_axes()
    draw_call_graph(ax, VIEW, dark=False)
    ax.set_xlim(-1.0, 1.0)
    ax.set_ylim(-1.5, 0.5)
    draw_call_graph(ax, VIEW, dark=False, selected="main", keep_limits=True)
    assert ax.get_xlim() == (-1.0, 1.0) and ax.get_ylim() == (-1.5, 0.5)
    draw_call_graph(ax, VIEW, dark=False)
    assert ax.get_xlim() != (-1.0, 1.0)


def test_nearest_node_uses_pixel_distance():
    figure, ax = new_axes()
    draw_call_graph(ax, VIEW, dark=False)
    figure.canvas.draw()
    main = VIEW.node("main")
    px, py = ax.transData.transform((main.x, main.y))
    assert nearest_node(ax, VIEW, px, py) == "main"
    assert nearest_node(ax, VIEW, px + 10, py) == "main"
    assert nearest_node(ax, VIEW, px + 200, py + 200) is None
    assert nearest_node(ax, VIEW, px + 10, py, radius=5) is None


# ---- GraphCanvas bileşeni ------------------------------------------------------------


def click(widget: GraphCanvas, name: str, button: int = 1) -> None:
    node = widget.view.node(name)
    x, y = widget.axes.transData.transform((node.x, node.y))
    event = MouseEvent("button_press_event", widget.canvas, x, y, button=button)
    widget.canvas.callbacks.process("button_press_event", event)


@pytest.fixture
def canvas(qtbot):
    widget = GraphCanvas()
    qtbot.addWidget(widget)
    widget.resize(700, 500)
    widget.show()
    return widget


def test_canvas_starts_with_the_placeholder(canvas):
    assert canvas.view is None and canvas.selected is None
    assert [t.get_text() for t in canvas.axes.texts] == [PLACEHOLDER]


def test_set_view_draws_the_graph_and_resets_selection_optionally(canvas):
    canvas.set_view(VIEW, selected="main")
    assert canvas.view is VIEW and canvas.selected == "main"
    canvas.set_view(VIEW)
    assert canvas.selected is None
    assert len(arrows(canvas.axes)) == len(VIEW.edges)


def test_select_redraws_and_keeps_zoom(canvas):
    canvas.set_view(VIEW)
    canvas.axes.set_xlim(-1.0, 1.0)
    canvas.select("main")
    assert canvas.selected == "main"
    assert canvas.axes.get_xlim() == (-1.0, 1.0)
    canvas.select(None)
    assert canvas.selected is None


def test_left_click_on_a_node_emits_its_name(qtbot, canvas):
    canvas.set_view(VIEW)
    canvas.canvas.draw()
    with qtbot.waitSignal(canvas.node_clicked, timeout=2000) as blocker:
        click(canvas, "fact")
    assert blocker.args == ["fact"]


def test_clicks_that_should_not_select_are_ignored(qtbot, canvas):
    canvas.set_view(VIEW)
    canvas.canvas.draw()
    with qtbot.assertNotEmitted(canvas.node_clicked):
        click(canvas, "main", button=3)  # sağ tık
        canvas.toolbar.zoom()  # yakınlaştırma aracı açıkken tıklama düğüm seçmez
        click(canvas, "main")
        canvas.toolbar.zoom()  # aracı kapat
    canvas.set_view(None)
    with qtbot.assertNotEmitted(canvas.node_clicked):
        canvas.canvas.callbacks.process(
            "button_press_event", MouseEvent("button_press_event", canvas.canvas, 50, 50, button=1)
        )


def test_click_on_empty_space_emits_nothing(qtbot, canvas):
    canvas.set_view(VIEW)
    canvas.canvas.draw()
    event = MouseEvent("button_press_event", canvas.canvas, 2, 2, button=1)
    with qtbot.assertNotEmitted(canvas.node_clicked):
        canvas.canvas.callbacks.process("button_press_event", event)


def test_toolbar_offers_zoom_pan_and_save(canvas):
    texts = {action.text() for action in canvas.toolbar.actions()}
    assert {"Home", "Pan", "Zoom", "Save"} <= texts


@pytest.mark.parametrize(("theme", "dark"), [("light_blue.xml", False), ("dark_teal.xml", True)])
def test_canvas_follows_the_application_theme(qtbot, qapp, theme, dark):
    apply_stylesheet(qapp, theme=theme)
    try:
        widget = GraphCanvas()
        qtbot.addWidget(widget)
        widget.show()
        widget.set_view(VIEW)
        assert widget.figure.get_facecolor() == to_rgba(palette_for(dark).background)
    finally:
        qapp.setStyleSheet("")
