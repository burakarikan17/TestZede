"""Çağrı Grafiği ve Metrikler sayfaları ile ortak kaynak seçici (US-1, US-2)."""

from __future__ import annotations

import dataclasses
import threading
from pathlib import Path

import pytest
from PySide6.QtWidgets import QFileDialog

from testzede.domain.models import TestCase
from testzede.gui.main_window import MainWindow
from testzede.gui.pages import metrics_page
from testzede.gui.pages.analysis_common import MODE_CODE, MODE_TASK, AnalysisPage, SourcePicker
from testzede.gui.pages.call_graph_page import (
    CallGraphPage,
    detail_text,
    node_rows,
    summary_text,
)
from testzede.gui.pages.graph_canvas import EMPTY_GRAPH
from testzede.gui.pages.metrics_page import MetricsPage
from testzede.gui.state import AppState
from testzede.services.analysis_service import AnalysisService, SampleTask
from testzede.services.errors import ServiceError

SOURCE = "def f(x):\n    return g(x) + len([x])\n\n\ndef g(x):\n    return x\n"
OTHER = "def h(y):\n    return y\n"
REAL = AnalysisService()
TASKS = [
    SampleTask("HumanEval/0", "inc", "def inc(x):\n    return x + 1\n"),
    SampleTask(
        "HumanEval/1",
        "twice",
        "def twice(x):\n    return twice_helper(x)\n\n\ndef twice_helper(x):\n    return 2 * x\n",
    ),
]


class FakeService:
    """Gerçek hesabı yapar ama hata, bekleme ve çağrı kaydı enjekte edilebilir."""

    def __init__(
        self,
        *,
        available: bool = True,
        tasks: list[SampleTask] | None = None,
        tasks_error: Exception | None = None,
        error: Exception | None = None,
        export_error: Exception | None = None,
        gate: threading.Event | None = None,
    ) -> None:
        self.available = available
        self.tasks = TASKS if tasks is None else tasks
        self.tasks_error = tasks_error
        self.error = error
        self.export_error = export_error
        self.gate = gate
        self.started = threading.Event()
        self.calls: list[tuple[str, str]] = []

    def _enter(self, kind: str, source: str) -> None:
        self.calls.append((kind, source))
        self.started.set()
        if self.gate is not None:
            assert self.gate.wait(10), "kapı açılmadı"
        if self.error is not None:
            raise self.error

    def call_graph(self, source):
        self._enter("graph", source)
        return REAL.call_graph(source)

    def metrics(self, source):
        self._enter("metrics", source)
        return REAL.metrics(source)

    def humaneval_available(self):
        return self.available

    def humaneval_tasks(self):
        if self.tasks_error is not None:
            raise self.tasks_error
        return self.tasks

    def export_metrics_csv(self, view, path):
        if self.export_error is not None:
            raise self.export_error
        return REAL.export_metrics_csv(view, path)


_LIVE: list = []


@pytest.fixture(autouse=True)
def _shutdown_pages():
    """Sayfaları teardown'a kadar canlı tutar, sonra iş parçacıklarının bitmesini bekler.

    pytest-qt widget'ları zayıf referansla tutar; iş parçacığı bitmeden silinirse Qt süreci
    sonlandırır. Uygulamada bunu ``MainWindow`` kapanırken yapar.
    """
    yield
    while _LIVE:
        _LIVE.pop().shutdown()


def make(qtbot, cls, service=None, source: str = SOURCE):
    state = AppState(source=source)
    page = cls(state, service=service if service is not None else FakeService())
    qtbot.addWidget(page)
    _LIVE.append(page)
    return page


def make_picker(qtbot, service=None, source: str = SOURCE) -> SourcePicker:
    picker = SourcePicker(AppState(source=source), service or FakeService())
    qtbot.addWidget(picker)
    _LIVE.append(picker)
    return picker


def run_and_wait(qtbot, page: AnalysisPage, timeout: int = 10000) -> bool:
    qtbot.waitUntil(lambda: not page._tasks.busy, timeout=5000)  # önceki işin temizliği
    with qtbot.waitSignal(page.run_completed, timeout=timeout) as blocker:
        page.run_button.click()
    return blocker.args[0]


def choose_task(qtbot, picker: SourcePicker, index: int = 0) -> None:
    with qtbot.waitSignal(picker.tasks_loaded, timeout=5000):
        picker.task_radio.setChecked(True)
    picker.task_box.setCurrentIndex(index)


def table_rows(table) -> list[list[str]]:
    return [
        [table.item(r, c).text() for c in range(table.columnCount())]
        for r in range(table.rowCount())
    ]


