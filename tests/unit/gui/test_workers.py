from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, QThread, Slot

from testzede.gui.workers import Worker, run_in_thread


def _finish(thread: QThread) -> None:
    thread.quit()
    assert thread.wait(5000)


def test_success_emits_progress_then_finished(qtbot):
    def job(progress_callback, should_cancel):
        progress_callback(1, 2)
        progress_callback(2, 2)
        return {"sonuç": 42}

    worker = Worker(job)
    progress: list[tuple[int, int]] = []
    worker.progress.connect(lambda d, t: progress.append((d, t)))
    with qtbot.waitSignal(worker.finished, timeout=5000) as blocker:
        thread = run_in_thread(worker)
    assert blocker.args == [{"sonuç": 42}]
    qtbot.waitUntil(lambda: len(progress) == 2, timeout=2000)
    assert progress == [(1, 2), (2, 2)]
    _finish(thread)


def test_exception_emits_failed_with_message_and_no_finished(qtbot):
    def job(progress_callback, should_cancel):
        raise ValueError("kötü girdi")

    worker = Worker(job)
    finished: list[object] = []
    worker.finished.connect(finished.append)
    with qtbot.waitSignal(worker.failed, timeout=5000) as blocker:
        thread = run_in_thread(worker)
    assert blocker.args == ["kötü girdi"]
    _finish(thread)
    assert finished == []


def test_exception_without_message_reports_type_name(qtbot):
    def job(progress_callback, should_cancel):
        raise RuntimeError

    worker = Worker(job)
    with qtbot.waitSignal(worker.failed, timeout=5000) as blocker:
        thread = run_in_thread(worker)
    assert blocker.args == ["RuntimeError"]
    _finish(thread)


def test_cancel_stops_job_and_returns_partial_result(qtbot):
    started = threading.Event()

    def job(progress_callback, should_cancel):
        done = 0
        started.set()
        while not should_cancel() and done < 1000:
            time.sleep(0.01)
            done += 1
        return done

    worker = Worker(job)
    assert not worker.is_cancelled()
    with qtbot.waitSignal(worker.finished, timeout=5000) as blocker:
        thread = run_in_thread(worker)
        qtbot.waitUntil(started.is_set, timeout=2000)
        worker.cancel()
    assert worker.is_cancelled()
    assert blocker.args[0] < 1000  # tamamlanmadan durdu
    _finish(thread)


def test_job_runs_off_the_gui_thread_and_signals_arrive_on_it(qtbot):
    seen: dict[str, int] = {}
    main_ident = threading.get_ident()

    def job(progress_callback, should_cancel):
        seen["job"] = threading.get_ident()
        progress_callback(1, 1)

    class Receiver(QObject):
        """Gerçek sayfalar gibi bir QObject yuvası: sinyal GUI iş parçacığına kuyruklanır."""

        @Slot(int, int)
        def on_progress(self, done: int, total: int) -> None:
            seen["slot"] = threading.get_ident()

    receiver = Receiver()
    worker = Worker(job)
    worker.progress.connect(receiver.on_progress)
    with qtbot.waitSignal(worker.finished, timeout=5000):
        thread = run_in_thread(worker)
    qtbot.waitUntil(lambda: "slot" in seen, timeout=2000)
    assert seen["job"] != main_ident
    assert seen["slot"] == main_ident
    _finish(thread)


def test_gui_thread_stays_responsive_while_job_runs(qtbot):
    release = threading.Event()

    def job(progress_callback, should_cancel):
        release.wait(5)
        return "bitti"

    worker = Worker(job)
    thread = run_in_thread(worker)
    qtbot.waitUntil(thread.isRunning, timeout=2000)
    ticks: list[int] = []
    for i in range(3):  # iş sürerken ana iş parçacığı olayları işlemeye devam eder
        qtbot.wait(20)
        ticks.append(i)
    assert ticks == [0, 1, 2]
    with qtbot.waitSignal(worker.finished, timeout=5000) as blocker:
        release.set()
    assert blocker.args == ["bitti"]
    _finish(thread)


def test_thread_quits_after_job_ends(qtbot):
    worker = Worker(lambda progress_callback, should_cancel: 1)
    with qtbot.waitSignal(worker.finished, timeout=5000):
        thread = run_in_thread(worker)
    assert thread.wait(5000)
    assert thread.isFinished()
