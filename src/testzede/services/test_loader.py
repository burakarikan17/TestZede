"""Kullanıcının yazdığı pytest kodunu ``TestCase`` listesine çevirir (GUI'den bağımsız)."""

from __future__ import annotations

import ast

from testzede.domain.models import TestCase
from testzede.execution.sandbox import TARGET_MODULE


def _rewrite_imports(tree: ast.Module, module_name: str) -> None:
    """``module_name`` içe aktarmalarını ``target`` modülüne yönlendirir (yerinde)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module_name:
                    alias.asname = alias.asname or module_name
                    alias.name = TARGET_MODULE
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == module_name:
            node.module = TARGET_MODULE


def _is_test(node: ast.stmt) -> bool:
    """Üst düzey ``def test_*`` ya da ``class Test*`` mi?"""
    if isinstance(node, ast.FunctionDef):
        return node.name.startswith("test_")
    return isinstance(node, ast.ClassDef) and node.name.startswith("Test")


def _unique(name: str, used: set[str]) -> str:
    """Kullanılmış adlara ``_2``, ``_3`` ... ekleyerek benzersiz ad üretir."""
    if name not in used:
        return name
    n = 2
    while f"{name}_{n}" in used:
        n += 1
    return f"{name}_{n}"


def load_tests(test_source: str, module_name: str | None = None) -> list[TestCase]:
    """Test kodunu ayrıştırır; her üst düzey test fonksiyonu/sınıfı bir ``TestCase`` olur.

    Test olmayan üst düzey düğümler (import, yardımcı, fixture, sabit) her testin başına
    eklenir. ``module_name`` verilirse o modülün import'ları ``target``'a yönlendirilir.
    Geçersiz kod ya da test yoksa ``ValueError`` fırlatır.
    """
    if not test_source.strip():
        raise ValueError("Test kodu boş.")
    try:
        tree = ast.parse(test_source)
    except SyntaxError as exc:
        where = f"Satır {exc.lineno}: " if exc.lineno else ""
        raise ValueError(f"{where}{exc.msg}") from exc
    except ValueError as exc:  # örn. null bayt
        raise ValueError(f"Test kodu geçerli değil: {exc}") from exc

    if module_name:
        _rewrite_imports(tree, module_name)
    tests = [node for node in tree.body if _is_test(node)]
    if not tests:
        raise ValueError(
            "Test fonksiyonu bulunamadı. 'test_' ile başlayan bir fonksiyon "
            "veya 'Test' ile başlayan bir sınıf yazın."
        )
    preamble = "\n".join(ast.unparse(node) for node in tree.body if not _is_test(node))

    cases: list[TestCase] = []
    used: set[str] = set()
    for node in tests:
        name = _unique(node.name, used)
        used.add(name)
        body = ast.unparse(node)
        code = f"{preamble}\n\n\n{body}" if preamble else body
        cases.append(TestCase(name=name, code=code, origin="user"))
    return cases