# ---- kaynak seçici -------------------------------------------------------------------


def test_picker_defaults_to_the_code_page_source(qtbot):
    picker = make_picker(qtbot)
    assert picker.mode == MODE_CODE
    assert picker.source() == SOURCE
    assert picker.label() == "Kod Yükle"
    assert picker.problem() == ""
    assert "Kod Yükle sayfasındaki kod" in picker.hint.text()


def test_picker_without_code_explains_what_to_do(qtbot):
    picker = make_picker(qtbot, source="")
    assert "Kod Yükle" in picker.problem()
    assert picker.hint.text() == "Kod Yükle sayfasında henüz kod yok."
    assert picker.hint.property("status") == "warn"


def test_humaneval_choice_is_disabled_with_a_hint_when_data_is_missing(qtbot):
    picker = make_picker(qtbot, FakeService(available=False))
    assert not picker.task_radio.isEnabled()
    assert "testzede download --dataset humaneval" in picker.task_radio.toolTip()


def test_picker_loads_humaneval_tasks_in_the_background(qtbot):
    picker = make_picker(qtbot)
    changes: list[int] = []
    picker.changed.connect(lambda: changes.append(1))
    choose_task(qtbot, picker)
    assert picker.mode == MODE_TASK
    assert [picker.task_box.itemText(i) for i in range(picker.task_box.count())] == [
        "HumanEval/0 · inc",
        "HumanEval/1 · twice",
    ]
    assert picker.task_box.isEnabled()
    assert picker.source() == TASKS[0].source and picker.label() == "HumanEval/0"
    assert changes  # kaynak değişti bildirimi geldi

    before = len(changes)
    picker.task_box.setCurrentIndex(1)
    assert picker.source() == TASKS[1].source and picker.label() == "HumanEval/1"
    assert len(changes) == before + 1


def test_switching_back_to_the_code_page_source(qtbot):
    picker = make_picker(qtbot)
    choose_task(qtbot, picker)
    picker.code_radio.setChecked(True)
    assert picker.mode == MODE_CODE and not picker.task_box.isEnabled()
    assert picker.source() == SOURCE


def test_tasks_are_loaded_only_once(qtbot):
    service = FakeService()
    picker = make_picker(qtbot, service)
    choose_task(qtbot, picker)
    service.tasks = []  # ikinci yükleme olsaydı liste boşalırdı
    picker.code_radio.setChecked(True)
    picker.task_radio.setChecked(True)
    assert picker.task_box.count() == 2


def test_failed_loading_returns_to_the_code_page_and_shows_the_error(qtbot):
    error = ServiceError("HumanEval indirilmemiş")
    picker = make_picker(qtbot, FakeService(tasks_error=error))
    with qtbot.waitSignal(picker.tasks_loaded, timeout=5000) as blocker:
        picker.task_radio.setChecked(True)
    assert blocker.args == [False]
    assert picker.mode == MODE_CODE
    assert picker.hint.text() == "HumanEval indirilmemiş"
    assert picker.hint.property("status") == "error"


def test_empty_task_list_asks_for_a_choice(qtbot):
    picker = make_picker(qtbot, FakeService(tasks=[]))
    choose_task(qtbot, picker)
    assert picker.source() == ""
    assert picker.problem() == "Bir HumanEval görevi seçin."


def test_on_enter_enables_humaneval_once_the_data_appears(qtbot):
    service = FakeService(available=False)
    picker = make_picker(qtbot, service)
    assert not picker.task_radio.isEnabled()
    service.available = True
    picker.on_enter()
    assert picker.task_radio.isEnabled() and picker.task_radio.toolTip() == ""


def test_on_enter_follows_the_code_page(qtbot):
    picker = make_picker(qtbot, source="")
    picker.state.source = SOURCE
    picker.on_enter()
    assert picker.problem() == ""
    assert "3" not in picker.hint.text() and "satır" in picker.hint.text()


# ---- çağrı grafiği sayfası -----------------------------------------------------------


def test_graph_page_cannot_run_without_code(qtbot):
    page = make(qtbot, CallGraphPage, source="")
    assert not page.run_button.isEnabled()
    assert "Kod Yükle" in page.status_label.text()
    page.run()  # düğme kapalıyken doğrudan çağrı da zararsızdır
    assert not page._tasks.busy
    page.state.source = SOURCE
    page.on_enter()
    assert page.run_button.isEnabled() and page.status_label.text() == ""


