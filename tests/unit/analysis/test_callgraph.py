import pytest

from testzede.analysis.callgraph import CallGraphError, build_call_graph


def edges(source: str) -> set[tuple[str, str]]:
    return set(build_call_graph(source).edges)


def test_function_calls_become_edges():
    src = "def a():\n    b()\n\ndef b():\n    pass\n"
    assert edges(src) == {("a", "b")}


def test_builtin_calls_are_labelled():
    graph = build_call_graph("def f(x):\n    return len(x)\n")
    assert ("f", "<builtin>.len") in graph.edges
    assert graph.nodes["<builtin>.len"]["kind"] == "builtin"


def test_recursion_is_a_self_loop():
    assert ("fact", "fact") in edges("def fact(n):\n    return n * fact(n - 1)\n")


def test_module_level_calls_come_from_module_node():
    assert ("<module>", "<builtin>.print") in edges("print(1)\n")


def test_unresolved_and_imported_calls_are_external():
    src = "import math\n\ndef f(x):\n    return math.sqrt(x)\n"
    assert ("f", "<external>.math.sqrt") in edges(src)


def test_self_method_calls_resolve_to_class_methods():
    src = "class C:\n    def a(self):\n        self.b()\n    def b(self):\n        pass\n"
    assert ("C.a", "C.b") in edges(src)


def test_nested_function_call_resolves_to_inner_definition():
    src = "def outer():\n    def inner():\n        pass\n    inner()\n"
    assert ("outer", "outer.inner") in edges(src)


def test_functions_without_calls_still_appear_as_nodes():
    graph = build_call_graph("def lonely():\n    pass\n")
    assert "lonely" in graph.nodes
    assert graph.number_of_edges() == 0


def test_invalid_syntax_raises_callgraph_error():
    with pytest.raises(CallGraphError):
        build_call_graph("def broken(:\n")


def test_null_bytes_are_a_callgraph_error_not_a_raw_value_error():
    with pytest.raises(CallGraphError, match="null"):
        build_call_graph("f()\x00")


def test_syntax_error_message_has_the_line_number():
    with pytest.raises(CallGraphError, match=r"satır 2"):
        build_call_graph("x = 1\ndef broken(:\n")


def test_invalid_escape_sequences_do_not_emit_warnings(recwarn):
    build_call_graph('def f(x):\n    return "\\d" + x\n')
    assert not [w for w in recwarn if issubclass(w.category, (SyntaxWarning, DeprecationWarning))]
