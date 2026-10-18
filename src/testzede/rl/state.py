"""Tabular Q-learning için ayrıklaştırılmış durum.

Durum: (satır coverage dilimi, branch coverage dilimi, son eylem başarılı mı,
adım dilimi). Her bileşen ``bins`` dilime bölünür.
"""

from __future__ import annotations

from dataclasses import dataclass

from testzede.domain.models import CoverageReport
from testzede.rl.reward import branch_rate, line_rate


@dataclass(frozen=True)
class State:
    line_bin: int
    branch_bin: int
    last_ok: bool
    step_bin: int


def _bin(rate: float, bins: int) -> int:
    """[0, 1] oranını 0..bins-1 dilimine yerleştirir; yalnızca 1.0 son dilime düşer."""
    if rate >= 1.0:
        return bins - 1
    return min(int(max(rate, 0.0) * (bins - 1)), bins - 2)


def discretize(
    report: CoverageReport | None, *, last_ok: bool, step: int, max_steps: int, bins: int = 5
) -> State:
    """Coverage raporunu ve adım sayısını ayrık bir duruma çevirir.

    Tam coverage (%100) kendi diliminde tutulur, böylece ajan hedefe ulaşıldığını ayırt edebilir.
    """
    if bins < 2:
        raise ValueError("bins en az 2 olmalı")
    if max_steps < 1:
        raise ValueError("max_steps en az 1 olmalı")
    return State(
        line_bin=_bin(line_rate(report), bins),
        branch_bin=_bin(branch_rate(report), bins),
        last_ok=last_ok,
        step_bin=_bin(step / max_steps, bins),
    )


def state_count(bins: int = 5) -> int:
    """Durum uzayının boyutu."""
    return bins * bins * 2 * bins


def state_index(state: State, bins: int = 5) -> int:
    """Durumu Q-tablosu satır indeksine çevirir (0..state_count-1)."""
    return ((state.line_bin * bins + state.branch_bin) * 2 + int(state.last_ok)) * bins + (
        state.step_bin
    )
