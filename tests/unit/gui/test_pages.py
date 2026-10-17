import time

import pytest
from PySide6.QtWidgets import QMessageBox

from testzede.domain.models import CodeUnit, CoverageReport, RunStats, TestCase
from testzede.gui.main_window import MainWindow
from testzede.gui.pages import batch_page, rl_page
from testzede.gui.pages.base import BasePage
from testzede.gui.pages.batch_page import BatchPage
from testzede.gui.pages.rl_page import RLPage
from testzede.gui.state import AppState
from testzede.services import batch_service
from testzede.services.batch_service import BatchOutcome, Target, UnitResult
from testzede.services.errors import ServiceError
from testzede.services.rl_service import GenerationResult

SOURCE = "def f(x):\n    if x:\n        return 1\n    return 0\n\n\ndef g():\n    return 2\n"


@pytest.fixture
def warnings(monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: shown.append(text))
    return shown


def _generation():
    test = TestCase(
        "test_step_001",
        "import pytest\n\nfrom target import f\n\n\ndef test_step_001():\n    assert f(1) == 1\n",
        "rl",
    )
    return GenerationResult(
        unit=CodeUnit("user/kod", SOURCE, entry_point="f"),
        tests=[test],
        coverage=CoverageReport(3, 4, 1, 2),
        stats=RunStats(generated=3, compiled=3, execution_time_s=0.5),
        curve=[],
        steps=4,
    )


def test_rl_page_lists_functions(qtbot):
    page = RLPage()
    qtbot.addWidget(page)
    page.set_source(SOURCE)
    assert [page.function_box.itemText(i) for i in range(page.function_box.count())] == ["f"]
    page.set_source("def f(:\n")
    assert "satır 1" in page.status.text()
    assert page.function_box.count() == 0


def test_rl_page_generates_in_background(qtbot, monkeypatch):
    calls = []

    def fake_generate(source, entry_point, **kwargs):
        calls.append((entry_point, kwargs))
        return _generation()

    monkeypatch.setattr(rl_page.rl_service, "generate", fake_generate)
    page = RLPage()
    qtbot.addWidget(page)
    page.set_source(SOURCE)
    page.generate_button.click()
    qtbot.waitUntil(lambda: page.test_list.count() == 1, timeout=5000)
    assert calls == [("f", {"user_tests": None, "module_name": None})]
    assert "assert f(1) == 1" in page.test_view.toPlainText()
    assert page.tile_tests.value.text() == "1"
    assert page.tile_branches.value.text() == "1 / 2"
    assert page.tile_lines.value.text() == "3 / 4"
    assert page.tile_rate.value.text() == "%75"
    assert page.save_button.isEnabled() and page.generate_button.isEnabled()


def test_rl_page_shows_service_error(qtbot, monkeypatch, warnings):
    def failing(source, entry_point, **kwargs):
        raise ServiceError("Fonksiyon bulunamadı")

    monkeypatch.setattr(rl_page.rl_service, "generate", failing)
    page = RLPage()
    qtbot.addWidget(page)
    page.set_source(SOURCE)
    page.generate_button.click()
    qtbot.waitUntil(lambda: bool(warnings), timeout=5000)
    assert warnings == ["Fonksiyon bulunamadı"]
    assert page.generate_button.isEnabled()


def test_rl_page_requires_function(qtbot, warnings):
    page = RLPage()
    qtbot.addWidget(page)
    page.generate_button.click()
    assert warnings == ["Önce test edilecek fonksiyonu seçin."]


def _fake_targets(data_dir):
    return [Target("split", "external", False), Target("dataset", "small67", True)]


def test_batch_page_disables_missing_targets(qtbot, monkeypatch):
    monkeypatch.setattr(batch_page.batch_service, "targets", _fake_targets)
    page = BatchPage()
    qtbot.addWidget(page)
    assert page.target_box.currentData().name == "small67"
    assert not page.target_box.model().item(0).isEnabled()
    assert page.start_button.isEnabled()


def test_batch_page_without_data(qtbot, monkeypatch):
    monkeypatch.setattr(batch_page.batch_service, "targets", lambda d: [])
    page = BatchPage()
    qtbot.addWidget(page)
    assert not page.start_button.isEnabled()
    assert "testzede download" in page.status.text()


