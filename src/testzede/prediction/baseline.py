"""Temel tahmin (US-7, opsiyonel): Halstead hata sayısı ve McCabe test sayısı.

* Teslim edilen hata sayısı Halstead'e göre ``B = V / 3000`` (V: Halstead hacmi).
* McCabe çevrimsel karmaşıklığı minimum bağımsız yol (basis path) sayısıdır; bu yolların
  her birini sınayan bir test optimum test sayısı olarak alınır.

:func:`knee_point` RL'nin coverage eğrisinden doygunluk noktasını bulur; öğrenilmiş
tahminin hedef değişkeni odur (:mod:`testzede.prediction.learned`).
"""

from __future__ import annotations

from collections.abc import Sequence

from testzede.domain.models import MetricSet, Prediction
from testzede.rl.env import CurvePoint

VOLUME = "Halstead Hacim"
COMPLEXITY = "Çevrimsel Karmaşıklık"
HALSTEAD_DIVISOR = 3000.0
METHOD = "Halstead (B = V / 3000) + McCabe (bağımsız yol)"
KNEE_TOLERANCE = 0.01  # son coverage'a bu kadar yaklaşan ilk nokta diz noktasıdır


def predict_baseline(metrics: MetricSet) -> Prediction:
    """Metriklerden tahmini hata sayısı ve optimum test sayısını hesaplar.

    Raises:
        KeyError: ``metrics`` Halstead hacmini ya da çevrimsel karmaşıklığı içermiyorsa.
    """
    volume = metrics.values[VOLUME]
    complexity = metrics.values[COMPLEXITY]
    return Prediction(
        estimated_bugs=volume / HALSTEAD_DIVISOR,
        optimum_test_count=max(1, round(complexity)),
        method=METHOD,
    )


def knee_point(curve: Sequence[CurvePoint], tolerance: float = KNEE_TOLERANCE) -> int:
    """Satır coverage'ının doygunluğa ulaştığı en küçük test sayısı.

    Eğrinin en yüksek satır coverage'ına ``tolerance`` kadar yaklaşan ilk noktanın test
    sayısıdır; eğri boşsa ``0``.
    """
    if not curve:
        return 0
    target = max(point.line_rate for point in curve) - tolerance
    return min(point.tests for point in curve if point.line_rate >= target)
