"""Veri seti testleri için küçük sahte veri kurucuları (ağ ve gerçek veri gerektirmez)."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pyarrow as pa
import pyarrow.parquet as pq

REPO = "org/repo"

ADD = "def add(a, b):\n    return a + b\n"
MUL = "def mul(a, b):\n    return a * b\n"
NEG = "def neg(a):\n    return -a\n"
SUB = "def sub(a, b):\n    return a - b\n"

HUMANEVAL_ROWS = [
    {
        "task_id": "HumanEval/0",
        "prompt": 'def inc(x):\n    """\n    >>> inc(1)\n    2\n    """\n',
        "canonical_solution": "    return x + 1\n",
        "entry_point": "inc",
    },
    {
        "task_id": "HumanEval/1",
        "prompt": "def twice(x):\n",
        "canonical_solution": "    return 2 * x\n",
        "entry_point": "twice",
    },
]


def write_parquet(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def tge_row(instance_id: str, code_src: str, code_file: str = "pkg/mod.py") -> dict[str, str]:
    return {
        "instance_id": instance_id,
        "repo": REPO,
        "code_file": code_file,
        "code_src": code_src,
    }


def write_xlsx(path: Path, cells: list[str | None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row, value in enumerate(cells, start=1):
        sheet.cell(row=row, column=1, value=value)
    workbook.save(path)


def build_data_dir(root: Path) -> Path:
    """Dört veri setinin de bulunduğu küçük bir ``data/`` klasörü kurar.

    Lite: i1 (add), i2 (mul); Lite dev: i9 (fonksiyonsuz). Ana deney: i1 (Lite ile aynı
    örnek), i3 (add; Lite ile birebir aynı kaynak), i4 (neg; Lite'ın ``pkg/b.py``
    dosyasında), i5 (neg; i4'ün kopyası), i6 (sub).
    """
    raw = root / "raw"
    write_parquet(
        raw / "testgeneval-lite" / "test.parquet",
        [tge_row("org__repo-1", ADD, "pkg/a.py"), tge_row("org__repo-2", MUL, "pkg/b.py")],
    )
    write_parquet(
        raw / "testgeneval-lite" / "dev.parquet",
        [tge_row("org__repo-9", "VALUE = 1\n", "pkg/z.py")],
    )
    write_parquet(
        raw / "testgeneval" / "test.parquet",
        [
            tge_row("org__repo-1", ADD, "pkg/a.py"),
            tge_row("org__repo-3", ADD, "pkg/c.py"),
            tge_row("org__repo-4", NEG, "pkg/b.py"),
            tge_row("org__repo-5", NEG, "pkg/d.py"),
            tge_row("org__repo-6", SUB, "pkg/e.py"),
        ],
    )
    write_parquet(raw / "humaneval" / "test.parquet", HUMANEVAL_ROWS)
    write_xlsx(raw / "small67" / "small.xlsx", ["def one(x):\n    return x\n", "def bad(:\n"])
    return root
