from __future__ import annotations

import threading
from collections.abc import Callable

import pytest
from PySide6.QtWidgets import QAbstractItemView

from testzede.domain.models import MutationReport, RunStats, TestCase
from testzede.gui.main_window import MainWindow
from testzede.gui.pages import mutation_logic as logic
from testzede.gui.pages.mutation_page import (
    DEFAULT_MAX_MUTANTS,
    MutationPage,
)
from testzede.gui.state import AppState
from testzede.mutation.engine import MutationError, MutationRun
from testzede.mutation.operators import generate_all
from testzede.services.errors import ServiceError
from testzede.services.mutation_service import MutationService

SOURCE = "def f(a):\n    return a + 1\n"
TESTS = [TestCase("test_a", "def test_a():\n    assert f(1) == 2", "user")]
MUTANTS = generate_all(SOURCE)  # AOR, CONST, RETURN_NONE (hepsi satır 2)
RUN = MutationRun(
    report=MutationReport(total=3, killed=1, survived=2, timeout=0),
    stats=RunStats(generated=1, compiled=1, execution_time_s=0.5),
    survivors=[MUTANTS[1], MUTANTS[0]],  # kaynak sırasında değil: tablo sıralamalı
    skipped_uncovered=1,
)
PARTIAL = MutationRun(
    report=MutationReport(total=1, killed=1, survived=0, timeout=0),
    stats=RUN.stats,
    survivors=[],
)


