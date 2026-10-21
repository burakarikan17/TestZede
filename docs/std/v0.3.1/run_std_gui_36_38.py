"""STD 3.6 (RL Test Üretimi) ve 3.8 (Toplu Test) adımlarını gerçek TestZede arayüzü üzerinde yürütür.

Girdiler STD'deki K1 ve T1a'dır; 3.8 için "Split: external", birim sınırı 5, CSV/HTML/XLSX.
Her adımda ekrandaki metin okunur, ekran görüntüsü alınır; sonuçlar results_36_38.json'a yazılır.
Kaydedilen test dosyası pytest ile çalıştırılır; rapor klasöründeki dosyalar ve split SHA-256'sı
gerçek dosyalarla karşılaştırılır. Çalıştırma (depo kökünden):
``QT_QPA_PLATFORM=offscreen python docs/std/v0.3.1/run_std_gui_36_38.py <çıktı klasörü>``
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog

OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)

K1 = "def sign(x):\n    if x > 0:\n        return 1\n    if x < 0:\n        return -1\n    return 0\n"
T1A = "def test_positive():\n    assert sign(5) == 1\n"

app = QApplication.instance() or QApplication(sys.argv)

from testzede.gui.main_window import MainWindow
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
    print(key, json.dumps(values, ensure_ascii=False)[:600], flush=True)


def shot(window: MainWindow, name: str) -> None:
    pump(0.2)
    window.grab().save(str(OUT / f"{name}.png"))


def go(window: MainWindow, title: str):
    page = window.page(title)
    window.nav.setCurrentRow(window.pages.index(page))
    pump(0.3)
    return page


def tiles(page) -> dict[str, str]:
    return {
        t.title.text(): f"{t.value.text()} | {t.detail.text()}"
        for t in (page.tile_tests, page.tile_branches, page.tile_lines, page.tile_rate)
    }


def generate(page) -> bool:
    reset_gap()
    page.generate_button.click()
    pump(0.3)
    ok = wait(lambda: page.generate_button.isEnabled() and page.test_list.count() > 0, 300)
    pump(0.3)
    return ok


win = MainWindow(AppState())
win.resize(1360, 860)
win.show()
pump(0.5)

# ---- 3.6 RL ile Test Üretme ------------------------------------------------------------------
sign_py = OUT / "sign.py"
sign_py.write_text(K1, encoding="utf-8")
rl = go(win, "RL Test Üretimi")
rl.set_source(K1, "sign")
rl.function_box.setCurrentText("sign")
shot(win, "3.6-1_K1_sign")
ok = generate(rl)
gap1 = round(_tick["max_gap"], 3)
code = rl.test_view.toPlainText()
record(
    "6.1",
    generated=ok,
    test_count=rl.test_list.count(),
    status=rl.status.text(),
    first_test=code.splitlines()[0] if code else "",
    code_visible=bool(code.strip()),
)
record("6.2", tiles=tiles(rl))
rate = rl.tile_rate.value.text()
record("6.3", coverage_rate=rate, passed=float(rate.strip("%")) >= 80 if rate.startswith("%") else False)
record("6.5", max_event_loop_gap_s=gap1)
shot(win, "3.6-2_testler_uretildi")

# kayıt + pytest
saved = OUT / "test_sign.py"
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(saved), "Python (*.py)"))
rl.save_button.click()
pump(0.3)
proc = subprocess.run(
    [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(saved)],
    cwd=OUT,
    capture_output=True,
    text=True,
    timeout=120,
)
record(
    "6.4",
    saved=saved.exists(),
    status=rl.status.text(),
    pytest_exit=proc.returncode,
    pytest_tail=proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-300:],
)
(OUT / "3.6-pytest.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")

# kullanıcı testleriyle tekrar (T1a)
rl.inputs.setCurrentWidget(rl.user_tests_edit)
rl.set_user_tests(T1A)
shot(win, "3.6-3_T1a_girildi")
ok2 = generate(rl)
record(
    "6.1-T1a",
    generated=ok2,
    test_count=rl.test_list.count(),
    status=rl.status.text(),
    tiles=tiles(rl),
    max_event_loop_gap_s=round(_tick["max_gap"], 3),
)
shot(win, "3.6-4_T1a_sonuc")

# ---- 3.8 Toplu Test ve Rapor -----------------------------------------------------------------
bp = go(win, "Toplu Test")
index = next(i for i in range(bp.target_box.count()) if bp.target_box.itemData(i).name == "external")
bp.target_box.setCurrentIndex(index)
bp.limit_box.setValue(5)
record(
    "8.0",
    target=bp.target_box.currentText(),
    limit=bp.limit_box.value(),
    formats={n: c.isChecked() for n, c in bp.format_checks.items()},
)
shot(win, "3.8-1_hazir")

reset_gap()
samples: list[tuple[int, int]] = []
bp.start_button.click()
pump(0.3)
end = time.monotonic() + 1800
while time.monotonic() < end and not (bp.start_button.isEnabled() and not bp._tasks.busy):
    app.processEvents()
    pair = (bp.progress.value(), bp.table.rowCount())
    if not samples or samples[-1] != pair:
        samples.append(pair)
        if pair[1] == 2:
            shot(win, "3.8-2_calisiyor")
    time.sleep(0.01)
pump(0.5)
rows = [
    [bp.table.item(r, c).text() if bp.table.item(r, c) else "" for c in range(bp.table.columnCount())]
    for r in range(bp.table.rowCount())
]
record(
    "8.1",
    progress_samples=samples,
    rows=rows,
    progress=f"{bp.progress.value()}/{bp.progress.maximum()}",
    status=bp.status.text(),
    max_event_loop_gap_s=round(_tick["max_gap"], 3),
)
shot(win, "3.8-3_bitti")

report_dir = bp._report_dir
files = sorted(str(p.relative_to(report_dir.parent)) for p in report_dir.rglob("*") if p.is_file()) if report_dir else []
record("8.2", report_dir=str(report_dir), files=files)
split_sha = hashlib.sha256(Path("data/splits/external.json").read_bytes()).hexdigest()
hits = {}
if report_dir:
    for p in report_dir.rglob("*"):
        if p.is_file() and p.suffix in {".csv", ".html"}:
            hits[p.name] = split_sha in p.read_text(encoding="utf-8-sig", errors="ignore")
    import openpyxl

    for p in report_dir.rglob("*.xlsx"):
        book = openpyxl.load_workbook(p, read_only=True)
        found = any(
            split_sha in str(cell)
            for sheet in book.worksheets
            for row in sheet.iter_rows(values_only=True)
            for cell in row
            if cell
        )
        hits[p.name] = found
record("8.3", split_sha256=split_sha, found_in=hits)

# ikinci çalıştırma: Durdur
rows_before = bp.table.rowCount()
bp.start_button.click()
pump(0.3)
got_row = wait(lambda: bp.table.rowCount() >= 1, 300)
shot(win, "3.8-4_durdurmadan_once")
bp.stop_button.click()
status_stopping = bp.status.text()
finished = wait(lambda: bp.start_button.isEnabled() and not bp._tasks.busy, 300)
pump(0.5)
record(
    "8.4",
    first_row_seen=got_row,
    status_after_stop_click=status_stopping,
    finished=finished,
    rows_after=bp.table.rowCount(),
    status=bp.status.text(),
    stopped_early=bp.status.text().startswith("Durduruldu"),
)
shot(win, "3.8-5_durduruldu")

record("genel", uncaught_exceptions=len(errors))
for err in errors:
    print(err, file=sys.stderr)
win.close()
pump(0.5)
(OUT / "results_36_38.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
)