def test_batch_page_runs_and_stops(qtbot, monkeypatch, tmp_path):
    report = tmp_path / "2026-10-17" / "small67" / "results.csv"

    def fake_run(target, *, progress, should_stop, limit, formats, **_):
        assert limit == 2 and formats == ["csv", "xlsx"]
        results = []
        for i in range(3):
            if should_stop():
                return BatchOutcome(results, {"small67": [report]}, stopped=True)
            result = UnitResult(f"small67/{i}", "small67", test_count=1)
            results.append(result)
            progress(i + 1, 3, result)
            deadline = time.monotonic() + 5
            while not should_stop() and time.monotonic() < deadline:
                time.sleep(0.01)  # arayüz "Durdur"a basana kadar bekle
        return BatchOutcome(results, {"small67": [report]})

    monkeypatch.setattr(batch_page.batch_service, "targets", _fake_targets)
    monkeypatch.setattr(batch_page.batch_service, "run", fake_run)
    page = BatchPage()
    qtbot.addWidget(page)
    page.limit_box.setValue(2)
    page.format_checks["html"].setChecked(False)
    page.start_button.click()
    qtbot.waitUntil(lambda: page.table.rowCount() == 1, timeout=5000)
    assert not page.start_button.isEnabled()
    page.stop_button.click()
    qtbot.waitUntil(lambda: page.start_button.isEnabled(), timeout=5000)
    assert page.table.rowCount() == 1
    assert page.table.item(0, 1).text() == "tamam"
    assert page.status.text().startswith("Durduruldu: 1 birim")
    assert page.open_button.isEnabled()


def test_main_window_hosts_pages(qtbot, monkeypatch):
    monkeypatch.setattr(batch_page.batch_service, "targets", _fake_targets)
    window = MainWindow()
    qtbot.addWidget(window)
    assert [window.nav.item(i).text() for i in range(window.nav.count())] == [
        "RL Test Üretimi",
        "Toplu Test",
    ]
    window.nav.setCurrentRow(1)
    assert window.stack.currentWidget() is window.page("Toplu Test")
    window.close()


class _RecordingPage(BasePage):
    """``on_enter`` çağrılarını sayan sayfa."""

    def __init__(self, title: str, state: AppState) -> None:
        super().__init__(title, state)
        self.entered = 0

    def on_enter(self) -> None:
        self.entered += 1


def _recording(title):
    return lambda state: _RecordingPage(title, state)


def test_main_window_calls_on_enter_when_page_is_shown(qtbot):
    window = MainWindow(pages=(_recording("A"), _recording("B")))
    qtbot.addWidget(window)
    first, second = window.pages
    assert (first.entered, second.entered) == (1, 0)  # ilk sayfa açılışta gösterilir
    window.nav.setCurrentRow(1)
    window.nav.setCurrentRow(0)
    assert (first.entered, second.entered) == (2, 1)


def test_main_window_shares_one_state_across_pages(qtbot, monkeypatch):
    monkeypatch.setattr(batch_page.batch_service, "targets", _fake_targets)
    state = AppState(source="x = 1")
    window = MainWindow(state)
    qtbot.addWidget(window)
    assert window.state is state
    assert all(page.state is state for page in window.pages)


def test_batch_service_reexports_types():
    assert batch_service.UnitResult is UnitResult


def test_rl_page_passes_user_tests_and_shows_comparison(qtbot, monkeypatch):
    seen = {}

    def fake_generate(source, entry_point, **kwargs):
        seen.update(kwargs)
        result = _generation()
        result.baseline = CoverageReport(2, 4, 1, 2)
        result.user_outcome = "failed"
        return result

    monkeypatch.setattr(rl_page.rl_service, "generate", fake_generate)
    page = RLPage()
    qtbot.addWidget(page)
    page.set_source(SOURCE, module_name="hesap")
    page.set_user_tests("from hesap import f\n\n\ndef test_f():\n    assert f(0) == 0\n")
    page.generate_button.click()
    qtbot.waitUntil(lambda: page.test_list.count() == 1, timeout=5000)
    assert seen["module_name"] == "hesap" and "def test_f" in seen["user_tests"]
    assert page.tile_rate.detail.text().startswith("kullanıcı testleri %50 → + RL")
    assert page.tile_lines.detail.text() == "kullanıcı testleri: 2"
    assert "kullanıcı testleri başarısız" in page.status.text()