def test_graph_page_renders_graph_table_and_summary(qtbot):
    service = FakeService()
    page = make(qtbot, CallGraphPage, service)
    assert run_and_wait(qtbot, page) is True
    assert service.calls == [("graph", SOURCE)]
    assert page.status_label.text() == "Tamamlandı."
    assert page.run_button.isEnabled()
    assert page.canvas.view is not None
    assert "Kaynak: Kod Yükle" in page.summary_label.text()
    assert "2 fonksiyon, 1 yerleşik (builtin)" in page.summary_label.text()
    assert "2 çağrı" in page.summary_label.text()
    assert table_rows(page.node_table) == [
        ["f", "Fonksiyon", "2", "0"],
        ["g", "Fonksiyon", "0", "1"],
        ["len", "Yerleşik", "0", "1"],
    ]
    assert page.note_label.isHidden()


def test_selecting_a_table_row_highlights_the_node_and_explains_it(qtbot):
    page = make(qtbot, CallGraphPage)
    run_and_wait(qtbot, page)
    page.node_table.selectRow(0)
    assert page.canvas.selected == "f"
    assert page.detail_label.text() == "f: çağırdıkları: g, len · çağıranlar: yok"
    page.select_node("g")
    assert page.canvas.selected == "g"
    assert page.node_table.selectedItems()[0].text() == "g"
    assert page.detail_label.text() == "g: çağırdıkları: yok · çağıranlar: f"


def test_clicking_a_node_in_the_graph_selects_its_row(qtbot):
    page = make(qtbot, CallGraphPage)
    run_and_wait(qtbot, page)
    page.canvas.node_clicked.emit("<builtin>.len")
    assert page.canvas.selected == "<builtin>.len"
    assert page.node_table.selectedItems()[0].text() == "len"


def test_selecting_an_unknown_node_changes_nothing(qtbot):
    page = make(qtbot, CallGraphPage)
    run_and_wait(qtbot, page)
    page.select_node("yok")
    assert page.canvas.selected is None


def test_a_new_run_clears_the_selection(qtbot):
    page = make(qtbot, CallGraphPage)
    run_and_wait(qtbot, page)
    page.select_node("g")
    run_and_wait(qtbot, page)
    assert page.canvas.selected is None
    assert page.detail_label.text().startswith("Ayrıntı için")


def test_code_without_functions_shows_an_explanation(qtbot):
    page = make(qtbot, CallGraphPage, source="x = 1\n")
    assert run_and_wait(qtbot, page) is True
    assert "Kodda fonksiyon ya da çağrı yok" in page.summary_label.text()
    assert page.node_table.rowCount() == 0
    assert [t.get_text() for t in page.canvas.axes.texts] == [EMPTY_GRAPH]


def test_service_error_is_shown_and_the_page_stays_usable(qtbot):
    service = FakeService(error=ServiceError("Çağrı grafiği çıkarılamadı: bozuk kod"))
    page = make(qtbot, CallGraphPage, service)
    assert run_and_wait(qtbot, page) is False
    assert page.status_label.text() == "Çağrı grafiği çıkarılamadı: bozuk kod"
    assert page.status_label.property("status") == "error"
    qtbot.waitUntil(lambda: not page._tasks.busy, timeout=5000)
    assert page.run_button.isEnabled()
    service.error = None
    assert run_and_wait(qtbot, page) is True
    assert page.status_label.property("status") == "ok"


def test_unexpected_error_is_reported_without_crashing(qtbot):
    page = make(qtbot, CallGraphPage, FakeService(error=RuntimeError("patladı")))
    assert run_and_wait(qtbot, page) is False
    assert page.status_label.text() == "Beklenmeyen hata: patladı"


def test_stale_note_appears_when_the_source_changes_and_goes_after_rerun(qtbot):
    page = make(qtbot, CallGraphPage)
    run_and_wait(qtbot, page)
    page.state.source = OTHER
    page.on_enter()
    assert not page.note_label.isHidden()
    run_and_wait(qtbot, page)
    assert page.note_label.isHidden()


def test_graph_page_analyses_a_humaneval_task(qtbot):
    service = FakeService()
    page = make(qtbot, CallGraphPage, service)
    choose_task(qtbot, page.picker, 1)
    assert run_and_wait(qtbot, page) is True
    assert service.calls[-1] == ("graph", TASKS[1].source)
    assert "Kaynak: HumanEval/1" in page.summary_label.text()
    assert page.state.source == SOURCE  # Kod Yükle sayfasının kodu değişmez


def test_changing_the_task_marks_the_result_stale(qtbot):
    page = make(qtbot, CallGraphPage)
    choose_task(qtbot, page.picker, 0)
    run_and_wait(qtbot, page)
    page.picker.task_box.setCurrentIndex(1)
    assert not page.note_label.isHidden()


