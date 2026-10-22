"""STD 3.1-3.5 ve 3.7 adımlarını gerçek TestZede arayüzü üzerinde yürütür.

Girdiler STD'deki K1, T1, T1a, K2, T3, H1'dir. Her adımda ekrandaki metin okunur,
ekran görüntüsü alınır; sonuçlar results.json'a yazılır.
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

K1 = "def sign(x):\n    if x > 0:\n        return 1\n    if x < 0:\n        return -1\n    return 0\n"
T1 = (
    "def test_positive():\n    assert sign(5) == 1\n"
    "def test_negative():\n    assert sign(-3) == -1\n"
    "def test_zero():\n    assert sign(0) == 0\n"
)
T1A = "def test_positive():\n    assert sign(5) == 1\n"
K2 = (
    "import math\n"
    "def fact(n):\n    return 1 if n < 2 else n * fact(n - 1)\n"
    "def main(x):\n    print(len(str(fact(x))), math.sqrt(x))\n"
    "main(3)\n"
)
T3 = "def test_loop():\n    while True:\n        pass\n"
H1 = "def f(:\n    pass\n"

app = QApplication.instance() or QApplication(sys.argv)

from testzede.gui.main_window import MainWindow
from testzede.gui.pages import coverage_logic
from testzede.gui.state import AppState

errors: list[str] = []
sys.excepthook = lambda t, v, tb: errors.append("".join(traceback.format_exception(t, v, tb)))

results: dict[str, dict] = {}
_tick = {"last": time.monotonic(), "max_gap": 0.0}


def _on_tick() -> None:
    now = time.monotonic()
    _tick["max_gap"] = max(_tick["max_gap"], now - _tick["last"])
    _tick["last"] = now


ticker = QTimer()
ticker.setInterval(20)
ticker.timeout.connect(_on_tick)
ticker.start()


def pump(seconds: float = 0.2) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def wait(cond, timeout: float = 30.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def reset_gap() -> None:
    _tick["last"] = time.monotonic()
    _tick["max_gap"] = 0.0


def record(key: str, **values) -> None:
    results.setdefault(key, {}).update(values)
    print(key, json.dumps(values, ensure_ascii=False)[:400], flush=True)


def new_window(state: AppState | None = None) -> MainWindow:
    window = MainWindow(state or AppState())
    window.resize(1360, 860)
    window.show()
    pump(0.5)
    return window


def go(window: MainWindow, title: str):
    page = window.page(title)
    window.nav.setCurrentRow(window.pages.index(page))
    pump(0.3)
    return page


def shot(window: MainWindow, name: str) -> None:
    pump(0.2)
    window.grab().save(str(OUT / f"{name}.png"))


def run_page(page, timeout: float = 60.0) -> bool:
    wait(lambda: not page._tasks.busy, 10)
    done: list[bool] = []
    page.run_completed.connect(lambda ok: done.append(ok))
    reset_gap()
    page.run_button.click()
    wait(lambda: bool(done), timeout)
    return bool(done and done[0])


def table(tbl) -> list[list[str]]:
    return [
        [tbl.item(r, c).text() if tbl.item(r, c) else "" for c in range(tbl.columnCount())]
        for r in range(tbl.rowCount())
    ]


win = new_window()
code = go(win, "Kod Yükle")

# ---- 3.1 Kod Yükleme ---------------------------------------------------------------------
code.tabs.setCurrentIndex(0)
code.editor.setPlainText(K1)
code.validate_button.click()
record("1.1", status=code.status_label.text(), kind=code.status_label.property("status"))
shot(win, "3.1-1_K1")
code.tabs.setCurrentIndex(1)
code.tests_editor.setPlainText(T1)
code.tests_validate_button.click()
record(
    "1.2", status=code.tests_status_label.text(), kind=code.tests_status_label.property("status")
)
shot(win, "3.1-2_T1")
sample = OUT / "sign.py"
sample.write_text(K1, encoding="utf-8")
code.tabs.setCurrentIndex(0)
code.editor.setPlainText("")
pump(0.6)
loaded = code.load_file(sample)  # "Dosya Aç" iletişim kutusunun seçtiği dosya
record(
    "1.3",
    loaded=loaded,
    editor_matches=code.editor.toPlainText() == K1,
    status=code.status_label.text(),
    module=win.page("Kod Yükle").state.module_name,
)
shot(win, "3.1-3_dosya_ac")
graph = go(win, "Çağrı Grafiği")
record(
    "1.4",
    code_radio=graph.picker.code_radio.text(),
    checked=graph.picker.code_radio.isChecked(),
    run_enabled=graph.run_button.isEnabled(),
    status=graph.status_label.text(),
    hint=graph.picker.hint.text(),
)
shot(win, "3.1-4_cagri_grafigi")

# ---- 3.2 Hatalı Kod Girişi ---------------------------------------------------------------
code = go(win, "Kod Yükle")
code.tabs.setCurrentIndex(0)
code.editor.setPlainText(K1)
code.validate()
code.editor.setPlainText(H1)
code.validate_button.click()
record(
    "2.1",
    status=code.status_label.text(),
    kind=code.status_label.property("status"),
)
shot(win, "3.2-1_H1")
record("2.2", state_source_is_K1=code.state.source == K1, status=code.status_label.text())
code.editor.setPlainText("")
code.validate_button.click()
record("2.2-bos", status=code.status_label.text(), state_source_is_K1=code.state.source == K1)
shot(win, "3.2-2_bos")

empty = new_window()  # kod yokken (yeni açılmış uygulama)
for title in ("Çağrı Grafiği", "Metrikler", "Coverage"):
    page = go(empty, title)
    record(
        f"2.3-{title}",
        run_enabled=page.run_button.isEnabled(),
        status=page.status_label.text(),
    )
    shot(empty, "3.2-3_kodsuz_" + title.replace("Çağrı Grafiği", "CagriGrafigi"))
empty.close()
pump(0.3)

bad = OUT / "latin1.py"
bad.write_bytes("x = 'çğış'\n".encode("cp1254"))
code = go(win, "Kod Yükle")
ok = code.load_file(bad)
record("2.4", loaded=ok, status=code.status_label.text(), kind=code.status_label.property("status"))
shot(win, "3.2-4_utf8_olmayan")
missing = code.load_file(OUT / "yok.py")
record("2.4-yok", loaded=missing, status=code.status_label.text())
record("2.5", window_visible=win.isVisible(), uncaught=len(errors))

# ---- 3.3 Çağrı Grafiği -------------------------------------------------------------------
code.editor.setPlainText(K2)
code.validate()
graph = go(win, "Çağrı Grafiği")
graph.picker.code_radio.setChecked(True)
ok = run_page(graph)
rows = table(graph.node_table)
kinds: dict[str, list[str]] = {}
for label, kind, *_ in rows:
    kinds.setdefault(kind, []).append(label)
record("3.1", ok=ok, kinds=kinds, rows=rows)
record("3.2", summary=graph.summary_label.text(), max_gap_s=round(_tick["max_gap"], 3))
shot(win, "3.3-1_K2_grafik")
main_row = next(i for i, r in enumerate(rows) if r[0].startswith("main"))
graph.node_table.selectRow(main_row)
pump(0.3)
record("3.3-tablo", canvas_selected=graph.canvas.selected, detail=graph.detail_label.text())
shot(win, "3.3-2_main_secili")
fact = next(n.name for n in graph._rows if n.label.startswith("fact"))
graph.canvas.node_clicked.emit(fact)  # grafikte düğüme tıklama sinyali
pump(0.3)
sel = graph.node_table.selectionModel().selectedRows()
record(
    "3.3-grafik",
    canvas_selected=graph.canvas.selected,
    table_row=rows[sel[0].row()][0] if sel else None,
    detail=graph.detail_label.text(),
)
shot(win, "3.3-3_fact_tiklandi")
loaded_tasks: list[bool] = []
graph.picker.tasks_loaded.connect(lambda ok: loaded_tasks.append(ok))
graph.picker.task_radio.setChecked(True)
wait(lambda: bool(loaded_tasks) or graph.picker.task_box.count() > 0, 20)
graph.picker.task_box.setCurrentIndex(0)
pump(0.2)
ok = run_page(graph)
record(
    "3.4",
    ok=ok,
    task=graph.picker.task_box.currentText(),
    tasks=graph.picker.task_box.count(),
    summary=graph.summary_label.text(),
    nodes=graph.node_table.rowCount(),
)
shot(win, "3.3-4_humaneval")
graph.picker.code_radio.setChecked(True)

# ---- 3.4 Metrikler -----------------------------------------------------------------------
code = go(win, "Kod Yükle")
code.editor.setPlainText(K1)
code.validate()
metrics = go(win, "Metrikler")
metrics.picker.code_radio.setChecked(True)
ok = run_page(metrics)
mrows = table(metrics.table)
record("4.1", ok=ok, count=len(mrows))
record("4.2", values={r[0]: r[1] for r in mrows})
record("4.3", summary=metrics.summary_label.text())
shot(win, "3.4-1_metrikler")
csv_path = OUT / "metrikler.csv"
exported = metrics.export_csv(csv_path)  # "CSV'ye Aktar…" iletişim kutusunun seçtiği yol
raw = csv_path.read_bytes() if csv_path.exists() else b""
text = raw.decode("utf-8-sig") if raw else ""
record(
    "4.4",
    exported=exported,
    bom=raw.startswith(b"\xef\xbb\xbf"),
    lines=len(text.splitlines()),
    header=text.splitlines()[0] if text else "",
    turkish_ok=all(w in text for w in ("Çevrimsel Karmaşıklık", "Sürdürülebilirlik İndeksi")),
)

# ---- 3.5 Coverage ------------------------------------------------------------------------
code = go(win, "Kod Yükle")
code.editor.setPlainText(K1)
code.validate()
code.tests_editor.setPlainText(T1A)
code.validate_tests()
cov = go(win, "Coverage")
ok = run_page(cov)
statuses = coverage_logic.line_statuses(cov._shown) if getattr(cov, "_shown", None) else None
record(
    "5.1",
    ok=ok,
    lines=cov.lines_label.text(),
    branches=cov.branches_label.text(),
    tests=table(cov.test_table),
    status=cov.status_label.text(),
)
sels = cov.source_view.extraSelections()
record(
    "5.3",
    colored_lines=len(sels),
    colors=sorted({s.format.background().color().name() for s in sels}),
    statuses=statuses,
)
shot(win, "3.5-1_T1a")
code = go(win, "Kod Yükle")
code.tests_editor.setPlainText(T1)
code.validate_tests()
cov = go(win, "Coverage")
ok = run_page(cov)
record(
    "5.2",
    ok=ok,
    lines=cov.lines_label.text(),
    branches=cov.branches_label.text(),
    tests=table(cov.test_table),
)
shot(win, "3.5-2_T1")
code = go(win, "Kod Yükle")
code.tests_editor.setPlainText(T1 + T3)
code.validate_tests()
cov = go(win, "Coverage")
start = time.monotonic()
ok = run_page(cov, timeout=120)
record(
    "5.4",
    ok=ok,
    seconds=round(time.monotonic() - start, 1),
    tests=table(cov.test_table),
    status=cov.status_label.text(),
    max_gap_s=round(_tick["max_gap"], 3),
    window_visible=win.isVisible(),
)
shot(win, "3.5-3_T3_zaman_asimi")

# ---- 3.7 Mutasyon ------------------------------------------------------------------------
code = go(win, "Kod Yükle")
code.editor.setPlainText(K1)
code.validate()
code.tests_editor.setPlainText(T1)
code.validate_tests()
mut = go(win, "Mutasyon")
mut.max_spin.setValue(100)
progress_seen: list[int] = []
mut.progress_bar.valueChanged.connect(lambda v: progress_seen.append(v))
ok = run_page(mut, timeout=180)
record(
    "7.1",
    ok=ok,
    max_mutants=mut.max_spin.value(),
    score=mut.score_label.text(),
    killed=mut.killed_label.text(),
    survived=mut.survived_label.text(),
    timeout=mut.timeout_label.text(),
    skipped=mut.skipped_label.text(),
    compilation=mut.compilation_label.text(),
    time=mut.time_label.text(),
    status=mut.status_label.text(),
)
record("7.2", survivors=table(mut.survivors_table))
shot(win, "3.7-1_mutasyon")
if mut.survivors_table.rowCount():
    mut.survivors_table.selectRow(0)
    pump(0.3)
record("7.3", diff=mut.diff_view.toPlainText())
record("7.4", max_gap_s=round(_tick["max_gap"], 3), progress_updates=len(progress_seen))
shot(win, "3.7-2_fark")

record("genel", uncaught_exceptions=errors, window_visible=win.isVisible())
win.close()
pump(0.5)
(OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), "utf-8")
print("BITTI", flush=True)
