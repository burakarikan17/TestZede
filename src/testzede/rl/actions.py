"""RL ajanının eylemleri: girdi üretim stratejileri (Strategy kalıbı).

Her eylem, test edilen fonksiyonun parametre türlerine göre bir argüman demeti
üretir. Üretilen her değer ``repr`` ile yazılıp ``ast.literal_eval`` ile geri
okunabilir olmalıdır; test sentezleyici girdileri bu yolla koda döker.
"""

from __future__ import annotations

import math
import random
import string
from abc import ABC, abstractmethod
from dataclasses import dataclass

from testzede.rl.signature import ParamSpec, TypeSpec

_INT_LIMIT = 2**31 - 1
_SPECIAL_STRINGS = ("\n", "\t", " ", "  a b  ", "ğüşıöçİ", "!@#$%^&*", "\\", "'\"", "0", "-1")
_SCALAR_KINDS = ("int", "str")


@dataclass(frozen=True)
class ActionContext:
    """Bir eylemin girdi üretirken kullandığı bilgiler."""

    params: tuple[ParamSpec, ...]
    seed_inputs: tuple[tuple, ...] = ()  # docstring örneklerinden çıkarılan argümanlar
    best_input: tuple | None = None  # şimdiye kadar en çok coverage kazandıran girdi


class Action(ABC):
    """Girdi üretim stratejisi."""

    name: str

    def generate(self, ctx: ActionContext, rng: random.Random) -> tuple | None:
        """Bir argüman demeti üretir; strateji uygulanamıyorsa ``None`` döner."""
        return tuple(self.value(p.type, rng) for p in ctx.params)

    @abstractmethod
    def value(self, spec: TypeSpec, rng: random.Random) -> object:
        """Tek bir parametre için değer üretir."""


def _item(spec: TypeSpec, index: int = 0) -> TypeSpec:
    if len(spec.args) > index:
        return spec.args[index]
    return TypeSpec("int")


def _resolve(spec: TypeSpec, rng: random.Random) -> TypeSpec:
    """``any`` türünü somut bir türe çevirir."""
    if spec.kind == "any":
        return TypeSpec(rng.choice(_SCALAR_KINDS))
    return spec


def _collection(spec: TypeSpec, items: list) -> object:
    if spec.kind == "tuple":
        return tuple(items)
    if spec.kind == "set":
        return set(items)
    return items


class _ValueAction(Action):
    """Skaler değerleri ``_scalar``, koleksiyonları ``_size`` ile üreten taban sınıf."""

    def value(self, spec: TypeSpec, rng: random.Random) -> object:
        spec = _resolve(spec, rng)
        if spec.kind in ("list", "tuple", "set"):
            items = [self.value(_item(spec), rng) for _ in range(self._size(rng))]
            return _collection(spec, items)
        if spec.kind == "dict":
            key, val = _hashable(_item(spec, 0)), _item(spec, 1)
            return {self.value(key, rng): self.value(val, rng) for _ in range(self._size(rng))}
        return self._scalar(spec.kind, rng)

    @abstractmethod
    def _scalar(self, kind: str, rng: random.Random) -> object: ...

    @abstractmethod
    def _size(self, rng: random.Random) -> int: ...


def _hashable(spec: TypeSpec) -> TypeSpec:
    return spec if spec.kind in ("int", "float", "bool", "str") else TypeSpec("str")


class Boundary(_ValueAction):
    name = "BOUNDARY"

    def _scalar(self, kind: str, rng: random.Random) -> object:
        if kind == "int":
            return rng.choice((0, 1, -1, _INT_LIMIT, -_INT_LIMIT - 1))
        if kind == "float":
            return rng.choice((0.0, 1.0, -1.0, 1e-9, -1e-9, 1e308))
        if kind == "bool":
            return rng.choice((True, False))
        return rng.choice(("a", " ", "A", "z"))

    def _size(self, rng: random.Random) -> int:
        return 1


class Empty(_ValueAction):
    name = "EMPTY"

    def _scalar(self, kind: str, rng: random.Random) -> object:
        return {"int": 0, "float": 0.0, "bool": False}.get(kind, "")

    def _size(self, rng: random.Random) -> int:
        return 0


