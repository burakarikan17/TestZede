"""Veri seti kaynaklarını ayrıştırırken ortak yardımcı."""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def quiet_warnings() -> Iterator[None]:
    """Ayrıştırma/derleme uyarılarını bastırır.

    Gerçek repo dosyaları ``"\\d"`` gibi geçersiz kaçış dizileri içerir; bu, veri setinin
    özelliğidir ve her yüklemede terminali doldurmamalıdır.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield
