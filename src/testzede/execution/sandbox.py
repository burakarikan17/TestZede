"""Alt süreçte güvenli fonksiyon çağrısı (oracle)."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from testzede.domain.models import CodeUnit

# Üretilen testler kaynak modülü bu isimle import eder: ``from target import <entry_point>``.
TARGET_MODULE = "target"

_MAX_REPR = 10_000

# Alt süreçte çalışır. Sonucu stdout yerine dosyaya yazar: hedef kod print edebilir.
_RUNNER = """
import ast, json, sys

source_path, entry, args_repr, out_path, max_repr = sys.argv[1:6]
try:
    with open(source_path, encoding="utf-8") as f:
        code = compile(f.read(), "target", "exec")
    ns = {"__name__": "target"}
    exec(code, ns)
    fn = ns[entry]
except BaseException:
    out = {"status": "error"}
else:
    try:
        value = fn(*ast.literal_eval(args_repr))
        out = {"status": "ok", "value_repr": repr(value)[: int(max_repr)]}
    except BaseException as exc:
        out = {"status": "raised", "exc_type": type(exc).__name__}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f)
"""


@dataclass(frozen=True)
class CallResult:
    status: Literal["ok", "raised", "timeout", "error"]
    value_repr: str | None  # status == "ok" ise repr(dönüş değeri)
    exc_type: str | None  # status == "raised" ise örn. "ValueError"
    duration_s: float


def call_function(unit: CodeUnit, args_repr: str, *, timeout: float = 2.0) -> CallResult:
    """``unit.entry_point(*literal_eval(args_repr))`` çağrısını alt süreçte yapar.

    Hiçbir koşulda istisna fırlatmaz; timeout/çökme ``status`` ile döner.
    """
    start = time.perf_counter()

    def finish(status, value_repr=None, exc_type=None) -> CallResult:
        return CallResult(status, value_repr, exc_type, time.perf_counter() - start)

    try:
        if not unit.entry_point:
            return finish("error")
        args = ast.literal_eval(args_repr)
        if not isinstance(args, tuple):
            return finish("error")
        with tempfile.TemporaryDirectory(prefix="testzede_call_") as tmp:
            tmp_dir = Path(tmp)
            src = tmp_dir / "target.py"
            runner = tmp_dir / "runner.py"
            out = tmp_dir / "out.json"
            src.write_text(unit.source, encoding="utf-8")
            runner.write_text(_RUNNER, encoding="utf-8")
            cmd = [
                sys.executable,
                "-I",
                str(runner),
                str(src),
                unit.entry_point,
                args_repr,
                str(out),
                str(_MAX_REPR),
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    check=False,
                    cwd=tmp,
                    timeout=timeout,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.TimeoutExpired:
                return finish("timeout")
            if proc.returncode != 0 or not out.exists():
                return finish("error")
            data = json.loads(out.read_text(encoding="utf-8"))
            return finish(data["status"], data.get("value_repr"), data.get("exc_type"))
    except Exception:  # noqa: BLE001 - Madde-1: hiçbir durumda istisna sızmaz
        return finish("error")
