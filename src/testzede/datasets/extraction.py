"""Gerçek bir Python dosyasından bağımsız çalışabilen fonksiyon birimleri çıkarır.

TestGenEval kaynakları repo dosyalarıdır (django, astropy …). Dosyanın tamamı
tek başına çalışmaz, ama içindeki birçok fonksiyon yalnızca yerleşik (builtin) ve
standart kütüphane öğelerine dayanır. Bu modül böyle fonksiyonları, ihtiyaç duydukları
import'lar, sabitler ve yardımcı fonksiyonlarla birlikte tek başına çalışan bir
kaynak metnine çevirir.

Bir fonksiyon şu durumlarda **reddedilir** (neden koduyla sayılır):
    * özel (``_`` ile başlayan), ``async``, dekoratörlü, parametresiz,
    * ``global`` ifadesi kullanan ya da modül düzeyinde yeniden tanımlanan,
    * dosya sistemi / ağ / süreç / rastgelelik gibi yan etkili ya da kararsız
      modüllere ve yerleşiklere (``open``, ``input`` …) dayanan,
    * repo içi, üçüncü parti ya da çözümlenemeyen bir isme dayanan.

Serbest (global) isimlerin tespiti ``symtable`` ile yapılır; bu, kapsam kurallarını
yorumlayıcının kendisiyle aynı şekilde uygular.
"""

from __future__ import annotations

import ast
import builtins
import symtable
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from testzede.datasets.parsing import quiet_warnings

NOT_PUBLIC = "not_public"
NO_PARAMETERS = "no_parameters"
ASYNC_FUNCTION = "async_function"
DECORATED = "decorated"
REDEFINED = "redefined"
GLOBAL_STATEMENT = "global_statement"
UNSAFE_BUILTIN = "unsafe_builtin"
SIDE_EFFECT_DEPENDENCY = "side_effect_dependency"
EXTERNAL_DEPENDENCY = "external_dependency"
HELPER_REJECTED = "helper_rejected"
SOURCE_UNAVAILABLE = "source_unavailable"

_STDLIB = frozenset(sys.stdlib_module_names)
_BUILTINS = frozenset(dir(builtins))

# Dosya sistemi, ağ, süreç, eşzamanlılık, rastgelelik ve zaman gibi yan etkili ya da
# her çalıştırmada farklı sonuç veren modüller: regresyon oracle'ı bunlarla anlamsızlaşır.
_SIDE_EFFECT_MODULES = frozenset(
    {
        "asyncio",
        "concurrent",
        "ctypes",
        "fileinput",
        "ftplib",
        "gc",
        "getpass",
        "glob",
        "http",
        "importlib",
        "logging",
        "multiprocessing",
        "os",
        "pathlib",
        "pickle",
        "platform",
        "random",
        "secrets",
        "shelve",
        "shutil",
        "signal",
        "smtplib",
        "socket",
        "sqlite3",
        "ssl",
        "subprocess",
        "sys",
        "tempfile",
        "threading",
        "time",
        "urllib",
        "uuid",
        "warnings",
        "webbrowser",
    }
)

# Etkileşimli, dosya sistemi, dinamik kod ya da süreç başına değişen sonuç veren yerleşikler.
_UNSAFE_BUILTINS = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "eval",
        "exec",
        "exit",
        "globals",
        "hash",
        "help",
        "id",
        "input",
        "locals",
        "open",
        "quit",
        "vars",
    }
)


class ExtractionError(ValueError):
    """Kaynak ayrıştırılamadığı için fonksiyon çıkarılamadı."""


@dataclass(frozen=True)
class ExtractedFunction:
    """Tek başına çalışan bir fonksiyon birimi."""

    name: str
    source: str  # import'lar + sabitler + yardımcılar + fonksiyon
    docstring: str | None


@dataclass(frozen=True)
class ExtractionResult:
    """Bir dosyadan çıkarılan birimler ve reddedilen fonksiyonların neden sayıları."""

    functions: tuple[ExtractedFunction, ...]
    rejected: Mapping[str, int] = field(default_factory=dict)