class FakeEngine:
    """Çağrıları kaydeden sahte motor; davranışı ``mode`` ile seçilir."""

    def __init__(self, mode: str = "ok", result: MutationRun = RUN) -> None:
        self.mode = mode
        self.result = result
        self.calls: list[tuple[str, list[TestCase]]] = []
        self.thread_ident: int | None = None
        self.started = threading.Event()
        self.gate = threading.Event()

    def run_detailed(
        self,
        source: str,
        tests: list[TestCase],
        progress_callback: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> MutationRun:
        self.calls.append((source, tests))
        self.thread_ident = threading.get_ident()
        self.started.set()
        assert progress_callback is not None and should_cancel is not None
        if self.mode == "service_error":
            raise ServiceError("Kaynak kod geçerli değil")
        if self.mode == "mutation_error":
            raise MutationError("Testler orijinal kodda geçmiyor")
        if self.mode == "crash":
            raise RuntimeError("beklenmedik")
        if self.mode == "block":  # serbest bırakılana kadar ilk ilerlemeyi bekletir
            self.gate.wait(10)
        if self.mode == "ok":
            for done in (1, 2, 3):
                progress_callback(done, 3)
            return self.result
        if self.mode == "cancel_after_progress":
            progress_callback(1, 5)
            self.gate.set()
            while not should_cancel():
                self.gate.wait(0.01)
            return PARTIAL
        if self.mode == "cancel_before_progress":
            while not should_cancel():
                self.gate.wait(0.01)
            return MutationRun(report=MutationReport(0, 0, 0, 0), stats=RUN.stats, survivors=[])
        if self.mode == "cancel_after_all":
            progress_callback(3, 3)
            while not should_cancel():
                self.gate.wait(0.01)
            return self.result
        return self.result


_LIVE_PAGES: list[MutationPage] = []


@pytest.fixture(autouse=True)
def _shutdown_pages():
    """Sayfaları teardown'a kadar canlı tutar, sonra iş parçacıklarının bitmesini bekler.

    pytest-qt widget'ları zayıf referansla tutar: test dönünce sayfa silinir ve iş parçacığı
    henüz tam bitmemişse Qt süreci sonlandırır. Uygulamada bunu ``MainWindow`` kapanırken yapar.
    """
    yield
    while _LIVE_PAGES:
        _LIVE_PAGES.pop().shutdown()


def _add_page(qtbot, page: MutationPage) -> None:
    qtbot.addWidget(page)
    _LIVE_PAGES.append(page)


def _page(
    qtbot,
    engine: FakeEngine | None = None,
    source: str = SOURCE,
    tests=None,
) -> tuple[MutationPage, FakeEngine, list[int]]:
    engine = engine or FakeEngine()
    max_calls: list[int] = []

    def factory(max_mutants: int) -> MutationService:
        max_calls.append(max_mutants)
        return MutationService(engine)

    state = AppState(source=source, tests=list(TESTS if tests is None else tests))
    page = MutationPage(state, service_factory=factory)
    _add_page(qtbot, page)
    return page, engine, max_calls


def _run_and_wait(qtbot, page: MutationPage, timeout: int = 10000) -> bool:
    # Önceki iş parçacığının temizliği (TaskRunner._cleanup) sonuç sinyalinden sonra gelir.
    qtbot.waitUntil(lambda: not page._tasks.busy, timeout=5000)
    with qtbot.waitSignal(page.run_completed, timeout=timeout) as blocker:
        page.run_button.click()
    return blocker.args[0]


def _table(page: MutationPage) -> list[list[str]]:
    t = page.survivors_table
    return [[t.item(r, c).text() for c in range(3)] for r in range(t.rowCount())]


# --- girdi kontrolü ----------------------------------------------------------------------------


def test_defaults(qtbot):
    page, _, _ = _page(qtbot)
    assert page.max_spin.value() == DEFAULT_MAX_MUTANTS == 100
    assert (page.max_spin.minimum(), page.max_spin.maximum()) == (1, 1000)
    assert page.run_button.isEnabled() and not page.cancel_button.isEnabled()
    assert page.score_label.text() == "Skor: —"


def test_missing_source_disables_run_and_explains(qtbot):
    page, engine, calls = _page(qtbot, source="")
    assert not page.run_button.isEnabled()
    assert "Kaynak kod yok" in page.status_label.text()
    page.run()
    assert engine.calls == [] and calls == []


def test_missing_tests_disables_run_and_explains(qtbot):
    page, engine, _ = _page(qtbot, tests=[])
    assert not page.run_button.isEnabled()
    assert "Test yok" in page.status_label.text()
    page.run()
    assert engine.calls == []


def test_on_enter_reenables_run_when_inputs_arrive(qtbot):
    page, _, _ = _page(qtbot, source="", tests=[])
    page.state.source, page.state.tests = SOURCE, list(TESTS)
    page.on_enter()
    assert page.run_button.isEnabled() and page.status_label.text() == ""


# --- başarı ------------------------------------------------------------------------------------


def test_successful_run_fills_state_summary_progress_and_table(qtbot):
    page, engine, _ = _page(qtbot)
    assert _run_and_wait(qtbot, page) is True
    assert engine.calls == [(SOURCE, list(TESTS))]
    assert page.state.mutation_run is RUN
    assert page.status_label.text() == "Tamamlandı."
    assert (page.progress_bar.maximum(), page.progress_bar.value()) == (3, 3)
    assert page.score_label.text() == "Skor: 33.3%"
    assert page.killed_label.text() == "Öldürülen: 1"
    assert page.survived_label.text() == "Hayatta kalan: 2"
    assert page.timeout_label.text() == "Zaman aşımı: 0"
    assert page.skipped_label.text() == "Atlanan (kapsanmamış): 1"
    assert page.compilation_label.text() == "Derleme: 100.0% (1/1)"
    assert page.time_label.text() == "Test süresi: 0.50 sn"
    assert _table(page) == [[m.operator, "2", m.description] for m in logic.sorted_survivors(RUN)]
    assert page.run_button.isEnabled() and not page.cancel_button.isEnabled()
    assert page.max_spin.isEnabled()


def test_max_mutants_spinbox_value_is_passed_to_the_engine_factory(qtbot):
    page, _, calls = _page(qtbot)
    page.max_spin.setValue(7)
    _run_and_wait(qtbot, page)
    assert calls == [7]
    _run_and_wait(qtbot, page)
    page.max_spin.setValue(1000)
    _run_and_wait(qtbot, page)
    assert calls == [7, 7, 1000]


def test_default_factory_is_the_service_layer_factory(qtbot):
    from testzede.services.mutation_service import create_mutation_service

    page = MutationPage(AppState(source=SOURCE, tests=list(TESTS)))
    _add_page(qtbot, page)
    assert page._service_factory is create_mutation_service


def test_spinbox_value_reaches_the_default_service_factory(qtbot, monkeypatch):
    from testzede.gui.pages import mutation_page

    calls: list[int] = []

    def fake_factory(max_mutants: int) -> MutationService:
        calls.append(max_mutants)
        return MutationService(FakeEngine())

    monkeypatch.setattr(mutation_page, "create_mutation_service", fake_factory)
    page = MutationPage(AppState(source=SOURCE, tests=list(TESTS)))  # varsayılan fabrika
    _add_page(qtbot, page)
    page.max_spin.setValue(33)
    _run_and_wait(qtbot, page)
    assert calls == [33]


def test_engine_runs_off_gui_thread_and_completion_arrives_on_it(qtbot):
    page, engine, _ = _page(qtbot)
    gui_ident = threading.get_ident()
    seen: list[int] = []
    page.run_completed.connect(lambda ok: seen.append(threading.get_ident()))
    _run_and_wait(qtbot, page)
    assert engine.thread_ident != gui_ident
    assert seen == [gui_ident]


def test_controls_while_running(qtbot):
    engine = FakeEngine("block")
    page, _, _ = _page(qtbot, engine)
    with qtbot.waitSignal(page.run_completed, timeout=10000):
        page.run_button.click()
        assert not page.run_button.isEnabled()
        assert page.cancel_button.isEnabled()
        assert not page.max_spin.isEnabled()
        assert page.status_label.text() == "Çalışıyor..."
        assert page.progress_bar.maximum() == 0  # belirsiz ilerleme (taban koşusu)
        qtbot.wait(50)  # GUI olayları işlenmeye devam eder
        page.run()  # çalışırken ikinci çalıştırma yok sayılır
        engine.gate.set()
    assert len(engine.calls) == 1


# --- iptal -------------------------------------------------------------------------------------


def test_cancel_shows_cancelled_and_keeps_partial_result(qtbot):
    engine = FakeEngine("cancel_after_progress")
    page, _, _ = _page(qtbot, engine)
    with qtbot.waitSignal(page.run_completed, timeout=10000) as blocker:
        page.run_button.click()
        qtbot.waitUntil(lambda: page.progress_bar.value() == 1, timeout=5000)
        page.cancel_button.click()
        assert not page.cancel_button.isEnabled()
        assert page.status_label.text() == "İptal ediliyor..."
    assert blocker.args == [True]
    assert page.status_label.text() == "İptal edildi. 1/5 mutant işlendi."
    assert page.status_label.property("status") == "warn"
    assert page.state.mutation_run is PARTIAL
    assert page.score_label.text() == "Skor: 100.0%"
    assert (page.progress_bar.maximum(), page.progress_bar.value()) == (5, 1)
    assert page.run_button.isEnabled() and not page.cancel_button.isEnabled()


def test_cancel_before_any_progress(qtbot):
    engine = FakeEngine("cancel_before_progress")
    page, _, _ = _page(qtbot, engine)
    with qtbot.waitSignal(page.run_completed, timeout=10000):
        page.run_button.click()
        qtbot.waitUntil(engine.started.is_set, timeout=5000)
        page.cancel_button.click()
    assert page.status_label.text() == "İptal edildi. 0 mutant işlendi."
    assert page.state.mutation_run is not None and page.state.mutation_run.report.total == 0


def test_cancel_after_everything_finished_reports_completed(qtbot):
    engine = FakeEngine("cancel_after_all")
    page, _, _ = _page(qtbot, engine)
    with qtbot.waitSignal(page.run_completed, timeout=10000):
        page.run_button.click()
        qtbot.waitUntil(lambda: page.progress_bar.value() == 3, timeout=5000)
        page.cancel_button.click()
    assert page.status_label.text() == "Tamamlandı."


def test_cancel_without_running_job_is_a_noop(qtbot):
    page, _, _ = _page(qtbot)
    page.cancel()
    assert page.status_label.text() == ""


def test_shutdown_cancels_running_job_and_waits(qtbot):
    engine = FakeEngine("cancel_before_progress")
    page, _, _ = _page(qtbot, engine)
    page.run_button.click()
    qtbot.waitUntil(engine.started.is_set, timeout=5000)
    thread = page._tasks._thread
    page.shutdown()  # pencere kapanırken: önce iptal, sonra bekle
    assert thread.isFinished()
    qtbot.waitUntil(lambda: not page._tasks.busy, timeout=5000)


def test_shutdown_is_a_noop_when_idle(qtbot):
    page, _, _ = _page(qtbot)
    page.shutdown()


def test_closing_main_window_shuts_down_running_job(qtbot):
    engine = FakeEngine("cancel_before_progress")
    state = AppState(source=SOURCE, tests=list(TESTS))
    window = MainWindow(
        state, pages=(lambda s: MutationPage(s, lambda _: MutationService(engine)),)
    )
    qtbot.addWidget(window)
    page = window.page("Mutasyon")
    page.run_button.click()
    qtbot.waitUntil(engine.started.is_set, timeout=5000)
    thread = page._tasks._thread
    window.close()
    assert thread.isFinished()


# --- hatalar -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("service_error", "Kaynak kod geçerli değil"),
        ("mutation_error", "Testler orijinal kodda geçmiyor"),  # servis ServiceError'a çevirir
        ("crash", "Beklenmeyen hata: beklenmedik"),
    ],
)
def test_errors_are_shown_in_red_without_crashing(qtbot, mode, message):
    page, _, _ = _page(qtbot, FakeEngine(mode))
    assert _run_and_wait(qtbot, page) is False
    assert page.status_label.text() == message
    assert page.status_label.property("status") == "error"
    assert "#ff5252" in page.status_label.styleSheet()
    assert page.state.mutation_run is None
    assert page.run_button.isEnabled() and not page.cancel_button.isEnabled()
    assert page.max_spin.isEnabled()
    assert page.survivors_table.rowCount() == 0


