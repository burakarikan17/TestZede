"""Coverage sayfası için cephe (Facade)."""

from __future__ import annotations

import ast

from testzede.domain.models import CodeUnit, TestCase
from testzede.execution.coverage_runner import ExecutionResult, run_tests
from testzede.services.errors import ServiceError

DEFAULT_TIMEOUT = 10.0


def _first_function_name(tree: ast.Module) -> str | None:
    """Kaynaktaki ilk üst düzey fonksiyonun adını döndürür; yoksa ``None``."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    return None


class CoverageService:
    """Kullanıcı kodu ve testleri için coverage hesabını GUI'ye sunar."""

    def run(
        self, source: str, tests: list[TestCase], timeout: float = DEFAULT_TIMEOUT
    ) -> ExecutionResult:
        """Girdileri doğrular, testleri koşturur ve sonucu aynen döndürür.

        Boş/geçersiz kaynak ya da boş test listesinde ``ServiceError`` fırlatır.
        """
        if not source.strip():
            raise ServiceError("Kaynak kod boş. Lütfen önce bir Python kodu yükleyin.")
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError) as exc:
            raise ServiceError(f"Kaynak kod geçerli bir Python kodu değil: {exc}") from exc
        if not tests:
            raise ServiceError("Test listesi boş. Coverage hesaplamak için en az bir test gerekir.")
        unit = CodeUnit(
            uid="user/0",
            source=source,
            entry_point=_first_function_name(tree),
            dataset=None,
        )
        return run_tests(unit, tests, timeout=timeout)
