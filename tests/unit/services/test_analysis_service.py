import csv
import io

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from testzede.analysis.metrics import METRIC_DESCRIPTIONS, METRIC_NAMES
from testzede.services.analysis_service import (
    AnalysisService,
    CallGraphView,
    format_metric,
)
from testzede.services.errors import ServiceError

SERVICE = AnalysisService()

CHAIN = "def a():\n    b()\n\ndef b():\n    c()\n\ndef c():\n    pass\n"
MIXED = (
    "import math\n"
    "def fact(n):\n    return 1 if n < 2 else n * fact(n - 1)\n"
    "def main(x):\n    print(len(str(fact(x))), math.sqrt(x))\n"
    "main(3)\n"
)


def view(source: str) -> CallGraphView:
    return SERVICE.call_graph(source)


# ---- çağrı grafiği -------------------------------------------------------------------


def test_nodes_edges_and_neighbours():
    graph = view("def a():\n    b()\n    len([])\n\ndef b():\n    pass\n")
    assert sorted(n.name for n in graph.nodes) == ["<builtin>.len", "a", "b"]
    assert graph.nodes[0].name == "a"  # çağıran en üst katmanda
    assert graph.edges == (("a", "<builtin>.len"), ("a", "b"))
    a, b = graph.node("a"), graph.node("b")
    assert a.calls == ("<builtin>.len", "b")
    assert a.called_by == ()
    assert b.called_by == ("a",)
    assert (a.kind, b.kind, graph.node("<builtin>.len").kind) == ("function", "function", "builtin")


def test_kinds_counts_and_labels():
    graph = view(MIXED)
    assert graph.count("function") == 2
    assert graph.count("builtin") == 3  # print, len, str
    assert graph.count("external") == 1
    assert graph.count("module") == 1
    assert graph.node("<builtin>.len").label == "len"
    assert graph.node("<external>.math.sqrt").label == "math.sqrt"
    assert graph.node("main").label == "main"
    assert graph.node("<module>").label == "<module>"


def test_recursion_is_reported():
    graph = view(MIXED)
    assert graph.recursive == ("fact",)
    assert graph.node("fact").recursive
    assert not graph.node("main").recursive


def test_layers_put_callers_above_callees():
    graph = view(CHAIN)
    assert [(n.name, n.layer, n.y) for n in graph.nodes] == [
        ("a", 0, 0),
        ("b", 1, -1),
        ("c", 2, -2),
    ]


def test_mutual_recursion_shares_a_layer():
    graph = view("def even(n):\n    return odd(n - 1)\n\ndef odd(n):\n    return even(n - 1)\n")
    assert {n.layer for n in graph.nodes} == {0}


def test_layer_nodes_are_centered_and_spaced():
    graph = view("def a():\n    b()\n    c()\n\ndef b():\n    pass\n\ndef c():\n    pass\n")
    xs = {n.name: n.x for n in graph.nodes}
    assert xs["a"] == 0
    assert xs["b"] == -xs["c"] < 0


def test_layout_orders_children_under_their_parents():
    # Alfabetik sıra y, z olurdu; çağıranlara göre sıralama z'yi a'nın altına koyar.
    source = "def a():\n    z()\n\ndef b():\n    y()\n\ndef y():\n    pass\n\ndef z():\n    pass\n"
    xs = {n.name: n.x for n in view(source).nodes}
    assert xs["a"] < xs["b"]
    assert xs["z"] < xs["y"]


def test_layout_is_deterministic():
    assert view(MIXED) == view(MIXED)


def test_unknown_node_raises_key_error():
    with pytest.raises(KeyError):
        view(CHAIN).node("zzz")


def test_code_without_calls_gives_an_empty_graph():
    graph = view("x = 1\n")
    assert graph.nodes == () and graph.edges == ()
    assert graph.recursive == ()


@pytest.mark.parametrize("source", ["", "   \n\t"])
def test_empty_source_is_a_service_error(source):
    with pytest.raises(ServiceError, match="Kaynak kod boş"):
        SERVICE.call_graph(source)
    with pytest.raises(ServiceError, match="Kaynak kod boş"):
        SERVICE.metrics(source)


