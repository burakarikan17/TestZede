"""Ham kaynak metninden doğrulanmış ``CodeUnit`` üretir."""

from __future__ import annotations

import ast

from testzede.datasets.base import EMPTY_SOURCE, NO_ENTRY_POINT, SYNTAX_ERROR, SkippedUnit
from testzede.datasets.docstring import doctest_examples
from testzede.datasets.parsing import quiet_warnings
from testzede.domain.models import CodeUnit


def make_unit(
    uid: str, dataset: str, source: str, entry_point: str | None = None
) -> CodeUnit | SkippedUnit:
    """Kaynağı doğrular ve ``CodeUnit`` üretir; olmuyorsa nedenini döndürür.

    Args:
        entry_point: Test edilecek fonksiyon. ``None`` ise kaynaktaki ilk üst düzey
            fonksiyon seçilir.

    Returns:
        ``CodeUnit``; kaynak boşsa, ayrıştırılamıyorsa ya da fonksiyon yoksa
        neden koduyla ``SkippedUnit``.
    """
    if not source.strip():
        return SkippedUnit(uid, EMPTY_SOURCE)
    try:
        with quiet_warnings():
            tree = ast.parse(source)
    except SyntaxError as exc:
        return SkippedUnit(uid, SYNTAX_ERROR, f"satır {exc.lineno}: {exc.msg}")
    except (ValueError, RecursionError, MemoryError) as exc:
        return SkippedUnit(uid, SYNTAX_ERROR, str(exc))

    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    node = next((f for f in functions if entry_point in (None, f.name)), None)
    if node is None:
        detail = f"'{entry_point}' fonksiyonu yok" if entry_point else "fonksiyon yok"
        return SkippedUnit(uid, NO_ENTRY_POINT, detail)
    return CodeUnit(
        uid=uid,
        source=source,
        entry_point=node.name,
        dataset=dataset,
        seed_examples=doctest_examples(ast.get_docstring(node)),
    )
