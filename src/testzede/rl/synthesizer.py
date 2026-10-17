"""Test sentezleyici: RL'nin ürettiği girdiyi pytest fonksiyonuna çevirir.

Oracle regresyon oracle'ıdır: girdi referans çözümde çalıştırılır, dönen değer
``assert`` olarak, fırlatılan istisna ``pytest.raises`` olarak yazılır. Her
``TestCase.code`` kendi import'larını içerir, tek başına çalıştırılabilir.
"""

from __future__ import annotations

import ast
import builtins
import math

from testzede.domain.models import TestCase
from testzede.rl.executor import GENERATOR_LIMIT, TARGET_MODULE, CallOutcome


def make_test_name(step: int) -> str:
    """Epizot içinde benzersiz test adı."""
    return f"test_step_{step:03d}"


def format_call(entry_point: str, args: tuple) -> str:
    """``f(1, [2])`` biçiminde çağrı ifadesi."""
    return f"{entry_point}({', '.join(repr(a) for a in args)})"


def consume_call(call: str) -> str:
    """Generator çağrısını oracle ile aynı biçimde tüketen ifade."""
    return f"list(islice({call}, {GENERATOR_LIMIT}))"


def parse_value(value_repr: str | None) -> tuple[bool, object]:
    """``repr`` metnini literal değere çevirir; çevrilemezse ``(False, None)``."""
    if value_repr is None:
        return False, None
    try:
        return True, ast.literal_eval(value_repr)
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return False, None


def _exception_name(exc_type: str | None) -> str:
    """Yerleşik istisnalar adıyla, diğerleri ``Exception`` olarak yakalanır."""
    name = (exc_type or "").rsplit(".", 1)[-1]
    obj = getattr(builtins, name, None)
    if isinstance(obj, type) and issubclass(obj, BaseException):
        return name
    return "Exception"


def _assertion(call: str, value_repr: str | None) -> str:
    # value_repr None: değer alınamadı (örn. çok uzun repr kesildi); "is None" yazılmaz.
    ok, value = parse_value(value_repr)
    if not ok:
        # Literal olmayan dönüş (nesne, nan, inf): yalnızca çağrının hatasız bittiği sınanır.
        return f"    {call}"
    if isinstance(value, float) and not math.isfinite(value):
        return f"    {call}"
    if isinstance(value, float):
        return f"    assert {call} == pytest.approx({value_repr})"
    if value is None or isinstance(value, bool):
        return f"    assert {call} is {value_repr}"
    return f"    assert {call} == {value_repr}"


def synthesize(
    entry_point: str,
    args: tuple,
    outcome: CallOutcome,
    step: int,
    *,
    generator: bool = False,
) -> TestCase | None:
    """Oracle sonucundan test üretir; girdi geçersizse (timeout/error) ``None`` döner.

    ``generator`` ise çağrı, oracle'daki gibi ilk ``GENERATOR_LIMIT`` öğe tüketilerek yazılır.
    """
    call = format_call(entry_point, args)
    if generator:
        call = consume_call(call)
    if outcome.status == "ok":
        body = _assertion(call, outcome.value_repr)
    elif outcome.status == "raised":
        body = f"    with pytest.raises({_exception_name(outcome.exc_type)}):\n        {call}"
    else:
        return None
    name = make_test_name(step)
    imports = "from itertools import islice\n\n" if generator else ""
    code = (
        f"{imports}import pytest\n\nfrom {TARGET_MODULE} import {entry_point}\n\n\n"
        f"def {name}():\n{body}\n"
    )
    return TestCase(name=name, code=code, origin="rl")


def output_class(outcome: CallOutcome) -> str:
    """Çıktıyı kaba bir sınıfa ayırır (ödüldeki "yeni çıktı sınıfı" terimi için).

    Sınıf türü ve işaret/boşluk bilgisini içerir: ``ok:int:-``, ``ok:list:empty``,
    ``raised:ValueError`` gibi.
    """
    if outcome.status == "raised":
        return f"raised:{(outcome.exc_type or '').rsplit('.', 1)[-1]}"
    if outcome.status != "ok":
        return outcome.status
    ok, value = parse_value(outcome.value_repr)
    if not ok:
        return "ok:object"
    kind = type(value).__name__
    if isinstance(value, bool):
        return f"ok:bool:{value}"
    if isinstance(value, int | float):
        sign = "0" if value == 0 else ("+" if value > 0 else "-")
        return f"ok:{kind}:{sign}"
    if isinstance(value, str | list | tuple | set | frozenset | dict):
        return f"ok:{kind}:{'empty' if not value else 'nonempty'}"
    return f"ok:{kind}"
