"""Docstring'lerdeki ``>>>`` örneklerini çıkarır (``CodeUnit.seed_examples``)."""

from __future__ import annotations

import doctest


def doctest_examples(docstring: str | None) -> tuple[str, ...]:
    """Docstring'deki doctest örneklerini ``">>> f(1, 2)"`` biçiminde döndürür.

    Beklenen çıktı satırları atılır; yalnızca çağrı ifadeleri tutulur. Biçimi bozuk
    docstring boş sonuç verir.
    """
    if not docstring:
        return ()
    try:
        examples = doctest.DocTestParser().get_examples(docstring)
    except ValueError:  # bozuk doctest biçimi (örn. hatalı girinti)
        return ()
    return tuple(f">>> {example.source.strip()}" for example in examples if example.source.strip())