def test_row_helpers():
    view = REAL.call_graph(SOURCE)
    assert [n.name for n in node_rows(view)] == ["f", "g", "<builtin>.len"]
    assert summary_text(view, "X").startswith("Kaynak: X · 2 fonksiyon")
    assert detail_text(view, "f") == "f: çağırdıkları: g, len · çağıranlar: yok"
    recursive = REAL.call_graph("def f(n):\n    return f(n - 1)\n")
    assert "özyinelemeli: f" in summary_text(recursive, "X")
    assert detail_text(recursive, "f").endswith("kendini çağırıyor (özyineleme)")
    assert summary_text(REAL.call_graph("x = 1\n"), "X") == (
        "Kaynak: X · Kodda fonksiyon ya da çağrı yok."
    )


# ---- metrikler sayfası ---------------------------------------------------------------


def test_metrics_page_cannot_run_without_code(qtbot):
    page = make(qtbot, MetricsPage, source="")
    assert not page.run_button.isEnabled() and not page.export_button.isEnabled()
    assert "Kod Yükle" in page.status_label.text()


def test_metrics_page_shows_all_14_metrics_with_descriptions(qtbot):
    service = FakeService()
    page = make(qtbot, MetricsPage, service)
    assert run_and_wait(qtbot, page) is True
    assert service.calls == [("metrics", SOURCE)]
    rows = table_rows(page.table)
    assert len(rows) == 14
    assert [r[0] for r in rows][:3] == ["LOC", "LLOC", "SLOC"]
    loc = rows[0]
    assert loc[1] == "6" and "Toplam satır" in loc[2]
    assert rows[-1][0] == "Sürdürülebilirlik İndeksi" and rows[-1][1].endswith("(A)")
    assert page.summary_label.text().endswith("Sürdürülebilirlik: A (yüksek)")
    assert page.summary_label.property("status") == "ok"
    assert page.export_button.isEnabled()
    assert page.status_label.text() == "Tamamlandı."


@pytest.mark.parametrize(
    ("rank", "color", "kind"),
    [("A", "ok", "ok"), ("B", "warning", "warn"), ("C", "error", "error")],
)
def test_maintainability_rank_is_colored(qtbot, rank, color, kind):
    class Ranked(FakeService):
        def metrics(self, source):
            return dataclasses.replace(super().metrics(source), maintainability_rank=rank)

    page = make(qtbot, MetricsPage, Ranked())
    run_and_wait(qtbot, page)
    mi_cell = page.table.item(13, 1)
    assert mi_cell.foreground().color() == page.colors[color].fg
    assert page.summary_label.property("status") == kind


def test_metrics_error_is_shown(qtbot):
    page = make(qtbot, MetricsPage, FakeService(error=ServiceError("Metrikler hesaplanamadı: x")))
    assert run_and_wait(qtbot, page) is False
    assert page.status_label.text() == "Metrikler hesaplanamadı: x"
    assert not page.export_button.isEnabled()


def test_metrics_stale_note(qtbot):
    page = make(qtbot, MetricsPage)
    run_and_wait(qtbot, page)
    page.state.source = OTHER
    page.on_enter()
    assert not page.note_label.isHidden()


def test_export_csv_writes_the_shown_metrics(qtbot, tmp_path: Path):
    page = make(qtbot, MetricsPage)
    assert page.export_csv(tmp_path / "x.csv") is False  # henüz sonuç yok
    run_and_wait(qtbot, page)
    target = tmp_path / "m.csv"
    assert page.export_csv(target) is True
    text = target.read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == "Metrik,Değer,Açıklama"
    assert len(text.splitlines()) == 15
    assert page.status_label.text() == f"CSV kaydedildi: {target}"
    assert page.status_label.property("status") == "ok"


def test_export_failure_is_shown_on_the_page(qtbot, tmp_path: Path):
    service = FakeService(export_error=ServiceError("CSV dosyası yazılamadı: dolu disk"))
    page = make(qtbot, MetricsPage, service)
    run_and_wait(qtbot, page)
    assert page.export_csv(tmp_path / "m.csv") is False
    assert page.status_label.text() == "CSV dosyası yazılamadı: dolu disk"
    assert page.status_label.property("status") == "error"


