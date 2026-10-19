from __future__ import annotations

import threading

import pytest
from PySide6.QtCore import Qt
from result_builders import make_result

from testzede.domain.models import RunStats, TestCase
from testzede.gui.main_window import MainWindow
from testzede.gui.pages.coverage_page import CoveragePage
from testzede.gui.state import AppState
from testzede.services.coverage_service import CoverageService
from testzede.services.errors import ServiceError

SOURCE = "def f(a):\n    if a > 0:\n        return 1\n    return 2\n"
TESTS = [
    TestCase("test_ok", "def test_ok():\n    assert f(1) == 1", "user"),
    TestCase("test_bad", "def test_bad():\n    assert f(1) == 2", "user"),
    TestCase("test_slow", "def test_slow():\n    pass", "user"),
    TestCase("test_gone", "def test_gone():\n    pass", "user"),
]
RESULT = make_result(
    all_lines={1, 2, 3, 4},
    covered_lines={1, 2, 3},
    all_branches={(2, 3), (2, 4)},
    covered_branches={(2, 3)},
    per_function={"f": 0.75, "Cls.method": 0.5},
    outcomes={"test_ok": "passed", "test_bad": "failed", "test_slow": "timeout"},
    stats=RunStats(generated=4, compiled=3, execution_time_s=1.5),
)


class FakeService:
    """Çağrıları kaydeden sahte servis; istenirse bekler ya da hata verir."""

    def __init__(self, result=RESULT, error: Exception | None = None, gate=None) -> None:
        self.result = result
        self.error = error
        self.gate = gate  # threading.Event: set edilene kadar bekler
        self.calls: list[tuple[str, list[TestCase]]] = []
        self.thread_ident: int | None = None

    def run(self, source: str, tests: list[TestCase]):
        self.calls.append((source, tests))
        self.thread_ident = threading.get_ident()
        if self.gate is not None:
            self.gate.wait(10)
        if self.error is not None:
            raise self.error
        return self.result


_LIVE_PAGES: list[CoveragePage] = []


@pytest.fixture(autouse=True)
def _shutdown_pages():
    """Sayfaları teardown'a kadar canlı tutar, sonra iş parçacıklarının bitmesini bekler.

    pytest-qt widget'ları zayıf referansla tutar: test dönünce sayfa silinir ve iş parçacığı
    henüz tam bitmemişse Qt süreci sonlandırır. Uygulamada bunu ``MainWindow`` kapanırken yapar.
    """
    yield
    while _LIVE_PAGES:
        _LIVE_PAGES.pop().shutdown()


def _page(qtbot, service=None, source: str = SOURCE, tests=None) -> CoveragePage:
    state = AppState(source=source, tests=list(TESTS if tests is None else tests))
    page = CoveragePage(state, service=service)
    qtbot.addWidget(page)
    _LIVE_PAGES.append(page)
    return page


def _run_and_wait(qtbot, page: CoveragePage, timeout: int = 10000) -> bool:
    # Önceki iş parçacığının temizliği (TaskRunner._cleanup) sonuç sinyalinden sonra gelir.
    qtbot.waitUntil(lambda: not page._tasks.busy, timeout=5000)
    with qtbot.waitSignal(page.run_completed, timeout=timeout) as blocker:
        page.run_button.click()
    return blocker.args[0]


def _table(table) -> list[list[str]]:
    return [
        [table.item(r, c).text() for c in range(table.columnCount())]
        for r in range(table.rowCount())
    ]


def _line_colors(page: CoveragePage) -> dict[int, tuple[int, int, int, int]]:
    out = {}
    for sel in page.source_view.extraSelections():
        color = sel.format.background().color()
        out[sel.cursor.blockNumber() + 1] = color.getRgb()
    return out


# --- girdi kontrolü ----------------------------------------------------------------------------


def test_missing_source_disables_run_and_explains(qtbot):
    page = _page(qtbot, source="")
    assert not page.run_button.isEnabled()
    assert "Kaynak kod yok" in page.status_label.text()
    assert page.status_label.property("status") == "warn"


def test_missing_tests_disables_run_and_explains(qtbot):
    page = _page(qtbot, tests=[])
    assert not page.run_button.isEnabled()
    assert "Test yok" in page.status_label.text()


def test_blank_source_counts_as_missing(qtbot):
    assert not _page(qtbot, source="  \n").run_button.isEnabled()


def test_inputs_present_enables_run_without_message(qtbot):
    page = _page(qtbot)
    assert page.run_button.isEnabled()
    assert page.status_label.text() == ""


def test_on_enter_reenables_run_after_inputs_arrive_and_clears_message(qtbot):
    page = _page(qtbot, source="", tests=[])
    page.state.source, page.state.tests = SOURCE, list(TESTS)
    page.on_enter()
    assert page.run_button.isEnabled()
    assert page.status_label.text() == ""