class Negative(_ValueAction):
    name = "NEGATIVE"

    def _scalar(self, kind: str, rng: random.Random) -> object:
        if kind == "int":
            return rng.randint(-100, -1)
        if kind == "float":
            return round(rng.uniform(-100.0, -0.01), 2)
        if kind == "bool":
            return False
        return "-" + str(rng.randint(1, 100))

    def _size(self, rng: random.Random) -> int:
        return rng.randint(1, 5)


class RandomSmall(_ValueAction):
    name = "RANDOM_SMALL"

    def _scalar(self, kind: str, rng: random.Random) -> object:
        if kind == "int":
            return rng.randint(-10, 10)
        if kind == "float":
            return round(rng.uniform(-10.0, 10.0), 2)
        if kind == "bool":
            return rng.choice((True, False))
        return "".join(rng.choices(string.ascii_lowercase, k=rng.randint(1, 5)))

    def _size(self, rng: random.Random) -> int:
        return rng.randint(1, 5)


class RandomLarge(_ValueAction):
    name = "RANDOM_LARGE"

    def _scalar(self, kind: str, rng: random.Random) -> object:
        if kind == "int":
            return rng.choice((1, -1)) * rng.randint(10**6, 10**9)
        if kind == "float":
            return round(rng.choice((1, -1)) * rng.uniform(1e6, 1e9), 2)
        if kind == "bool":
            return rng.choice((True, False))
        return "".join(rng.choices(string.ascii_letters + string.digits, k=rng.randint(50, 200)))

    def _size(self, rng: random.Random) -> int:
        return rng.randint(50, 100)


class SpecialChars(_ValueAction):
    name = "SPECIAL_CHARS"

    def _scalar(self, kind: str, rng: random.Random) -> object:
        if kind == "str":
            return rng.choice(_SPECIAL_STRINGS)
        if kind == "float":
            return rng.choice((-0.0, 1e-300, 0.1 + 0.2))
        return Boundary()._scalar(kind, rng)

    def _size(self, rng: random.Random) -> int:
        return rng.randint(1, 3)


class FromDocstring(Action):
    """Docstring'deki ``>>>`` örneklerinden birini aynen kullanır."""

    name = "FROM_DOCSTRING"

    def generate(self, ctx: ActionContext, rng: random.Random) -> tuple | None:
        candidates = [s for s in ctx.seed_inputs if len(s) == len(ctx.params)]
        return rng.choice(candidates) if candidates else None

    def value(self, spec: TypeSpec, rng: random.Random) -> object:
        return RandomSmall().value(spec, rng)


class MutateBest(Action):
    """En iyi girdinin rastgele bir argümanını küçük bir değişiklikle bozar."""

    name = "MUTATE_BEST"

    def generate(self, ctx: ActionContext, rng: random.Random) -> tuple | None:
        if ctx.best_input is None or not ctx.best_input:
            return None
        args = list(ctx.best_input)
        index = rng.randrange(len(args))
        args[index] = self.mutate(args[index], rng)
        return tuple(args)

    def value(self, spec: TypeSpec, rng: random.Random) -> object:
        return RandomSmall().value(spec, rng)

    def mutate(self, value: object, rng: random.Random) -> object:
        if isinstance(value, bool):
            return not value
        if isinstance(value, int):
            return rng.choice((value + 1, value - 1, -value, value * 2))
        if isinstance(value, float):
            mutated = rng.choice((value + 1.0, value - 1.0, -value, value * 2))
            return mutated if math.isfinite(mutated) else -value
        if isinstance(value, str):
            if value and rng.random() < 0.5:
                i = rng.randrange(len(value))
                return value[:i] + value[i + 1 :]
            i = rng.randint(0, len(value))
            return value[:i] + rng.choice(string.ascii_letters) + value[i:]
        if isinstance(value, list | tuple):
            items = list(value)
            choice = rng.randrange(3) if items else 0
            if choice == 0:
                items.append(self.mutate(items[-1], rng) if items else 0)
            elif choice == 1:
                items.pop(rng.randrange(len(items)))
            else:
                items.reverse()
            return type(value)(items)
        return value


ACTION_REGISTRY: dict[str, Action] = {
    action.name: action
    for action in (
        Boundary(),
        Empty(),
        Negative(),
        RandomSmall(),
        RandomLarge(),
        SpecialChars(),
        FromDocstring(),
        MutateBest(),
    )
}
"""Eylem adı → strateji. Sıra Q-tablosundaki eylem indeksini belirler."""

ACTION_NAMES: tuple[str, ...] = tuple(ACTION_REGISTRY)