def test_failed_run_keeps_previous_result(qtbot):
    engine = FakeEngine()
    page, _, _ = _page(qtbot, engine)
    _run_and_wait(qtbot, page)
    engine.mode = "service_error"
    assert _run_and_wait(qtbot, page) is False
    assert page.state.mutation_run is RUN
    assert page.survivors_table.rowCount() == 2


# --- fark gösterimi ----------------------------------------------------------------------------


def test_selecting_a_survivor_shows_its_diff(qtbot):
    page, _, _ = _page(qtbot)
    _run_and_wait(qtbot, page)
    first = logic.sorted_survivors(RUN)[0]
    page.survivors_table.selectRow(0)
    expected = logic.mutant_diff(SOURCE, first.source)
    assert page.diff_view.toPlainText() == expected
    assert "-    return a + 1" in expected and "+" in expected


def test_diff_lines_are_colored_green_and_red(qtbot):
    page, _, _ = _page(qtbot)
    _run_and_wait(qtbot, page)
    page.survivors_table.selectRow(0)
    colors = {}
    for sel in page.diff_view.extraSelections():
        text = sel.cursor.block().text()
        colors[text[:1]] = sel.format.background().color().getRgb()
    assert set(colors) == {"-", "+"}
    assert colors["+"][1] > colors["+"][0]  # yeşil baskın
    assert colors["-"][0] > colors["-"][1]  # kırmızı baskın