def test_export_dialog_writes_to_the_chosen_file_and_ignores_cancel(qtbot, monkeypatch, tmp_path):
    page = make(qtbot, MetricsPage)
    run_and_wait(qtbot, page)
    asked = []

    def choose(parent, title, default, filters):
        asked.append((default, filters))
        return str(tmp_path / "secilen.csv"), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose)
    page.export_button.click()
    assert asked == [(metrics_page.DEFAULT_CSV_NAME, "CSV (*.csv)")]
    assert (tmp_path / "secilen.csv").is_file()

    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("", ""))
    page.status_label.setText("önceki")
    page.export_button.click()
    assert page.status_label.text() == "önceki"  # iptal: hiçbir şey olmaz


# ---- ortak davranış ------------------------------------------------------------------


@pytest.mark.parametrize("cls", [CallGraphPage, MetricsPage])
def test_analysis_pages_never_modify_the_shared_state(qtbot, cls):
    tests = [TestCase("t", "def test_t(): pass", "user")]
    state = AppState(source=SOURCE, tests=tests, module_name="mod")
    page = cls(state, service=FakeService())
    qtbot.addWidget(page)
    _LIVE.append(page)
    choose_task(qtbot, page.picker, 0)
    run_and_wait(qtbot, page)
    assert (state.source, state.tests, state.module_name) == (SOURCE, tests, "mod")
    assert state.execution_result is None and state.mutation_run is None


def test_a_rendering_failure_is_reported_and_does_not_lock_the_page(qtbot, monkeypatch):
    page = make(qtbot, CallGraphPage)

    def broken(result, label):
        raise RuntimeError("çizim bozuldu")

    monkeypatch.setattr(page, "_render", broken)
    assert run_and_wait(qtbot, page) is False
    assert page.status_label.text() == "Sonuç gösterilemedi: çizim bozuldu"
    assert page.status_label.property("status") == "error"
    qtbot.waitUntil(lambda: not page._tasks.busy, timeout=5000)
    assert page.run_button.isEnabled()
    assert page.note_label.isHidden()  # eksik sonuç "gösterilen sonuç" sayılmaz


def test_base_hooks_must_be_overridden():
    base = AnalysisPage("t", "r", AppState(), FakeService())
    with pytest.raises(NotImplementedError):
        base._compute("x")
    with pytest.raises(NotImplementedError):
        base._render(None, "x")
    base.shutdown()


# ---- ana pencere ---------------------------------------------------------------------


def test_main_window_registers_the_pages_in_architecture_order(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    titles = [window.nav.item(i).text() for i in range(window.nav.count())]
    assert titles[:4] == ["Kod Yükle", "Çağrı Grafiği", "Metrikler", "Coverage"]
    assert isinstance(window.page("Çağrı Grafiği"), CallGraphPage)
    assert isinstance(window.page("Metrikler"), MetricsPage)
    assert window.page("Metrikler").state is window.state
    window.close()


def test_entering_the_page_picks_up_code_loaded_elsewhere(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    page = window.page("Çağrı Grafiği")
    assert not page.run_button.isEnabled()
    window.state.source = SOURCE
    window.nav.setCurrentRow(window.pages.index(page))
    assert page.run_button.isEnabled()
    window.close()


def test_closing_the_window_waits_for_a_running_analysis(qtbot):
    gate = threading.Event()
    service = FakeService(gate=gate)
    state = AppState(source=SOURCE)
    window = MainWindow(state, pages=(lambda s: CallGraphPage(s, service=service),))
    qtbot.addWidget(window)
    page = window.page("Çağrı Grafiği")
    page.run_button.click()
    qtbot.waitUntil(service.started.is_set, timeout=5000)
    thread = page._tasks._thread
    threading.Timer(0.3, gate.set).start()
    window.close()
    assert thread.isFinished()


def test_end_to_end_with_the_real_service(qtbot):
    graph = make(qtbot, CallGraphPage, REAL)
    assert run_and_wait(qtbot, graph, timeout=30000) is True
    assert graph.node_table.rowCount() == 3
    metrics = make(qtbot, MetricsPage, REAL)
    assert run_and_wait(qtbot, metrics, timeout=30000) is True
    assert metrics.table.rowCount() == 14
    assert metrics.table.item(0, 1).text() == "6"


@pytest.mark.skipif(not REAL.humaneval_available(), reason="HumanEval indirilmemiş")
def test_end_to_end_with_real_humaneval_data(qtbot):
    page = make(qtbot, MetricsPage, REAL)
    with qtbot.waitSignal(page.picker.tasks_loaded, timeout=30000):
        page.picker.task_radio.setChecked(True)
    assert page.picker.task_box.count() == 164
    page.picker.task_box.setCurrentIndex(12)
    assert run_and_wait(qtbot, page, timeout=30000) is True
    assert page.summary_label.text().startswith("Kaynak: HumanEval/12")
    assert float(page.table.item(0, 1).text()) > 0