def extract_functions(source: str) -> ExtractionResult:
    """Dosyadaki bağımsız çalışabilen üst düzey fonksiyonları çıkarır.

    Raises:
        ExtractionError: Kaynak ayrıştırılamıyorsa (söz dizimi hatası vb.).
    """
    try:
        with quiet_warnings():
            tree = ast.parse(source)
            table = symtable.symtable(source, "<unit>", "exec")
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        raise ExtractionError(str(exc)) from exc
    return _ModuleAnalysis(source, tree, table).extract()


@dataclass(frozen=True)
class _Needs:
    """Bir fonksiyonun doğrudan ihtiyaçları (modül düzeyindeki isimler)."""

    imports: frozenset[str] = frozenset()
    constants: frozenset[str] = frozenset()
    helpers: frozenset[str] = frozenset()


def _root(module: str | None) -> str:
    return (module or "").split(".")[0]


def _is_immutable_literal(node: ast.expr) -> bool:
    """Değiştirilemez sabit: sayı, metin, bool, None ya da bunların demeti."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        return isinstance(node.operand, ast.Constant)
    if isinstance(node, ast.Tuple):
        return all(_is_immutable_literal(item) for item in node.elts)
    return False


def _stored_names(node: ast.AST) -> set[str]:
    return {
        n.id
        for n in ast.walk(node)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store | ast.Del)
    }


class _ModuleAnalysis:
    """Bir modülün üst düzey tanımlarını indeksler ve bağımsız fonksiyonları çıkarır."""

    def __init__(self, source: str, tree: ast.Module, table: symtable.SymbolTable) -> None:
        self._source = source
        self._table = table
        self._imports: dict[str, ast.stmt] = {}
        self._constants: dict[str, ast.stmt] = {}
        self._functions: dict[str, ast.FunctionDef] = {}
        self._blocked: dict[str, str] = {}  # kullanılamayan modül düzeyi isimler → neden
        self._pre_rejected: Counter[str] = Counter()  # indekslenirken elenen fonksiyonlar
        self._tables = {
            (child.get_name(), child.get_lineno()): child
            for child in table.get_children()
            if child.get_type() == "function"
        }
        self._index(tree)

    # ---- indeksleme -------------------------------------------------------------

    def _index(self, tree: ast.Module) -> None:
        for stmt in tree.body:
            if isinstance(stmt, ast.Import):
                self._index_import(stmt)
            elif isinstance(stmt, ast.ImportFrom):
                self._index_import_from(stmt)
            elif isinstance(stmt, ast.Assign | ast.AnnAssign):
                self._index_assignment(stmt)
            elif isinstance(stmt, ast.FunctionDef):
                self._define(stmt.name, self._functions, stmt)
            elif isinstance(stmt, ast.AsyncFunctionDef):
                self._pre_rejected[ASYNC_FUNCTION] += 1
                self._block(stmt.name, ASYNC_FUNCTION)
            elif isinstance(stmt, ast.ClassDef):
                self._block(stmt.name, EXTERNAL_DEPENDENCY)
            else:
                self._rebind(_stored_names(stmt))
        # if/try/with gibi bloklarda bağlanan her isim güvenilmezdir.
        for symbol in self._table.get_symbols():
            name = symbol.get_name()
            bound = symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()
            if bound and not self._known(name):
                self._block(name, EXTERNAL_DEPENDENCY)

    def _known(self, name: str) -> bool:
        return (
            name in self._imports
            or name in self._constants
            or name in self._functions
            or name in self._blocked
        )

    def _define(self, name: str, bucket: dict, node: ast.stmt) -> None:
        """Adı kaydeder; ikinci kez bağlanıyorsa yeniden tanımlanmış sayıp engeller."""
        if self._known(name):
            self._block(name, REDEFINED)
        else:
            bucket[name] = node

    def _block(self, name: str, reason: str) -> None:
        self._imports.pop(name, None)
        self._constants.pop(name, None)
        if self._functions.pop(name, None) is not None:
            self._pre_rejected[reason] += 1
        self._blocked.setdefault(name, reason)

    def _rebind(self, names: Iterable[str]) -> None:
        for name in names:
            if self._known(name):
                self._block(name, REDEFINED)

    def _index_import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name.split(".")[0]
            reason = self._module_reason(_root(alias.name))
            if reason:
                self._block(bound, reason)
            else:
                single = ast.copy_location(ast.Import(names=[alias]), node)
                self._define(bound, self._imports, single)

    def _index_import_from(self, node: ast.ImportFrom) -> None:
        if node.module == "__future__":
            return
        for alias in node.names:
            if alias.name == "*":
                continue
            bound = alias.asname or alias.name
            reason = EXTERNAL_DEPENDENCY if node.level else self._module_reason(_root(node.module))
            if reason:
                self._block(bound, reason)
            else:
                single = ast.copy_location(
                    ast.ImportFrom(module=node.module, names=[alias], level=0), node
                )
                self._define(bound, self._imports, single)

    def _index_assignment(self, node: ast.Assign | ast.AnnAssign) -> None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        simple = (
            len(targets) == 1
            and isinstance(targets[0], ast.Name)
            and value is not None
            and _is_immutable_literal(value)
        )
        if simple:
            self._define(targets[0].id, self._constants, node)
            return
        for name in _stored_names(node):
            self._block(name, EXTERNAL_DEPENDENCY)

    @staticmethod
    def _module_reason(root: str) -> str | None:
        """İçe aktarılan modül kullanılamazsa nedenini döndürür."""
        if root in _SIDE_EFFECT_MODULES:
            return SIDE_EFFECT_DEPENDENCY
        if root not in _STDLIB:
            return EXTERNAL_DEPENDENCY
        return None

    # ---- bağımlılık analizi ----------------------------------------------------

    @staticmethod
    def _collect_globals(table: symtable.SymbolTable, names: set[str]) -> bool:
        """Serbest (global) isimleri toplar; ``global`` ifadesi varsa ``True`` döner."""
        declared = False
        for symbol in table.get_symbols():
            declared = declared or symbol.is_declared_global()
            if symbol.is_global() and symbol.is_referenced():
                names.add(symbol.get_name())
        for child in table.get_children():
            declared = _ModuleAnalysis._collect_globals(child, names) or declared
        return declared

    @staticmethod
    def _signature_names(node: ast.FunctionDef) -> set[str]:
        """Tanım anında değerlendirilen isimler: varsayılan değerler ve tür ipuçları."""
        args = node.args
        every_arg = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        every_arg += [a for a in (args.vararg, args.kwarg) if a is not None]
        parts: list[ast.expr] = [*args.defaults, *(d for d in args.kw_defaults if d is not None)]
        parts += [a.annotation for a in every_arg if a.annotation is not None]
        if node.returns is not None:
            parts.append(node.returns)
        return {
            n.id
            for part in parts
            for n in ast.walk(part)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
        }

    def _nested_import_reason(self, node: ast.FunctionDef) -> str | None:
        for inner in ast.walk(node):
            if isinstance(inner, ast.Import):
                roots = [_root(alias.name) for alias in inner.names]
            elif isinstance(inner, ast.ImportFrom):
                roots = [_root(inner.module)] if not inner.level else [""]
            else:
                continue
            for root in roots:
                reason = self._module_reason(root)
                if reason:
                    return reason
        return None

    def _direct(self, node: ast.FunctionDef) -> tuple[_Needs | None, str | None]:
        """Fonksiyonun doğrudan ihtiyaçlarını ya da reddedilme nedenini döndürür."""
        if node.decorator_list:
            return None, DECORATED
        table = self._tables.get((node.name, node.lineno))
        if table is None:
            return None, SOURCE_UNAVAILABLE
        names: set[str] = set()
        if self._collect_globals(table, names):
            return None, GLOBAL_STATEMENT
        nested = self._nested_import_reason(node)
        if nested:
            return None, nested
        names |= self._signature_names(node)

        imports, constants, helpers = set(), set(), set()
        for name in sorted(names):
            if name in self._blocked:
                return None, self._blocked[name]
            if name in self._imports:
                imports.add(name)
            elif name in self._constants:
                constants.add(name)
            elif name in self._functions:
                helpers.add(name)
            elif name in _UNSAFE_BUILTINS:
                return None, UNSAFE_BUILTIN
            elif name not in _BUILTINS:
                return None, EXTERNAL_DEPENDENCY
        return _Needs(frozenset(imports), frozenset(constants), frozenset(helpers)), None

    def _usable_functions(self, direct: Mapping[str, _Needs | None]) -> set[str]:
        """Doğrudan uygun olup yardımcılarının da uygun olduğu fonksiyonlar (sabit nokta)."""
        usable = {name for name, needs in direct.items() if needs is not None}
        changed = True
        while changed:
            changed = False
            for name in sorted(usable):
                needs = direct[name]
                if needs is not None and not needs.helpers <= usable:
                    usable.discard(name)
                    changed = True
        return usable

    def _closure(self, name: str, direct: Mapping[str, _Needs | None]) -> set[str]:
        """``name`` ve ona (dolaylı) bağlı yardımcı fonksiyonların kümesi."""
        seen: set[str] = set()
        stack = [name]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            needs = direct[current]
            stack.extend(needs.helpers if needs else ())
        return seen

    # ---- çıkarma ----------------------------------------------------------------

    def extract(self) -> ExtractionResult:
        direct: dict[str, _Needs | None] = {}
        reasons: dict[str, str] = {}
        for name, node in self._functions.items():
            needs, reason = self._direct(node)
            direct[name] = needs
            if reason:
                reasons[name] = reason
        usable = self._usable_functions(direct)

        rejected: Counter[str] = Counter(self._pre_rejected)
        functions: list[ExtractedFunction] = []
        for name, node in sorted(self._functions.items(), key=lambda item: item[1].lineno):
            reason = self._target_reason(name, node, usable, reasons)
            if reason:
                rejected[reason] += 1
                continue
            built = self._build(node, self._closure(name, direct), direct)
            if built is None:
                rejected[SOURCE_UNAVAILABLE] += 1
            else:
                functions.append(ExtractedFunction(name, built, ast.get_docstring(node)))
        return ExtractionResult(tuple(functions), dict(rejected))

    @staticmethod
    def _target_reason(
        name: str, node: ast.FunctionDef, usable: set[str], reasons: Mapping[str, str]
    ) -> str | None:
        if name.startswith("_"):
            return NOT_PUBLIC
        args = node.args
        if not (args.posonlyargs or args.args or args.kwonlyargs or args.vararg):
            return NO_PARAMETERS
        if name in usable:
            return None
        return reasons.get(name, HELPER_REJECTED)

    def _segment(self, node: ast.stmt) -> str | None:
        if isinstance(node, ast.Import | ast.ImportFrom):
            return ast.unparse(node)
        if isinstance(node, ast.AnnAssign):
            # ``LIMIT: Final = 3`` → ``LIMIT = 3``: anotasyon çalışma anında değerlendirilir
            # ve ``Final`` gibi isimlerin import'unu gerektirir; sabit için gereksizdir.
            plain = ast.Assign(targets=[node.target], value=node.value, type_comment=None)
            return ast.unparse(ast.copy_location(plain, node))
        return ast.get_source_segment(self._source, node)

    def _build(
        self, target: ast.FunctionDef, names: set[str], direct: Mapping[str, _Needs | None]
    ) -> str | None:
        """Hedef ve yardımcılarından tek başına çalışan kaynak metnini kurar."""
        imports: set[str] = set()
        constants: set[str] = set()
        for name in names:
            needs = direct[name]
            if needs is not None:
                imports |= needs.imports
                constants |= needs.constants

        def ordered(wanted: Iterable[str], mapping: Mapping[str, ast.stmt]) -> list[ast.stmt]:
            # (satır, ad) sırası: küme yineleme sırasından bağımsız, tekrarlanabilir çıktı.
            return [mapping[n] for n in sorted(wanted, key=lambda n: (mapping[n].lineno, n))]

        sections: list[list[ast.stmt]] = [
            ordered(imports, self._imports),
            ordered(constants, self._constants),
            ordered(names, self._functions),
        ]
        texts: list[str] = []
        for index, nodes in enumerate(sections):
            segments = [self._segment(n) for n in nodes]
            if any(seg is None for seg in segments):
                return None
            if segments:
                separator = "\n\n\n" if index == 2 else "\n"
                texts.append(separator.join(seg for seg in segments if seg))
        result = "\n\n".join(texts) + "\n"
        try:
            with quiet_warnings():
                compile(result, "<unit>", "exec")
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            return None
        return result
