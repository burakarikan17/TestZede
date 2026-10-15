"""Python kaynak kodundan çağrı grafiği (call graph) çıkarır (US-1).

Grafik ``ast`` ile üretilir ve ``networkx.DiGraph`` olarak döndürülür; çizim
GUI katmanında matplotlib ile yapılır.
"""

from __future__ import annotations

import ast
import builtins

import networkx as nx

MODULE_NODE = "<module>"
BUILTIN_PREFIX = "<builtin>."
EXTERNAL_PREFIX = "<external>."

_BUILTIN_NAMES = frozenset(dir(builtins))


class CallGraphError(ValueError):
    """Kaynak kod ayrıştırılamadığı için çağrı grafiği çıkarılamadı."""


def build_call_graph(source: str) -> nx.DiGraph:
    """Kaynak koddaki fonksiyon çağrılarından yönlü graf üretir.

    Düğümler:
        * Tanımlı fonksiyonlar: ``f`` ya da ``Sinif.metot`` (``kind="function"``).
        * Builtin çağrılar: ``<builtin>.len`` (``kind="builtin"``).
        * Diğer çağrılar (import edilen vb.): ``<external>.math.sqrt``
          (``kind="external"``).
        * Fonksiyon dışındaki çağrıların kaynağı: ``<module>`` (``kind="module"``).

    Kenar ``a -> b``, ``a`` içinde ``b`` çağrıldığını gösterir. Özyineleme
    kendi üzerine kenar olarak görünür.

    Raises:
        CallGraphError: Kaynak geçerli Python söz dizimi değilse.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise CallGraphError(f"Kod ayrıştırılamadı (satır {exc.lineno}): {exc.msg}") from exc

    definitions = _DefinitionCollector()
    definitions.visit(tree)

    graph = nx.DiGraph()
    for name in definitions.names:
        graph.add_node(name, kind="function")

    _CallCollector(graph, definitions.names).visit(tree)
    return graph


class _DefinitionCollector(ast.NodeVisitor):
    """Tanımlı fonksiyon ve metotların nitelikli adlarını toplar."""

    def __init__(self) -> None:
        self.names: list[str] = []
        self._scope: list[str] = []

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._scope.append(node.name)
        self.names.append(".".join(self._scope))
        self.generic_visit(node)
        self._scope.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()


class _CallCollector(ast.NodeVisitor):
    """Çağrıları bulur ve çağıran → çağrılan kenarlarını grafa ekler."""

    def __init__(self, graph: nx.DiGraph, defined: list[str]) -> None:
        self._graph = graph
        self._defined = set(defined)
        # Kapsam yığını: (ad, fonksiyon_mu). Sınıflar fonksiyon kapsamı sayılmaz.
        self._scope: list[tuple[str, bool]] = []

    def _qualname(self, depth: int) -> str:
        return ".".join(name for name, _ in self._scope[:depth])

    def _caller(self) -> str:
        for depth in range(len(self._scope), 0, -1):
            if self._scope[depth - 1][1]:
                return self._qualname(depth)
        return MODULE_NODE

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._scope.append((node.name, True))
        self.generic_visit(node)
        self._scope.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope.append((node.name, False))
        self.generic_visit(node)
        self._scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        callee, kind = self._resolve(node.func)
        if callee is not None and kind is not None:
            caller = self._caller()
            if caller == MODULE_NODE and not self._graph.has_node(MODULE_NODE):
                self._graph.add_node(MODULE_NODE, kind="module")
            if not self._graph.has_node(callee):
                self._graph.add_node(callee, kind=kind)
            self._graph.add_edge(caller, callee)
        self.generic_visit(node)

    def _resolve(self, func: ast.expr) -> tuple[str | None, str | None]:
        """Çağrılan ifadeyi (düğüm adı, tür) ikilisine çevirir."""
        if isinstance(func, ast.Name):
            return self._resolve_name(func.id)
        if isinstance(func, ast.Attribute):
            dotted = _dotted_name(func)
            if dotted is None:
                return None, None  # örn. f().g() ya da "x".join()
            head, _, rest = dotted.partition(".")
            if head in ("self", "cls"):
                method = self._resolve_method(rest)
                if method is not None:
                    return method, "function"
            return EXTERNAL_PREFIX + dotted, "external"
        return None, None  # örn. (lambda: 0)() ya da f()()

    def _resolve_name(self, name: str) -> tuple[str, str]:
        # İçten dışa doğru fonksiyon kapsamlarında, sonra modül düzeyinde ara.
        prefixes = [
            self._qualname(depth)
            for depth in range(len(self._scope), 0, -1)
            if self._scope[depth - 1][1]
        ]
        for prefix in [*prefixes, ""]:
            candidate = f"{prefix}.{name}" if prefix else name
            if candidate in self._defined:
                return candidate, "function"
        if name in _BUILTIN_NAMES:
            return BUILTIN_PREFIX + name, "builtin"
        return EXTERNAL_PREFIX + name, "external"

    def _resolve_method(self, method: str) -> str | None:
        """``self.metot()`` çağrısını içinde bulunulan sınıfın metoduna bağlar."""
        class_depths = [i + 1 for i, (_, is_func) in enumerate(self._scope) if not is_func]
        if not class_depths or "." in method:
            return None
        candidate = f"{self._qualname(class_depths[-1])}.{method}"
        return candidate if candidate in self._defined else None


def _dotted_name(node: ast.expr) -> str | None:
    """``a.b.c`` biçimindeki ifadeyi ``"a.b.c"`` yapar; başka ifadeler için None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))
