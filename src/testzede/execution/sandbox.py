"""Alt süreçte güvenli fonksiyon çağrısı (oracle)."""

from __future__ import annotations

import ast
import json
import os
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

# Generator fonksiyonlarının ilk kaç öğesi tüketilir (``rl.executor.GENERATOR_LIMIT`` ile aynı).
GENERATOR_LIMIT = 50

# Üst süreçteki coverage (örn. ``pytest --cov``) ayarları alt süreçlere sızmamalı: iç
# ``coverage run`` üst sürecin veri dosyasına yazar ve verisini bozar.
_COVERAGE_ENV_PREFIXES = ("COVERAGE_", "COV_CORE_")


def child_env() -> dict[str, str]:
    """Alt süreçler için ortam: ``os.environ``'ın ``COVERAGE_*``/``COV_CORE_*`` hariç kopyası."""
    # Windows'ta ortam değişkeni adları büyük/küçük harfe duyarsızdır: karşılaştırma büyük harfle.
    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(_COVERAGE_ENV_PREFIXES)
    }


# Alt süreçte çalışır. Sonucu stdout yerine dosyaya yazar: hedef kod print edebilir.
_RUNNER = """
import ast, inspect, itertools, json, sys

source_path, entry, args_repr, out_path, max_repr, gen_limit = sys.argv[1:7]
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
        if inspect.isgeneratorfunction(fn):
            # Gövde ancak tüketilince çalışır; sonsuz olabileceği için sınırlı tüketilir.
            value = list(itertools.islice(value, int(gen_limit)))
    except BaseException as exc:
        out = {"status": "raised", "exc_type": type(exc).__name__}
    else:
        # Kesilmiş repr literal_eval ile farklı bir değere dönüşebilir: kesmek yerine None ver.
        try:
            text = repr(value)
        except BaseException:
            text = None
        if text is not None and len(text) > int(max_repr):
            text = None
        out = {"status": "ok", "value_repr": text}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f)
"""


@dataclass(frozen=True)
class CallResult:
    status: Literal["ok", "raised", "timeout", "error"]
    value_repr: str | None  # "ok" ise repr(değer); repr yoksa/çok büyükse None
    exc_type: str | None  # status == "raised" ise örn. "ValueError"
    duration_s: float


def call_function(unit: CodeUnit, args_repr: str, *, timeout: float = 2.0) -> CallResult:
    """``unit.entry_point(*literal_eval(args_repr))`` çağrısını alt süreçte yapar.

    Giriş bir generator fonksiyonuysa ilk ``GENERATOR_LIMIT`` öğesi listeye toplanır;
    ``value_repr`` bu listenin ``repr``'idir.

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
                str(GENERATOR_LIMIT),
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    check=False,
                    cwd=tmp,
                    env=child_env(),
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
