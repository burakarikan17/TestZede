"""execution/ ve mutation/ süre ölçümü (sadece ölçer, üretim kodunu değiştirmez).

Kullanım: ``python scripts/bench.py [--repeats 5]``
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from testzede.domain.models import CodeUnit, TestCase
from testzede.execution.coverage_runner import run_tests
from testzede.execution.sandbox import TARGET_MODULE, call_function
from testzede.mutation.engine import MutationEngine, _default_workers
from testzede.mutation.operators import generate_all

SIMPLE = "def f(a):\n    if a > 0:\n        return 1\n    return 2\n"
MUTATED = """def score(a, b, limit):
    total = a + b
    if total > limit:
        return limit
    if total < 0:
        return 0
    if a == b:
        return total * 2
    return total
"""
MUTATED_TESTS = [
    "def test_a():\n    assert score(1, 2, 10) == 3",
    "def test_b():\n    assert score(5, 5, 100) == 20\n    assert score(9, 9, 10) == 10",
    "def test_c():\n    assert score(-5, 1, 10) == 0",
]
HEADER = f"import pytest\nimport {TARGET_MODULE}\nfrom {TARGET_MODULE} import *  # noqa\n"
PYTEST = [sys.executable, "-I", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
COVERAGE = [sys.executable, "-I", "-m", "coverage", "run", "--branch"]


def timed(fn: Callable[[], object], repeats: int) -> list[float]:
    """``fn`` çağrısını ``repeats`` kez çalıştırıp süreleri (sn) döndürür."""
    out = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        out.append(time.perf_counter() - start)
    return out


def row(label: str, times: list[float], extra: str = "") -> None:
    """Bir sonuç satırı yazdırır: ortalama, min, max."""
    mean, lo, hi = statistics.mean(times), min(times), max(times)
    print(f"{label:<46}{mean:>9.3f}{lo:>9.3f}{hi:>9.3f}  {extra}")


def sh(cmd: list[str], cwd: Path) -> None:
    """Alt süreci (shell'siz, timeout'lu) çalıştırır."""
    subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        timeout=120,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def write_suite(tmp: Path, source: str, tests: list[str]) -> None:
    """``run_tests``'in yazdığı dosya düzenini geçici dizine yazar."""
    (tmp / f"{TARGET_MODULE}.py").write_text(source, encoding="utf-8")
    for i, code in enumerate(tests):
        (tmp / f"test_{i:04d}.py").write_text(HEADER + "\n" + code + "\n", encoding="utf-8")


def coverage_cmd() -> list[str]:
    """``coverage_runner`` ile aynı ``coverage run`` komutu."""
    return [
        *COVERAGE,
        f"--include={TARGET_MODULE}.py",
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "--continue-on-collection-errors",
        "--junitxml=report.xml",
    ]


def split_run(source: str, tests: list[str]) -> tuple[float, float]:
    """(coverage+pytest alt süreci, ``coverage json`` adımı) sürelerini ayrı ölçer."""
    with tempfile.TemporaryDirectory(prefix="bench_") as tmp:
        tmp_dir = Path(tmp)
        write_suite(tmp_dir, source, tests)
        t0 = time.perf_counter()
        sh(coverage_cmd(), tmp_dir)
        t1 = time.perf_counter()
        sh([sys.executable, "-I", "-m", "coverage", "json", "-q", "-o", "coverage.json"], tmp_dir)
        return t1 - t0, time.perf_counter() - t1


def plain_pytest(source: str, tests: list[str]) -> float:
    """Coverage'sız düz pytest süresi."""
    with tempfile.TemporaryDirectory(prefix="bench_") as tmp:
        tmp_dir = Path(tmp)
        write_suite(tmp_dir, source, tests)
        start = time.perf_counter()
        sh([*PYTEST, "--continue-on-collection-errors", "--junitxml=report.xml"], tmp_dir)
        return time.perf_counter() - start


def main() -> None:
    """Tüm ölçümleri çalıştırıp tablo basar."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=5)
    n = parser.parse_args().repeats
    print(f"{'ölçüm':<46}{'ort(s)':>9}{'min':>9}{'max':>9}  (n={n})")

    print("\n[1] sandbox.call_function")
    unit = CodeUnit(uid="b/0", source=SIMPLE, entry_point="f", dataset=None)
    row("call_function f(1)", timed(lambda: call_function(unit, "(1,)"), n))

    print("\n[2] coverage_runner.run_tests")
    for count in (1, 5, 20):
        tests = [f"def test_{i}():\n    assert f({i + 1}) == 1" for i in range(count)]
        cases = [TestCase(f"t{i}", code, "user") for i, code in enumerate(tests)]
        row(f"run_tests, {count} test (toplam)", timed(lambda c=cases: run_tests(unit, c), n))
        parts = [split_run(SIMPLE, tests) for _ in range(n)]
        row(f"  coverage run + pytest alt süreci ({count})", [p[0] for p in parts])
        row(f"  coverage json adımı ({count})", [p[1] for p in parts])

    print("\n[3] MutationEngine.run_detailed (önceki sıralı+coverage'lı sürüm: 24.378 sn)")
    cases = [TestCase(f"t{i}", c, "user") for i, c in enumerate(MUTATED_TESTS)]
    mutants = generate_all(MUTATED)
    for label, workers in (("workers=1", 1), (f"workers={_default_workers()} (varsayılan)", None)):
        totals = []
        for _ in range(n):
            start = time.perf_counter()
            run = MutationEngine(workers=workers).run_detailed(MUTATED, cases)
            totals.append(time.perf_counter() - start)
        extra = (
            f"{len(mutants)} mutant, atlanan {run.skipped_uncovered}, killed {run.report.killed}"
        )
        row(f"engine, {label}", totals, extra)
        row("  mutant başına (toplam / mutant)", [t / run.report.total for t in totals])

    print("\n[4] referans alt süreç maliyetleri")
    with tempfile.TemporaryDirectory(prefix="bench_") as tmp:
        tmp_dir = Path(tmp)
        write_suite(tmp_dir, SIMPLE, ["def test_x():\n    assert f(1) == 1"])
        refs = {
            "python -I -c pass": [sys.executable, "-I", "-c", "pass"],
            "python -I -c 'import pytest'": [sys.executable, "-I", "-c", "import pytest"],
            "python -I -c 'import coverage'": [sys.executable, "-I", "-c", "import coverage"],
            "python -I -m pytest -q (1 test)": PYTEST,
            "python -I -m coverage run -m pytest -q (1 test)": [*COVERAGE, "-m", "pytest", "-q"],
        }
        for label, cmd in refs.items():
            row(label, timed(lambda c=cmd: sh(c, tmp_dir), n))

    print("\n[5] bir mutant: coverage'lı ve coverage'sız")
    mutant = mutants[0].source
    row("mutant, coverage run + pytest", [split_run(mutant, MUTATED_TESTS)[0] for _ in range(n)])
    row(
        "mutant, düz pytest (coverage yok)", [plain_pytest(mutant, MUTATED_TESTS) for _ in range(n)]
    )


if __name__ == "__main__":
    main()
