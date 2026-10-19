"""Analiz modüllerinin ortak kaynak ayrıştırıcısı."""

from __future__ import annotations

import ast
import warnings
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def quiet_warnings() -> Iterator[None]:
    """Kullanıcı kodunun ayrıştırma/analiz uyarılarını (geçersiz kaçış dizisi vb.) bastırır."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


class SourceError(ValueError):
    """Kaynak geçerli Python kodu değil; mesaj kullanıcıya gösterilebilir."""


def parse_python(source: str) -> ast.Module:
    """Kaynağı ``ast.parse`` ile ayrıştırır.

    Uyarılar bastırılır (bkz. :func:`quiet_warnings`). Söz dizimi hatası
    kadar null bayt, aşırı iç içe yapı ve bellek hataları da ``SourceError`` olur (satır
    numarası biliniyorsa mesajda yazar).

    Raises:
        SourceError: Kaynak ayrıştırılamıyorsa.
    """
    try:
        with quiet_warnings():
            return ast.parse(source)
    except SyntaxError as exc:
        where = f" (satır {exc.lineno})" if exc.lineno else ""
        raise SourceError(f"Kod ayrıştırılamadı{where}: {exc.msg}") from exc
    except (ValueError, RecursionError, MemoryError) as exc:
        raise SourceError(f"Kod ayrıştırılamadı: {exc}") from exc
