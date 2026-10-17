"""RL test üretimi cephesi (Facade): GUI'nin "RL Test Üretimi" sayfası bunu kullanır (US-3, US-4).

Kullanıcı kaynaklı her hata ``ServiceError`` olarak döner; mesajı doğrudan
arayüzde gösterilebilir.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from testzede.batch.runner import measure_suite
from testzede.config import default_config_path, load_config
from testzede.datasets.base import SkippedUnit
from testzede.datasets.units import make_unit
from testzede.domain.models import CodeUnit, CoverageReport, RunStats, TestCase
from testzede.execution.executor import SandboxExecutor
from testzede.rl.env import CurvePoint
from testzede.rl.executor import Executor
from testzede.rl.signature import SignatureError
from testzede.rl.trainer import RLConfig, generate_tests
from testzede.services.errors import ServiceError

USER_UID = "user/kod"


@dataclass
class GenerationResult:
    """Bir üretim çalıştırmasının sonucu (sayfanın alt şeridindeki istatistikler dahil)."""

    unit: CodeUnit
    tests: list[TestCase]
    coverage: CoverageReport | None
    stats: RunStats
    curve: list[CurvePoint]
    steps: int

    @property
    def branch_rate(self) -> float:
        cov = self.coverage
        return cov.covered_branches / cov.total_branches if cov and cov.total_branches else 0.0


def list_functions(source: str) -> list[str]:
    """Test edilebilecek üst düzey fonksiyonların adları (parametresizler hariç).

    Raises:
        ServiceError: Kaynak ayrıştırılamazsa.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ServiceError(f"Kod ayrıştırılamadı (satır {exc.lineno}): {exc.msg}") from exc
    except (ValueError, RecursionError, MemoryError) as exc:
        raise ServiceError(f"Kod ayrıştırılamadı: {exc}") from exc
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and (node.args.args or node.args.posonlyargs)
    ]


def build_unit(source: str, entry_point: str) -> CodeUnit:
    """Kullanıcı kodundan birim üretir (docstring ``>>>`` örnekleri tohum girdi olur).

    Raises:
        ServiceError: Kod boş/geçersizse ya da fonksiyon yoksa.
    """
    unit = make_unit(USER_UID, "user", source, entry_point)
    if isinstance(unit, SkippedUnit):
        detail = f" ({unit.detail})" if unit.detail else ""
        messages = {
            "empty_source": "Kod boş.",
            "syntax_error": "Kod ayrıştırılamadı",
            "no_entry_point": "Fonksiyon bulunamadı",
        }
        raise ServiceError(f"{messages.get(unit.reason, unit.reason)}{detail}")
    return unit


def load_rl_config(path: Path | None = None) -> RLConfig:
    """``configs/frozen.yaml`` (yoksa ``default.yaml``) içinden RL ayarlarını okur.

    Raises:
        ServiceError: Dosya okunamaz ya da ayarlar geçersizse.
    """
    path = path or default_config_path()
    try:
        return RLConfig.from_mapping(load_config(path))
    except (ValueError, TypeError) as exc:  # ConfigError dahil
        raise ServiceError(f"Yapılandırma geçersiz ({path}): {exc}") from exc


def generate(
    source: str,
    entry_point: str,
    *,
    config: RLConfig | None = None,
    executor: Executor | None = None,
    seed: int | None = 0,
    suite_timeout_s: float = 60.0,
) -> GenerationResult:
    """RL ile testleri üretir; coverage'ı seçilen paketin tam çalıştırmasından ölçer.

    Raises:
        ServiceError: Kod, fonksiyon ya da yapılandırma geçersizse.
    """
    unit = build_unit(source, entry_point)
    config = config or load_rl_config()
    executor = executor or SandboxExecutor()
    try:
        episode = generate_tests(unit, executor, config, seed=seed)
    except SignatureError as exc:
        raise ServiceError(str(exc)) from exc
    coverage, _ = measure_suite(unit, episode.tests, executor, timeout=suite_timeout_s)
    return GenerationResult(
        unit,
        episode.tests,
        coverage or episode.coverage,
        episode.stats,
        episode.curve,
        episode.steps,
    )


def tests_module(result: GenerationResult) -> str:
    """Üretilen testleri tek bir pytest dosyası olarak birleştirir (import'lar tekilleştirilir).

    Dosya, test edilen kodun ``target.py`` adıyla yanında durduğunu varsayar.
    """
    imports: list[str] = []
    bodies: list[str] = []
    for test in result.tests:
        head, _, body = test.code.partition("\n\n\n")
        for line in head.splitlines():
            if line.strip() and line not in imports:
                imports.append(line)
        bodies.append(body.strip("\n"))
    header = "# TestZede RL tarafından üretildi.\n"
    return header + "\n".join(imports) + "\n\n\n" + "\n\n\n".join(bodies) + "\n"
