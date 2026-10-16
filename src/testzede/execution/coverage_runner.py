"""``coverage run --branch -m pytest`` sarmalayıcısı."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from testzede.domain.models import CodeUnit, CoverageReport, RunStats, TestCase
from testzede.execution.sandbox import TARGET_MODULE

Outcome = Literal["passed", "failed", "error", "timeout"]

_MODULE_RE = re.compile(r"test_(\d{4,})$")
# Aynı isimli testlerde en kötü sonuç kazanır.
_SEVERITY: dict[str, int] = {"passed": 0, "failed": 1, "error": 2, "timeout": 3}


@dataclass
class ExecutionResult:
    coverage: CoverageReport
    stats: RunStats
    covered_lines: frozenset[int]
    # coverage.py arc'ları (çıkış için negatif olabilir)
    covered_branches: frozenset[tuple[int, int]]
    all_lines: frozenset[int]
    all_branches: frozenset[tuple[int, int]]
    # anahtar: TestCase.name
    test_outcomes: dict[str, Outcome]


def run_tests(
    unit: CodeUnit, tests: Sequence[TestCase], *, timeout: float = 10.0
) -> ExecutionResult:
    """Testleri alt süreçte koşturur; yalnızca ``unit.source`` ölçülür.

    Hiçbir koşulda istisna fırlatmaz; derleme hatası/timeout ``test_outcomes`` içinde döner.
    ``per_function`` değerleri 0-1 aralığında satır kapsama oranıdır.
    """
    start = time.perf_counter()
    data: dict | None = None
    try:
        outcomes, data = _run(unit, tests, timeout)
    except Exception:  # noqa: BLE001 - Madde-1: hiçbir durumda istisna sızmaz
        outcomes = {i: "error" for i in range(len(tests))}
    elapsed = time.perf_counter() - start

    names: dict[str, Outcome] = {}
    for i, test in enumerate(tests):
        new = outcomes.get(i, "error")
        old = names.get(test.name)
        if old is None or _SEVERITY[new] > _SEVERITY[old]:
            names[test.name] = new
    compiled = sum(1 for i in range(len(tests)) if outcomes.get(i, "error") != "error")
    return _build_result(data, names, len(tests), compiled, elapsed)


def _run(
    unit: CodeUnit, tests: Sequence[TestCase], timeout: float
) -> tuple[dict[int, Outcome], dict | None]:
    outcomes: dict[int, Outcome] = {}
    runnable: list[int] = []
    for i, test in enumerate(tests):
        try:
            ast.parse(test.code)
        except (SyntaxError, ValueError):
            outcomes[i] = "error"
        else:
            runnable.append(i)
    if not runnable:
        return outcomes, None

    header = f"import pytest\nimport {TARGET_MODULE}\nfrom {TARGET_MODULE} import *  # noqa\n"
    if unit.entry_point:
        header += f"from {TARGET_MODULE} import {unit.entry_point}\n"

    with tempfile.TemporaryDirectory(prefix="testzede_run_") as tmp:
        tmp_dir = Path(tmp)
        (tmp_dir / f"{TARGET_MODULE}.py").write_text(unit.source, encoding="utf-8")
        for i in runnable:
            path = tmp_dir / f"test_{i:04d}.py"
            path.write_text(header + "\n" + tests[i].code + "\n", encoding="utf-8")

        cmd = [
            sys.executable,
            "-I",
            "-m",
            "coverage",
            "run",
            "--branch",
            f"--include={TARGET_MODULE}.py",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--continue-on-collection-errors",
            "--junitxml=report.xml",
        ]
        try:
            subprocess.run(
                cmd,
                check=False,
                cwd=tmp,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            outcomes.update({i: "timeout" for i in runnable})
            return outcomes, None

        reported = _parse_junit(tmp_dir / "report.xml")
        for i in runnable:
            # Hiç raporlanmayan modül: test fonksiyonu yok ya da süreç çöktü.
            outcomes[i] = reported.get(i, "error")
        return outcomes, _coverage_json(tmp_dir)


def _parse_junit(path: Path) -> dict[int, Outcome]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {}
    result: dict[int, Outcome] = {}
    for case in root.iter("testcase"):
        # Toplama hatasında classname boştur ve name modül adıdır.
        module = (case.get("classname") or case.get("name") or "").split(".")[0]
        match = _MODULE_RE.match(module)
        if not match:
            continue
        index = int(match.group(1))
        if case.find("error") is not None:
            outcome: Outcome = "error"
        elif case.find("failure") is not None:
            outcome = "failed"
        else:
            outcome = "passed"
        if index not in result or _SEVERITY[outcome] > _SEVERITY[result[index]]:
            result[index] = outcome
    return result


def _coverage_json(tmp_dir: Path) -> dict | None:
    out = tmp_dir / "coverage.json"
    subprocess.run(
        [sys.executable, "-I", "-m", "coverage", "json", "-q", "-o", str(out)],
        check=False,
        cwd=tmp_dir,
        timeout=30,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not out.exists():
        return None
    files = json.loads(out.read_text(encoding="utf-8")).get("files", {})
    return files.get(f"{TARGET_MODULE}.py")


def _arcs(items: list) -> frozenset[tuple[int, int]]:
    return frozenset((int(a), int(b)) for a, b in items)


def _build_result(
    data: dict | None,
    names: dict[str, Outcome],
    generated: int,
    compiled: int,
    elapsed: float,
) -> ExecutionResult:
    d = data or {}
    executed_lines = frozenset(d.get("executed_lines", ()))
    all_lines = executed_lines | frozenset(d.get("missing_lines", ()))
    executed_br = _arcs(d.get("executed_branches", ()))
    all_branches = executed_br | _arcs(d.get("missing_branches", ()))

    per_function = {
        func: info["summary"]["percent_covered"] / 100
        for func, info in d.get("functions", {}).items()
        if func  # "" = modül düzeyi
    }
    coverage = CoverageReport(
        covered_lines=len(executed_lines),
        total_lines=len(all_lines),
        covered_branches=len(executed_br),
        total_branches=len(all_branches),
        per_function=per_function,
    )
    stats = RunStats(generated=generated, compiled=compiled, execution_time_s=elapsed)
    return ExecutionResult(
        coverage=coverage,
        stats=stats,
        covered_lines=executed_lines,
        covered_branches=executed_br,
        all_lines=all_lines,
        all_branches=all_branches,
        test_outcomes=names,
    )