def test_syntax_error_is_a_service_error_with_line_number():
    with pytest.raises(ServiceError, match=r"Çağrı grafiği çıkarılamadı.*satır 1"):
        SERVICE.call_graph("def broken(:\n")
    with pytest.raises(ServiceError, match=r"Metrikler hesaplanamadı.*satır 1"):
        SERVICE.metrics("def broken(:\n")


# ---- metrikler -----------------------------------------------------------------------


def test_metrics_have_all_14_rows_in_order_with_descriptions():
    metrics = SERVICE.metrics(MIXED)
    assert [row.name for row in metrics.rows] == list(METRIC_NAMES)
    assert len(metrics.rows) == 14
    assert [row.description for row in metrics.rows] == [
        METRIC_DESCRIPTIONS[n] for n in METRIC_NAMES
    ]


def test_metric_values_and_formats():
    metrics = SERVICE.metrics("def f(a):\n    # not\n    return a + 1\n")
    assert metrics.value("LOC") == 3
    rows = {row.name: row for row in metrics.rows}
    assert rows["LOC"].text == "3"
    assert rows["Yorum"].text == "1"
    assert rows["Çevrimsel Karmaşıklık"].text == "1"
    assert rows["Halstead Hacim"].text == f"{rows['Halstead Hacim'].value:.2f}"
    assert rows["Sürdürülebilirlik İndeksi"].text.count(".") == 1


def test_format_metric():
    assert format_metric("LOC", 12.0) == "12"
    assert format_metric("Halstead Zaman", 36.9333) == "36.93"
    assert format_metric("Halstead Uzunluk", 29.0) == "29"


def test_maintainability_rank_and_text():
    metrics = SERVICE.metrics("def f(a):\n    return a\n")
    assert metrics.maintainability_rank == "A"
    assert metrics.maintainability_text == "A (yüksek)"


def test_unknown_metric_raises_key_error():
    with pytest.raises(KeyError):
        SERVICE.metrics("x = 1\n").value("yok")


def test_csv_has_header_and_one_line_per_metric():
    text = SERVICE.metrics_csv(SERVICE.metrics(MIXED))
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == ["Metrik", "Değer", "Açıklama"]
    assert [r[0] for r in rows[1:]] == list(METRIC_NAMES)
    assert all(len(r) == 3 for r in rows)


def test_csv_export_writes_a_bom_for_excel(tmp_path):
    target = SERVICE.export_metrics_csv(SERVICE.metrics(MIXED), tmp_path / "m.csv")
    raw = target.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "Sürdürülebilirlik İndeksi" in raw.decode("utf-8-sig")


def test_csv_export_failure_is_a_service_error(tmp_path):
    with pytest.raises(ServiceError, match="CSV dosyası yazılamadı"):
        SERVICE.export_metrics_csv(SERVICE.metrics(MIXED), tmp_path)  # klasör, dosya değil


# ---- HumanEval görevleri -------------------------------------------------------------


def _write_humaneval(data_dir, rows):
    path = data_dir / "raw" / "humaneval" / "test.parquet"
    path.parent.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def test_humaneval_tasks_are_loaded_with_labels(tmp_path):
    _write_humaneval(
        tmp_path,
        [
            {
                "task_id": "HumanEval/0",
                "prompt": "def inc(x):\n",
                "canonical_solution": "    return x + 1\n",
                "entry_point": "inc",
            }
        ],
    )
    service = AnalysisService(tmp_path)
    assert service.humaneval_available()
    (task,) = service.humaneval_tasks()
    assert task.uid == "HumanEval/0"
    assert task.label == "HumanEval/0 · inc"
    assert "return x + 1" in task.source


def test_humaneval_missing_data_explains_how_to_download(tmp_path):
    service = AnalysisService(tmp_path)
    assert not service.humaneval_available()
    with pytest.raises(ServiceError, match="testzede download --dataset humaneval"):
        service.humaneval_tasks()
