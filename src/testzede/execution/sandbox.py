"""Alt süreçte güvenli fonksiyon çağrısı (oracle). Gövde henüz yazılmadı."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from testzede.domain.models import CodeUnit

# Üretilen testler kaynak modülü bu isimle import eder: ``from target import <entry_point>``.
TARGET_MODULE = "target"


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
    raise NotImplementedError