def test_selecting_another_row_replaces_the_diff(qtbot):
    page, _, _ = _page(qtbot)
    _run_and_wait(qtbot, page)
    page.survivors_table.selectRow(0)
    first = page.diff_view.toPlainText()
    page.survivors_table.selectRow(1)
    assert page.diff_view.toPlainText() != first


def test_clearing_selection_clears_diff(qtbot):
    page, _, _ = _page(qtbot)
    _run_and_wait(qtbot, page)
    page.survivors_table.selectRow(0)
    page.survivors_table.clearSelection()
    assert page.diff_view.toPlainText() == ""
    assert page.diff_view.extraSelections() == []


def test_diff_view_is_read_only_monospace(qtbot):
    page, _, _ = _page(qtbot)
    assert page.diff_view.isReadOnly() and page.diff_view.font().fixedPitch()


# --- on_enter ----------------------------------------------------------------------------------


def test_on_enter_redraws_existing_result(qtbot):
    page, _, _ = _page(qtbot)
    _run_and_wait(qtbot, page)
    page.survivors_table.setRowCount(0)
    page.on_enter()
    assert page.survivors_table.rowCount() == 2
    assert page.note_label.isHidden()


def test_on_enter_marks_result_stale_when_source_or_tests_changed(qtbot):
    page, _, _ = _page(qtbot)
    _run_and_wait(qtbot, page)
    page.state.source = SOURCE + "# değişti\n"
    page.on_enter()
    assert not page.note_label.isHidden() and "eski" in page.note_label.text()
    _run_and_wait(qtbot, page)
    assert page.note_label.isHidden()
    page.state.tests = []
    page.on_enter()
    assert not page.note_label.isHidden()


