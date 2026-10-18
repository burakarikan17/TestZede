"""RL test üretimi cephesi (Facade): GUI'nin "RL Test Üretimi" sayfası bunu kullanır (US-3, US-4).

Kullanıcı kendi test dosyasını da verirse (US-3 artırım) RL bu testlerin coverage'ıyla
başlar ve yalnızca eksik kalan satır/dallar için test ekler; sonuç "kullanıcı testleri"
ve "kullanıcı testleri + RL" coverage'ı olarak iki ayrı değer döner.

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
from testzede.rl.executor import TARGET_MODULE, Executor

__all__ = [
    "TARGET_MODULE",
    "GenerationResult",
    "build_unit",
    "generate",
    "guess_module_name",
    "list_functions",
    "load_rl_config",
    "tests_module",
    "user_test_case",
]
from testzede.rl.signature import SignatureError
from testzede.rl.trainer import RLConfig, generate_tests
from testzede.services.errors import ServiceError

USER_UID = "user/kod"
USER_TEST_NAME = "user_tests"


@dataclass
class GenerationResult:
    """Bir üretim çalıştırmasının sonucu (sayfanın alt şeridindeki istatistikler dahil)."""

    unit: CodeUnit
    tests: list[TestCase]
    coverage: CoverageReport | None
    stats: RunStats
    curve: list[CurvePoint]
    steps: int
    baseline: CoverageReport | None = None  # yalnızca kullanıcı testleri
    user_outcome: str | None = None  # kullanıcı test dosyasının sonucu ("passed", "failed" …)

    @property
    def branch_rate(self) -> float:
        return _branch_rate(self.coverage)

    @property
    def baseline_branch_rate(self) -> float:
        return _branch_rate(self.baseline)


def _branch_rate(cov: CoverageReport | None) -> float:
    return cov.covered_branches / cov.total_branches if cov and cov.total_branches else 0.0


class _ImportRewriter(ast.NodeTransformer):
    """``hesap`` modülüne yapılan import'ları ``target``'a çevirir (adlar korunur)."""

    def __init__(self, module: str) -> None:
        self.module = module

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom:
        if node.level == 0 and node.module == self.module:
            node.module = TARGET_MODULE
        return node

    def visit_Import(self, node: ast.Import) -> ast.Import:
        for alias in node.names:
            if alias.name == self.module:
                alias.asname = alias.asname or self.module
                alias.name = TARGET_MODULE
        return node


def guess_module_name(test_source: str, source: str) -> str | None:
    """Test dosyasının, kaynaktaki bir adı import ettiği modülün adı (bulunamazsa ``None``).

    Örn. kaynakta ``topla`` tanımlıysa ``from hesap import topla`` → ``"hesap"``.
    """
    try:
        defined = {
            node.name
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef | ast.ClassDef)
        }
        tree = ast.parse(test_source)
    except (SyntaxError, ValueError):
        return None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module
            and any(alias.name in defined or alias.name == "*" for alias in node.names)
        ):
            return node.module
    return None


def user_test_case(test_source: str, module_name: str | None) -> TestCase:
    """Kullanıcının test dosyasını, kaynağı ``target`` olarak import eden bir teste çevirir.

    ``module_name`` kullanıcının kaynak dosyasının modül adıdır (``hesap.py`` → ``hesap``).

    Raises:
        ServiceError: Dosya ayrıştırılamıyor ya da ``test_`` ile başlayan fonksiyon yoksa.
    """
    try:
        tree = ast.parse(test_source)
    except SyntaxError as exc:
        raise ServiceError(f"Test dosyası ayrıştırılamadı (satır {exc.lineno}): {exc.msg}") from exc
    except (ValueError, RecursionError, MemoryError) as exc:
        raise ServiceError(f"Test dosyası ayrıştırılamadı: {exc}") from exc
    has_tests = any(
        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test")
        or isinstance(node, ast.ClassDef)
        and node.name.startswith("Test")
        for node in tree.body
    )
    if not has_tests:
        raise ServiceError("Test dosyasında 'test' ile başlayan bir test fonksiyonu yok.")
    if module_name and module_name != TARGET_MODULE:
        tree = ast.fix_missing_locations(_ImportRewriter(module_name).visit(tree))
        test_source = ast.unparse(tree)
    return TestCase(name=USER_TEST_NAME, code=test_source, origin="user")


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
    user_tests: str | None = None,
    module_name: str | None = None,
) -> GenerationResult:
    """RL ile testleri üretir; coverage'ı seçilen paketin tam çalıştırmasından ölçer.

    ``user_tests`` verilirse RL bu testlerin coverage'ıyla başlar (US-3 artırım);
    ``coverage`` kullanıcı testleri + RL testlerinin birlikte coverage'ıdır.
    ``module_name`` verilmezse test dosyasının import'larından tahmin edilir.

    Raises:
        ServiceError: Kod, fonksiyon, test dosyası ya da yapılandırma geçersizse.
    """
    unit = build_unit(source, entry_point)
    baseline: list[TestCase] = []
    if user_tests and user_tests.strip():
        module_name = module_name or guess_module_name(user_tests, source)
        baseline.append(user_test_case(user_tests, module_name))
    config = config or load_rl_config()
    executor = executor or SandboxExecutor()
    try:
        episode = generate_tests(unit, executor, config, seed=seed, baseline=baseline)
    except SignatureError as exc:
        raise ServiceError(str(exc)) from exc
    user_outcome = None
    if baseline:
        run = executor.run_tests(unit, baseline, timeout=suite_timeout_s)
        user_outcome = run.test_outcomes.get(USER_TEST_NAME, "error")
    suite = [*baseline, *episode.tests]
    coverage, _ = measure_suite(unit, suite, executor, timeout=suite_timeout_s)
    return GenerationResult(
        unit,
        episode.tests,
        coverage or episode.coverage,
        episode.stats,
        episode.curve,
        episode.steps,
        baseline=episode.baseline,
        user_outcome=user_outcome,
    )


def tests_module(result: GenerationResult, module_name: str = TARGET_MODULE) -> str:
    """Üretilen testleri tek bir pytest dosyası olarak birleştirir (import'lar tekilleştirilir).

    Testler test edilen kodu ``module_name`` modülünden import eder (varsayılan ``target``).
    """
    imports: list[str] = []
    bodies: list[str] = []
    for test in result.tests:
        head, _, body = test.code.partition("\n\n\n")
        for line in head.splitlines():
            if line.startswith(f"from {TARGET_MODULE} import "):
                line = f"from {module_name} import " + line.split(" import ", 1)[1]
            if line.strip() and line not in imports:
                imports.append(line)
        bodies.append(body.strip("\n"))
    header = "# TestZede RL tarafından üretildi.\n"
    return header + "\n".join(imports) + "\n\n\n" + "\n\n\n".join(bodies) + "\n"
