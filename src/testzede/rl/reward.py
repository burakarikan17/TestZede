"""Ödül fonksiyonu.

``r = α·Δline + β·Δbranch + γ·yeni_çıktı_sınıfı − δ·(geçersiz/timeout) − ε``

Δ değerleri coverage oranlarındaki (0–1) artıştır. ε her test için ödenen
sabit maliyettir; gereksiz test üretimini cezalandırır.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields

from testzede.domain.models import CoverageReport


@dataclass(frozen=True)
class RewardWeights:
    alpha: float = 1.0  # Δline
    beta: float = 2.0  # Δbranch
    gamma: float = 0.5  # yeni çıktı sınıfı
    delta: float = 1.0  # geçersiz/timeout cezası
    epsilon: float = 0.05  # test başı maliyet

    @classmethod
    def from_config(cls, config: Mapping[str, float]) -> RewardWeights:
        """``configs/*.yaml`` içindeki ``reward`` bölümünden ağırlıkları okur."""
        names = {f.name for f in fields(cls)}
        unknown = set(config) - names
        if unknown:
            raise ValueError(f"Bilinmeyen ödül ağırlığı: {', '.join(sorted(unknown))}")
        return cls(**{k: float(v) for k, v in config.items()})


def branch_rate(report: CoverageReport | None) -> float:
    """Branch coverage oranı; branch yoksa ya da rapor yoksa 0."""
    if report is None or not report.total_branches:
        return 0.0
    return report.covered_branches / report.total_branches


def line_rate(report: CoverageReport | None) -> float:
    return report.line_rate if report is not None else 0.0


def compute_reward(
    weights: RewardWeights,
    before: CoverageReport | None,
    after: CoverageReport | None,
    *,
    new_output_class: bool,
    invalid: bool,
) -> float:
    """Bir test eklendikten sonraki adım ödülünü hesaplar.

    Args:
        before: Test eklenmeden önceki toplam coverage (ilk adımda ``None``).
        after: Test eklendikten sonraki toplam coverage; test çalışmadıysa ``None``
            verilebilir, bu durumda coverage değişmemiş sayılır.
        new_output_class: Girdi daha önce görülmemiş bir çıktı türü/istisna üretti mi.
        invalid: Test derlenemedi, hata verdi ya da zaman aşımına uğradı mı.
    """
    if after is None:
        after = before
    d_line = max(0.0, line_rate(after) - line_rate(before))
    d_branch = max(0.0, branch_rate(after) - branch_rate(before))
    return (
        weights.alpha * d_line
        + weights.beta * d_branch
        + weights.gamma * float(new_output_class)
        - weights.delta * float(invalid)
        - weights.epsilon
    )