def test_run_with_missing_input_does_not_call_service(qtbot):
    service = FakeService()
    page = _page(qtbot, service, source="")
    page.run()
    assert service.calls == []
    assert "Kaynak kod yok" in page.status_label.text()


# --- başarılı çalıştırma -----------------------------------------------------------------------


def test_successful_run_fills_state_summary_tables_and_source(qtbot):
    service = FakeService()
    page = _page(qtbot, service)
    assert _run_and_wait(qtbot, page) is True

    assert service.calls == [(SOURCE, list(TESTS))]
    assert page.state.execution_result is RESULT
    assert page.status_label.text() == "Tamamlandı."
    assert page.run_button.isEnabled()

    assert page.lines_label.text() == "Satır: 75.0% (3/4)"
    assert page.branches_label.text() == "Dal: 50.0% (1/2)"
    assert page.compilation_label.text() == "Derleme: 75.0% (3/4)"
    assert page.time_label.text() == "Süre: 1.50 sn"

    assert _table(page.function_table) == [["Cls.method", "50.0%"], ["f", "75.0%"]]
    assert _table(page.test_table) == [
        ["test_ok", "Geçti"],
        ["test_bad", "Başarısız"],
        ["test_slow", "Zaman aşımı"],
        ["test_gone", "Hata"],  # sonucu olmayan test
    ]
    colors = [page.test_table.item(r, 1).foreground().color().name() for r in range(4)]
    assert colors == [
        page.colors["passed"].fg.name(),
        page.colors["failed"].fg.name(),
        page.colors["timeout"].fg.name(),
        page.colors["error"].fg.name(),
    ]
    raw = [page.test_table.item(r, 1).data(Qt.ItemDataRole.UserRole) for r in range(4)]
    assert raw == ["passed", "failed", "timeout", "error"]

    text = page.source_view.toPlainText()
    assert text.splitlines()[0] == "1 │ def f(a):"
    assert text.splitlines()[3] == "4 │     return 2"
    assert page.source_view.isReadOnly()
    assert page.source_view.font().fixedPitch()


def test_source_lines_are_colored_by_status(qtbot):
    page = _page(qtbot, FakeService())
    _run_and_wait(qtbot, page)
    rgb = {k: page.colors[k].bg.getRgb() for k in ("covered", "partial", "missed")}
    colors = _line_colors(page)
    assert colors[2] == rgb["partial"]
    assert colors[4] == rgb["missed"]
    assert colors[1] == colors[3] == rgb["covered"]


def test_service_runs_off_the_gui_thread_and_results_arrive_on_it(qtbot):
    service = FakeService()
    page = _page(qtbot, service)
    gui_ident = threading.get_ident()
    seen: list[int] = []
    page.run_completed.connect(lambda ok: seen.append(threading.get_ident()))
    _run_and_wait(qtbot, page)
    assert service.thread_ident != gui_ident
    assert seen == [gui_ident]  # sinyal, @Slot'u çalıştıran GUI iş parçacığından yayıldı


def test_ui_is_disabled_and_shows_running_while_service_works(qtbot):
    gate = threading.Event()
    service = FakeService(gate=gate)
    page = _page(qtbot, service)
    with qtbot.waitSignal(page.run_completed, timeout=10000):
        page.run_button.click()
        assert not page.run_button.isEnabled()
        assert page.status_label.text() == "Çalışıyor..."
        qtbot.wait(50)  # GUI iş parçacığı olayları işlemeye devam eder
        page.run()  # çalışırken ikinci çalıştırma yok sayılır
        gate.set()
    assert len(service.calls) == 1
    assert page.run_button.isEnabled()


def test_run_twice_updates_result(qtbot):
    second = make_result(
        all_lines={1}, covered_lines={1}, per_function={"g": 1.0}, outcomes={"test_ok": "passed"}
    )
    service = FakeService()
    page = _page(qtbot, service)
    _run_and_wait(qtbot, page)
    service.result = second
    _run_and_wait(qtbot, page)
    assert page.state.execution_result is second
    assert _table(page.function_table) == [["g", "100.0%"]]
    assert page.lines_label.text() == "Satır: 100.0% (1/1)"


# --- hatalar -----------------------------------------------------------------------------------


def test_service_error_is_shown_in_red_without_crashing(qtbot):
    page = _page(qtbot, FakeService(error=ServiceError("Kaynak kod geçerli değil: x")))
    assert _run_and_wait(qtbot, page) is False
    assert page.status_label.text() == "Kaynak kod geçerli değil: x"
    assert page.status_label.property("status") == "error"
    assert page.colors["error"].fg.name() in page.status_label.styleSheet()
    assert page.state.execution_result is None
    assert page.run_button.isEnabled()
    assert page.function_table.rowCount() == 0


def test_unexpected_error_is_shown_without_crashing(qtbot):
    page = _page(qtbot, FakeService(error=RuntimeError("beklenmedik")))
    assert _run_and_wait(qtbot, page) is False
    assert "beklenmedik" in page.status_label.text()
    assert page.status_label.property("status") == "error"
    assert page.run_button.isEnabled()