def test_diff_uses_the_source_the_result_was_computed_from(qtbot):
    page, _, _ = _page(qtbot)
    _run_and_wait(qtbot, page)
    page.state.source = "completely = different\n"
    page.on_enter()
    page.survivors_table.selectRow(0)
    assert "return a + 1" in page.diff_view.toPlainText()


def test_on_enter_after_reset_clears_view(qtbot):
    page, _, _ = _page(qtbot)
    _run_and_wait(qtbot, page)
    page.state.reset()
    page.on_enter()
    assert page.survivors_table.rowCount() == 0
    assert page.score_label.text() == "Skor: —"
    assert not page.run_button.isEnabled()


def test_on_enter_renders_result_set_by_another_component(qtbot):
    page, _, _ = _page(qtbot)
    page.state.mutation_run = RUN
    page.on_enter()
    assert page.survivors_table.rowCount() == 2
    assert page.note_label.isHidden()


# --- ana pencere ve gerçek uçtan uca -----------------------------------------------------------


def test_main_window_registers_mutation_page(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert isinstance(window.page("Mutasyon"), MutationPage)
    window.nav.setCurrentRow(3)
    assert window.stack.currentWidget() is window.page("Mutasyon")


def test_end_to_end_with_real_engine_finds_surviving_mutants(qtbot):
    source = "def f(a):\n    if a > 0:\n        return 1\n    return 2\n"
    tests = [TestCase("test_one", "def test_one():\n    assert f(1) == 1", "user")]
    page = MutationPage(AppState(source=source, tests=tests))  # gerçek motor ve servis
    _add_page(qtbot, page)
    assert _run_and_wait(qtbot, page, timeout=120000) is True

    assert page.status_label.text() == "Tamamlandı."
    assert page.score_label.text() == "Skor: 60.0%"
    assert page.skipped_label.text() == "Atlanan (kapsanmamış): 1"
    rows = _table(page)
    assert [(r[0], r[1]) for r in rows] == [("ROR", "2"), ("RETURN_NONE", "4")]
    assert page.state.mutation_run is not None
    assert len(page.state.mutation_run.survivors) >= 1

    page.survivors_table.selectRow(0)
    diff = page.diff_view.toPlainText()
    assert "-    if a > 0:" in diff and "+    if a >= 0:" in diff
    assert page.progress_bar.value() == page.progress_bar.maximum() == 5
    assert page.survivors_table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
