import ast

import pytest

from testzede.analysis import metrics, parsing
from testzede.analysis.parsing import SourceError, parse_python


def test_valid_source_returns_a_module():
    tree = parse_python("def f():\n    pass\n")
    assert isinstance(tree, ast.Module) and len(tree.body) == 1


def test_syntax_error_message_has_line_and_reason():
    with pytest.raises(SourceError, match=r"^Kod ayrıştırılamadı \(satır 2\): "):
        parse_python("x = 1\ny = (\n")


def test_errors_without_a_line_number_still_have_a_message():
    with pytest.raises(SourceError, match=r"^Kod ayrıştırılamadı: .*null"):
        parse_python("x\x00")


@pytest.mark.parametrize("error", [RecursionError("çok derin"), MemoryError("bellek")])
def test_resource_errors_become_source_errors(monkeypatch, error):
    def explode(source):
        raise error

    monkeypatch.setattr(parsing.ast, "parse", explode)
    with pytest.raises(SourceError, match="Kod ayrıştırılamadı"):
        parse_python("x = 1")


def test_warnings_are_suppressed(recwarn):
    parse_python('x = "\\d"\n')
    assert not [w for w in recwarn if issubclass(w.category, (SyntaxWarning, DeprecationWarning))]


def test_radon_syntax_errors_do_not_leak_a_none_line_number(monkeypatch):
    def explode(source):
        raise SyntaxError("SyntaxError at line: 1")  # radon satır numarası taşımaz

    monkeypatch.setattr(metrics, "analyze", explode)
    with pytest.raises(metrics.MetricsError) as raised:
        metrics.compute_metrics("x = 1\n")
    assert "None" not in str(raised.value)