def test_failed_run_keeps_previous_result_on_screen(qtbot):
    service = FakeService()
    page = _page(qtbot, service)
    _run_and_wait(qtbot, page)
    service.error = ServiceError("sonraki çalıştırma hatası")
    assert _run_and_wait(qtbot, page) is False
    assert page.state.execution_result is RESULT
    assert page.function_table.rowCount() == 2


# --- on_enter ----------------------------------------------------------------------------------


def test_on_enter_redraws_existing_result(qtbot):
    page = _page(qtbot, FakeService())
    _run_and_wait(qtbot, page)
    page.function_table.setRowCount(0)
    page.test_table.setRowCount(0)
    page.source_view.setPlainText("")
    page.on_enter()
    assert page.function_table.rowCount() == 2
    assert page.test_table.rowCount() == 4
    assert page.source_view.toPlainText().startswith("1 │ def f(a):")
    assert page.note_label.isHidden()


def test_on_enter_marks_result_as_stale_when_source_changed(qtbot):
    page = _page(qtbot, FakeService())
    _run_and_wait(qtbot, page)
    assert page.note_label.isHidden()
    page.state.source = SOURCE + "# değişti\n"
    page.on_enter()
    assert not page.note_label.isHidden()
    assert "eski" in page.note_label.text()
    # Eski sonuç, hesaplandığı kaynakla çizilmeye devam eder (satır numaraları kaymaz).
    assert page.source_view.toPlainText().count("değişti") == 0


def test_on_enter_marks_result_as_stale_when_tests_changed(qtbot):
    page = _page(qtbot, FakeService())
    _run_and_wait(qtbot, page)
    page.state.tests = TESTS[:1]
    page.on_enter()
    assert not page.note_label.isHidden()


def test_rerun_clears_stale_note(qtbot):
    page = _page(qtbot, FakeService())
    _run_and_wait(qtbot, page)
    page.state.source = SOURCE + "\n"
    page.on_enter()
    _run_and_wait(qtbot, page)
    assert page.note_label.isHidden()


def test_on_enter_after_state_reset_clears_view(qtbot):
    page = _page(qtbot, FakeService())
    _run_and_wait(qtbot, page)
    page.state.reset()
    page.on_enter()
    assert page.function_table.rowCount() == 0 and page.test_table.rowCount() == 0
    assert page.source_view.toPlainText() == ""
    assert page.lines_label.text() == "Satır: —"
    assert not page.run_button.isEnabled()


def test_on_enter_renders_result_set_by_another_component(qtbot):
    page = _page(qtbot)
    page.state.execution_result = RESULT
    page.on_enter()
    assert page.function_table.rowCount() == 2
    assert page.note_label.isHidden()  # güncel kabul edilir


def test_shutdown_is_a_noop_when_idle(qtbot):
    page = _page(qtbot)
    page.shutdown()


def test_shutdown_waits_for_running_job(qtbot):
    gate = threading.Event()
    page = _page(qtbot, FakeService(gate=gate))
    page.run_button.click()
    thread = page._tasks._thread
    threading.Timer(0.2, gate.set).start()
    page.shutdown()  # pencere kapanırken: iş bitene kadar bekler
    assert thread.isFinished()


# --- ana pencere ve gerçek uçtan uca -----------------------------------------------------------


def test_main_window_registers_coverage_page(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert isinstance(window.page("Coverage"), CoveragePage)
    window.nav.setCurrentRow(window.pages.index(window.page("Coverage")))
    assert window.stack.currentWidget() is window.page("Coverage")


def test_end_to_end_with_real_coverage_service(qtbot):
    tests = [TestCase("test_one", "def test_one():\n    assert f(1) == 1", "user")]
    page = _page(qtbot, CoverageService(), tests=tests)
    assert _run_and_wait(qtbot, page, timeout=60000) is True

    assert page.status_label.text() == "Tamamlandı."
    assert _table(page.test_table) == [["test_one", "Geçti"]]
    rows = _table(page.function_table)
    assert [r[0] for r in rows] == ["f"]
    assert rows[0][1].endswith("%") and 0 < float(rows[0][1].rstrip("%")) < 100
    assert page.lines_label.text() == "Satır: 75.0% (3/4)"
    assert page.branches_label.text() == "Dal: 50.0% (1/2)"
    assert page.compilation_label.text() == "Derleme: 100.0% (1/1)"
    assert page.state.execution_result is not None
    rgb = {k: page.colors[k].bg.getRgb() for k in ("covered", "partial", "missed")}
    assert _line_colors(page) == {
        1: rgb["covered"],
        2: rgb["partial"],  # if: (2,4) dalı hiç çalışmadı
        3: rgb["covered"],
        4: rgb["missed"],
    }
    assert page.source_view.toPlainText().splitlines()[1] == "2 │     if a > 0:"
