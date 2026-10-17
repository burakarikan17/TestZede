"""AST tabanlı mutasyon operatörleri (Strategy kalıbı)."""

from __future__ import annotations

import ast
import copy
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Mutant:
    """Tek bir değişiklik içeren mutant kaynak kodu."""

    operator: str
    line: int
    description: str
    source: str


class MutationOperator(ABC):
    """Mutasyon operatörü arayüzü."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Operatörün kısa adı (örn. ``AOR``)."""

    @abstractmethod
    def generate(self, source: str) -> list[Mutant]:
        """Her mutasyon noktası için ayrı bir mutant üretir.

        Geçersiz Python kodunda ``ValueError`` fırlatır.
        """


@dataclass(frozen=True)
class _Site:
    """Bir mutasyon noktası: konum ve değişikliği ağaçta yapan geri çağrı."""

    node: ast.AST
    apply: Callable[[], str]  # ağacı yerinde değiştirir, açıklamayı döndürür


def _parse(source: str) -> ast.Module:
    """Kaynağı ayrıştırır; geçersizse ``ValueError`` fırlatır."""
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"Geçersiz Python kodu: {exc}") from exc


class _SiteOperator(MutationOperator):
    """Mutasyon noktalarını bulan, her biri için ağacı kopyalayıp değiştiren taban sınıf."""

    @abstractmethod
    def _sites(self, tree: ast.Module) -> list[_Site]:
        """Ağaçtaki mutasyon noktalarını (satır, sütun sırasıyla) döndürür."""

    def generate(self, source: str) -> list[Mutant]:
        """Her nokta için orijinal ağacın kopyasında tek değişiklik yapar."""
        tree = _parse(source)
        seen = {ast.unparse(tree)}  # orijinalle aynı çıkanlar ve tekrarlar atlanır
        mutants: list[Mutant] = []
        for index in range(len(self._sites(tree))):
            clone = copy.deepcopy(tree)
            site = self._sites(clone)[index]
            line = getattr(site.node, "lineno", 0)
            description = site.apply()
            mutated = ast.unparse(clone)
            if mutated in seen:
                continue
            seen.add(mutated)
            mutants.append(Mutant(self.name, line, description, mutated))
        return mutants


def _ordered(sites: list[_Site]) -> list[_Site]:
    """Noktaları kaynak konumuna göre sıralar (eşitlikte ağaç sırası korunur)."""
    return sorted(
        sites,
        key=lambda s: (getattr(s.node, "lineno", 0), getattr(s.node, "col_offset", 0)),
    )


_AOR_SWAP: dict[type[ast.operator], type[ast.operator]] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Div,
    ast.Div: ast.Mult,
}
_ROR_SWAP: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
}
_SYMBOL: dict[type[ast.AST], str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.And: "and",
    ast.Or: "or",
}


class AOR(_SiteOperator):
    """Aritmetik operatör değiştirme: ``+``↔``-``, ``*``↔``/``."""

    name = "AOR"

    def _sites(self, tree: ast.Module) -> list[_Site]:
        sites = []
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and type(node.op) in _AOR_SWAP:

                def apply(node: ast.BinOp = node) -> str:
                    old = type(node.op)
                    node.op = _AOR_SWAP[old]()
                    return f"{_SYMBOL[old]} -> {_SYMBOL[type(node.op)]}"

                sites.append(_Site(node, apply))
        return _ordered(sites)


class ROR(_SiteOperator):
    """İlişkisel operatör değiştirme: ``<``→``<=``, ``>``→``>=``, ``==``↔``!=`` vb."""

    name = "ROR"

    def _sites(self, tree: ast.Module) -> list[_Site]:
        sites = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            for i, op in enumerate(node.ops):
                if type(op) in _ROR_SWAP:

                    def apply(node: ast.Compare = node, i: int = i) -> str:
                        old = type(node.ops[i])
                        node.ops[i] = _ROR_SWAP[old]()
                        return f"{_SYMBOL[old]} -> {_SYMBOL[type(node.ops[i])]}"

                    sites.append(_Site(node, apply))
        return _ordered(sites)


class COR(_SiteOperator):
    """Mantıksal operatör değiştirme: ``and``↔``or``."""

    name = "COR"

    def _sites(self, tree: ast.Module) -> list[_Site]:
        sites = []
        for node in ast.walk(tree):
            if isinstance(node, ast.BoolOp):

                def apply(node: ast.BoolOp = node) -> str:
                    old = type(node.op)
                    node.op = ast.Or() if old is ast.And else ast.And()
                    return f"{_SYMBOL[old]} -> {_SYMBOL[type(node.op)]}"

                sites.append(_Site(node, apply))
        return _ordered(sites)


class ConstantReplacement(_SiteOperator):
    """Sabit değiştirme: int ``0``↔``1`` ve ``True``↔``False``."""

    name = "CONST"

    def _sites(self, tree: ast.Module) -> list[_Site]:
        sites = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            # bool, int'in alt sınıfıdır: tür karşılaştırması tam eşitlikle yapılır.
            if type(node.value) is bool:
                new: object = not node.value
            elif type(node.value) is int and node.value in (0, 1):
                new = 1 - node.value
            else:
                continue

            def apply(node: ast.Constant = node, new: object = new) -> str:
                old = node.value
                node.value = new
                return f"{old!r} -> {new!r}"

            sites.append(_Site(node, apply))
        return _ordered(sites)


class ReturnNone(_SiteOperator):
    """``return <ifade>`` ifadesini ``return None`` yapar."""

    name = "RETURN_NONE"

    def _sites(self, tree: ast.Module) -> list[_Site]:
        sites = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            if isinstance(node.value, ast.Constant) and node.value.value is None:
                continue

            def apply(node: ast.Return = node) -> str:
                old = ast.unparse(node.value) if node.value is not None else ""
                node.value = ast.Constant(value=None)
                return f"return {old} -> return None"

            sites.append(_Site(node, apply))
        return _ordered(sites)


OPERATOR_REGISTRY: dict[str, MutationOperator] = {
    op.name: op for op in (AOR(), ROR(), COR(), ConstantReplacement(), ReturnNone())
}


def generate_all(source: str, operators: Sequence[MutationOperator] | None = None) -> list[Mutant]:
    """Verilen (varsayılan: tüm) operatörlerle mutant üretir; aynı kaynaklar tekilleştirilir.

    Geçersiz Python kodunda ``ValueError`` fırlatır.
    """
    seen = {ast.unparse(_parse(source))}
    result: list[Mutant] = []
    for operator in operators if operators is not None else OPERATOR_REGISTRY.values():
        for mutant in operator.generate(source):
            if mutant.source not in seen:
                seen.add(mutant.source)
                result.append(mutant)
    return result
