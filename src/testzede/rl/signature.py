"""Test edilen fonksiyonun parametre tiplerini çıkarır.

RL eylemleri girdi üretirken her parametrenin türünü bilmek zorundadır. Tür,
sırasıyla tip ipucundan, varsayılan değerden ve docstring örneklerinden
çıkarılır; hiçbiri yoksa ``any`` kabul edilir.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from testzede.domain.models import CodeUnit

KINDS: tuple[str, ...] = ("int", "float", "bool", "str", "list", "tuple", "set", "dict", "any")

_ALIASES = {
    "List": "list",
    "Tuple": "tuple",
    "Set": "set",
    "Dict": "dict",
    "Sequence": "list",
    "Iterable": "list",
    "Mapping": "dict",
    "Any": "any",
    "Optional": "any",
    "Union": "any",
}


@dataclass(frozen=True)
class TypeSpec:
    """Bir parametrenin türü. ``args`` öğe türleridir (list[int] → (int,))."""

    kind: str
    args: tuple[TypeSpec, ...] = ()


ANY = TypeSpec("any")


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: TypeSpec


class SignatureError(ValueError):
    """Giriş fonksiyonu bulunamadı ya da kaynak ayrıştırılamadı."""


def extract_params(unit: CodeUnit) -> tuple[ParamSpec, ...]:
    """``unit.entry_point`` fonksiyonunun parametrelerini türleriyle döndürür.

    Raises:
        SignatureError: Kaynak geçersizse ya da giriş fonksiyonu yoksa.
    """
    if not unit.entry_point:
        raise SignatureError(f"{unit.uid}: entry_point tanımlı değil")
    try:
        tree = ast.parse(unit.source)
    except SyntaxError as exc:
        raise SignatureError(f"Kod ayrıştırılamadı (satır {exc.lineno}): {exc.msg}") from exc

    func = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name == unit.entry_point
        ),
        None,
    )
    if func is None:
        raise SignatureError(f"{unit.uid}: '{unit.entry_point}' fonksiyonu bulunamadı")

    args = [*func.args.posonlyargs, *func.args.args]
    if args and args[0].arg in ("self", "cls"):
        args = args[1:]
    defaults = [None] * (len(args) - len(func.args.defaults)) + list(func.args.defaults)
    examples = parse_seed_inputs(unit)

    params = []
    for index, (arg, default) in enumerate(zip(args, defaults, strict=True)):
        spec = _from_annotation(arg.annotation) if arg.annotation else ANY
        if spec == ANY and default is not None:
            spec = _from_value(_literal(default))
        if spec == ANY:
            values = [ex[index] for ex in examples if len(ex) > index]
            if values:
                spec = _from_value(values[0])
        params.append(ParamSpec(arg.arg, spec))
    return tuple(params)


# ``>>> list(f(1))`` gibi sonucu tüketen sarmalayıcılar (generator örneklerinde yaygın).
_SEED_WRAPPERS = frozenset({"list", "tuple", "set", "sorted", "next"})


def _entry_function(tree: ast.Module, entry_point: str | None) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == entry_point:
            return node
    return None


def is_generator(unit: CodeUnit) -> bool:
    """Giriş fonksiyonu generator mı (gövdesinde, iç fonksiyonlar hariç ``yield`` var mı)."""
    try:
        func = _entry_function(ast.parse(unit.source), unit.entry_point)
    except (SyntaxError, ValueError):
        return False
    if func is None:
        return False
    stack: list[ast.AST] = list(func.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Yield | ast.YieldFrom):
            return True
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | ast.ClassDef):
            continue  # iç tanımın yield'i dış fonksiyonu generator yapmaz
        stack.extend(ast.iter_child_nodes(node))
    return False


def parse_seed_inputs(unit: CodeUnit) -> tuple[tuple, ...]:
    """``>>> f(1, [2])`` biçimindeki docstring örneklerinden argüman demetleri çıkarır.

    ``list(f(1))`` gibi tek argümanlı tüketici sarmalayıcılar açılır. Literal olmayan
    argüman içeren ya da başka bir fonksiyonu çağıran örnekler atlanır.
    """
    inputs = []
    for example in unit.seed_examples:
        text = example.strip().removeprefix(">>>").strip()
        try:
            node = ast.parse(text, mode="eval").body
        except SyntaxError:
            continue
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _SEED_WRAPPERS
            and node.func.id != unit.entry_point
            and len(node.args) == 1
            and not node.keywords
            and isinstance(node.args[0], ast.Call)
        ):
            node = node.args[0]
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == unit.entry_point
            and not node.keywords
        ):
            continue
        try:
            inputs.append(tuple(ast.literal_eval(arg) for arg in node.args))
        except ValueError:
            continue
    return tuple(inputs)


def _from_annotation(node: ast.expr) -> TypeSpec:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            node = ast.parse(node.value, mode="eval").body
        except SyntaxError:
            return ANY
    if isinstance(node, ast.Name):
        name = _ALIASES.get(node.id, node.id)
        return TypeSpec(name) if name in KINDS else ANY
    if isinstance(node, ast.Attribute):  # typing.List
        return _from_annotation(ast.Name(node.attr))
    if isinstance(node, ast.Subscript):
        outer = _from_annotation(node.value)
        if outer.kind not in ("list", "tuple", "set", "dict"):
            return ANY
        inner = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        args = tuple(_from_annotation(e) for e in inner if not isinstance(e, ast.Constant))
        return TypeSpec(outer.kind, args)
    return ANY


def _literal(node: ast.expr) -> object:
    try:
        return ast.literal_eval(node)
    except ValueError:
        return None


def _from_value(value: object) -> TypeSpec:
    if value is None:
        return ANY
    kind = type(value).__name__
    if kind not in KINDS:
        return ANY
    if isinstance(value, list | tuple | set) and value:
        return TypeSpec(kind, (_from_value(next(iter(value))),))
    if isinstance(value, dict) and value:
        key, val = next(iter(value.items()))
        return TypeSpec(kind, (_from_value(key), _from_value(val)))
    return TypeSpec(kind)
