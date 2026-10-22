"""TestZede SDD'sinin UML diyagramlarını çizer (matplotlib).

Makinede Graphviz, PlantUML ya da Mermaid CLI olmadığı için diyagramlar burada elle
yerleştirilir; bu dosya diyagramların kaynağıdır. İçerik ``src/testzede`` kodundan alınmıştır
(sınıf, metot ve alan adları koddakiyle aynıdır).

Çalıştırma (depo kökünden)::

    python docs/diagrams/draw_diagrams.py

Her diyagram ``docs/diagrams/<ad>.png`` olarak yazılır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, Polygon, Rectangle
from matplotlib.textpath import TextPath

OUT = Path(__file__).resolve().parent
DPI = 200

SANS = "DejaVu Sans"
MONO = "DejaVu Sans Mono"
INK = "#1F3864"
MUTED = "#5A5A5A"
HEAD = "#D9E2F3"
FILL = "#F4F7FC"
NOTE = "#FFF6D5"
NOTE_EDGE = "#B39A3C"
GREY = "#9AA5B8"

FS = 7.5  # gövde yazısı (pt)
LINE = FS * 1.45 / 72  # satır yüksekliği (inç)
PAD = 0.07


def text_width(text: str, size: float = FS, family: str = SANS, weight: str = "normal") -> float:
    """Metnin genişliği (inç)."""
    if not text.strip():
        return 0.0
    if family == MONO:  # eş aralıklı: baştaki boşluklar da yer kaplar
        return len(text) * 0.602 * size / 72
    path = TextPath((0, 0), text, size=size, prop=FontProperties(family=family, weight=weight))
    return path.get_extents().width / 72


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float
    shape: str = "rect"

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def side(self, name: str, f: float = 0.5) -> tuple[float, float]:
        """Kenar üzerindeki nokta: ``f`` kenar boyunca 0..1 konumdur."""
        if name == "top":
            return self.x + self.w * f, self.y
        if name == "bottom":
            return self.x + self.w * f, self.y + self.h
        if name == "left":
            return self.x, self.y + self.h * f
        return self.x + self.w, self.y + self.h * f

    def clip(self, tx: float, ty: float) -> tuple[float, float]:
        """Merkezden ``(tx, ty)`` yönündeki kenar noktası."""
        cx, cy = self.center
        dx, dy = tx - cx, ty - cy
        if dx == 0 and dy == 0:
            return cx, cy
        rx, ry = self.w / 2, self.h / 2
        if self.shape == "ellipse":
            t = 1 / math.sqrt((dx / rx) ** 2 + (dy / ry) ** 2)
        elif self.shape == "diamond":
            t = 1 / (abs(dx) / rx + abs(dy) / ry)
        else:
            t = min(rx / abs(dx) if dx else math.inf, ry / abs(dy) if dy else math.inf)
        return cx + dx * t, cy + dy * t


class Diagram:
    def __init__(self, width: float, height: float, title: str) -> None:
        self.fig = Figure(figsize=(width, height), dpi=DPI)
        self.ax = self.fig.add_axes((0, 0, 1, 1))
        self.ax.set_xlim(0, width)
        self.ax.set_ylim(height, 0)
        self.ax.axis("off")
        self.width, self.height = width, height
        self.text(width / 2, 0.22, title, size=11, weight="bold", ha="center")

    def text(
        self,
        x: float,
        y: float,
        s: str,
        *,
        size: float = FS,
        weight: str = "normal",
        ha: str = "left",
        va: str = "center",
        color: str = INK,
        family: str = SANS,
        style: str = "normal",
        zorder: int = 6,
        bg: str | None = None,
    ) -> None:
        bbox = None
        if bg is not None:
            bbox = {"boxstyle": "square,pad=0.08", "fc": bg, "ec": "none"}
        self.ax.text(
            x,
            y,
            s,
            fontsize=size,
            fontweight=weight,
            ha=ha,
            va=va,
            color=color,
            family=family,
            style=style,
            zorder=zorder,
            bbox=bbox,
            linespacing=1.25,
        )

    def line(
        self,
        points: list[tuple[float, float]],
        *,
        dashed: bool = False,
        color: str = INK,
        lw: float = 0.9,
        zorder: int = 3,
    ) -> None:
        xs, ys = zip(*points, strict=True)
        self.ax.add_line(
            Line2D(
                xs,
                ys,
                color=color,
                lw=lw,
                linestyle=(0, (4, 3)) if dashed else "-",
                zorder=zorder,
            )
        )

    def head(
        self,
        tip: tuple[float, float],
        frm: tuple[float, float],
        kind: str,
        color: str = INK,
    ) -> None:
        """Ok başı: ``open`` (V), ``hollow`` (boş üçgen), ``filled`` (dolu üçgen)."""
        ang = math.atan2(tip[1] - frm[1], tip[0] - frm[0])
        size, spread = (0.1, 0.38) if kind != "open" else (0.1, 0.45)
        left = (tip[0] - size * math.cos(ang - spread), tip[1] - size * math.sin(ang - spread))
        right = (tip[0] - size * math.cos(ang + spread), tip[1] - size * math.sin(ang + spread))
        if kind == "open":
            self.line([left, tip, right], color=color, zorder=4)
            return
        fc = "white" if kind == "hollow" else color
        self.ax.add_patch(
            Polygon([tip, left, right], closed=True, fc=fc, ec=color, lw=0.9, zorder=5)
        )

    def diamond(self, at: tuple[float, float], toward: tuple[float, float]) -> None:
        ang = math.atan2(toward[1] - at[1], toward[0] - at[0])
        ux, uy = math.cos(ang), math.sin(ang)
        px, py = -uy, ux
        size, half = 0.18, 0.06
        pts = [
            at,
            (at[0] + ux * size / 2 + px * half, at[1] + uy * size / 2 + py * half),
            (at[0] + ux * size, at[1] + uy * size),
            (at[0] + ux * size / 2 - px * half, at[1] + uy * size / 2 - py * half),
        ]
        self.ax.add_patch(Polygon(pts, closed=True, fc=INK, ec=INK, lw=0.9, zorder=5))

    def save(self, name: str) -> Path:
        path = OUT / f"{name}.png"
        self.fig.savefig(path, dpi=DPI, facecolor="white")
        return path


# --------------------------------------------------------------------------- öğeler


def uml_class(
    d: Diagram,
    x: float,
    y: float,
    name: str,
    attrs: tuple[str, ...] = (),
    ops: tuple[str, ...] = (),
    *,
    stereo: str | None = None,
    abstract: bool = False,
    min_w: float = 0.0,
    fill: str = FILL,
) -> Box:
    """UML sınıf kutusu; sol üst köşe ``(x, y)``."""
    size = FS - 0.5
    widths = [text_width(name, FS + 0.5, SANS, "bold") + 2 * PAD]
    if stereo:
        widths.append(text_width(f"«{stereo}»", FS - 1, SANS) + 2 * PAD)
    widths += [text_width(s, size, MONO) + 2 * PAD for s in (*attrs, *ops)]
    w = max(max(widths), min_w)
    head_h = LINE * (2.0 if stereo else 1.35)
    attrs_h = LINE * 0.95 * len(attrs) + (0.06 if attrs else 0.05)
    ops_h = LINE * 0.95 * len(ops) + (0.06 if ops else 0.0)
    h = head_h + attrs_h + ops_h
    d.ax.add_patch(Rectangle((x, y), w, h, fc=fill, ec=INK, lw=0.9, zorder=2))
    d.ax.add_patch(Rectangle((x, y), w, head_h, fc=HEAD, ec=INK, lw=0.9, zorder=2))
    cy = y + head_h / 2
    if stereo:
        d.text(x + w / 2, y + LINE * 0.6, f"«{stereo}»", size=FS - 1, ha="center", color=MUTED)
        cy = y + LINE * 1.38
    d.text(
        x + w / 2,
        cy,
        name,
        size=FS + 0.5,
        weight="bold",
        ha="center",
        style="italic" if abstract else "normal",
    )
    yy = y + head_h + 0.03 + LINE * 0.5
    for s in attrs:
        d.text(x + PAD, yy, s, size=size, family=MONO, color="#222222")
        yy += LINE * 0.95
    if ops:
        sep = y + head_h + attrs_h
        d.line([(x, sep), (x + w, sep)], lw=0.7)
        yy = sep + 0.03 + LINE * 0.5
        for s in ops:
            d.text(x + PAD, yy, s, size=size, family=MONO, color="#222222")
            yy += LINE * 0.95
    return Box(x, y, w, h)


def note(
    d: Diagram,
    x: float,
    y: float,
    lines: tuple[str, ...],
    *,
    targets: tuple[tuple[float, float], ...] = (),
    size: float = FS - 0.5,
) -> Box:
    w = max(text_width(s, size) for s in lines) + 2 * PAD + 0.08
    h = LINE * len(lines) + 0.1
    fold = 0.1
    pts = [(x, y), (x + w - fold, y), (x + w, y + fold), (x + w, y + h), (x, y + h)]
    d.ax.add_patch(Polygon(pts, closed=True, fc=NOTE, ec=NOTE_EDGE, lw=0.8, zorder=2))
    d.line([(x + w - fold, y), (x + w - fold, y + fold), (x + w, y + fold)], color=NOTE_EDGE)
    yy = y + 0.05 + LINE * 0.5
    for s in lines:
        d.text(x + PAD, yy, s, size=size, color="#3D3200")
        yy += LINE
    box = Box(x, y, w, h)
    for t in targets:
        d.line([box.clip(*t), t], dashed=True, color=NOTE_EDGE, lw=0.8)
    return box


def link(
    d: Diagram,
    a: Box,
    b: Box,
    kind: str = "assoc",
    *,
    label: str | None = None,
    src: tuple[str, float] | None = None,
    dst: tuple[str, float] | None = None,
    via: tuple[tuple[float, float], ...] = (),
    label_at: float = 0.5,
    label_dy: float = -0.07,
    color: str = INK,
    mult: tuple[str | None, str | None] = (None, None),
) -> None:
    """İki kutu arası ilişki.

    ``kind``: ``inherit`` (genelleme), ``realize`` (gerçekleştirme), ``dep`` (bağımlılık),
    ``assoc`` (yönlü ilişki), ``compose`` (bileşim), ``line`` (oksuz çizgi).
    """
    if src is not None:
        p = a.side(*src)
    if dst is not None:
        q = b.side(*dst)
    if src is None:
        aim = via[0] if via else (q if dst is not None else b.center)
        p = a.clip(*aim)
    if dst is None:
        aim = via[-1] if via else p
        q = b.clip(*aim)
    points = [p, *via, q]
    dashed = kind in ("realize", "dep")
    d.line(points, dashed=dashed, color=color)
    last = points[-2]
    if kind in ("inherit", "realize"):
        d.head(q, last, "hollow", color)
    elif kind in ("dep", "assoc"):
        d.head(q, last, "open", color)
    elif kind == "compose":
        d.diamond(p, points[1])
        d.head(q, last, "open", color)
    if label:
        i = min(int(label_at * (len(points) - 1)), len(points) - 2)
        f = label_at * (len(points) - 1) - i
        (x1, y1), (x2, y2) = points[i], points[i + 1]
        d.text(
            x1 + (x2 - x1) * f,
            y1 + (y2 - y1) * f + label_dy,
            label,
            size=FS - 1,
            ha="center",
            color=MUTED,
            bg="white",
        )
    for value, (px, py), (ox, oy) in (
        (mult[0], p, points[1]),
        (mult[1], q, points[-2]),
    ):
        if value:
            ang = math.atan2(oy - py, ox - px)
            d.text(
                px + 0.2 * math.cos(ang) - 0.1 * math.sin(ang),
                py + 0.2 * math.sin(ang) - 0.12,
                value,
                size=FS - 1,
                color=MUTED,
            )


def package(
    d: Diagram,
    x: float,
    y: float,
    w: float,
    h: float,
    name: str,
    body: tuple[str, ...] = (),
    *,
    fill: str = FILL,
) -> Box:
    tab_w = text_width(name, FS + 0.5, SANS, "bold") + 0.2
    tab_h = 0.2
    d.ax.add_patch(Rectangle((x, y - tab_h), tab_w, tab_h, fc=HEAD, ec=INK, lw=0.9, zorder=2))
    d.ax.add_patch(Rectangle((x, y), w, h, fc=fill, ec=INK, lw=0.9, zorder=2))
    d.text(x + 0.1, y - tab_h / 2, name, size=FS + 0.5, weight="bold")
    yy = y + 0.07 + LINE * 0.5
    for s in body:
        d.text(x + 0.08, yy, s, size=FS - 1, color="#222222")
        yy += LINE * 0.9
    return Box(x, y, w, h)


def actor(d: Diagram, cx: float, cy: float, label: str) -> Box:
    r = 0.11
    d.ax.add_patch(Circle((cx, cy - 0.32), r, fc="white", ec=INK, lw=1.0, zorder=4))
    d.line([(cx, cy - 0.21), (cx, cy + 0.08)], lw=1.0)
    d.line([(cx - 0.18, cy - 0.12), (cx + 0.18, cy - 0.12)], lw=1.0)
    d.line([(cx - 0.15, cy + 0.3), (cx, cy + 0.08), (cx + 0.15, cy + 0.3)], lw=1.0)
    d.text(cx, cy + 0.48, label, ha="center", va="top", size=FS)
    return Box(cx - 0.25, cy - 0.45, 0.5, 0.8)


def usecase(
    d: Diagram, cx: float, cy: float, text: str, *, dashed: bool = False, w: float | None = None
) -> Box:
    lines = text.split("\n")
    w = w or max(text_width(s) for s in lines) + 0.5
    h = max(0.42, LINE * len(lines) + 0.2)
    d.ax.add_patch(
        Ellipse(
            (cx, cy),
            w,
            h,
            fc=FILL,
            ec=INK,
            lw=0.9,
            zorder=3,
            linestyle=(0, (4, 3)) if dashed else "-",
        )
    )
    d.text(cx, cy, text, ha="center", size=FS)
    return Box(cx - w / 2, cy - h / 2, w, h, shape="ellipse")


# --------------------------------------------------------------------------- 1. use case


def use_case_diagram() -> Path:
    d = Diagram(9.6, 6.2, "Kullanım Durumu Diyagramı — TestZede")
    user = actor(d, 0.65, 3.0, "Kullanıcı\n(test yazan /\nyükleyen)")
    hf = actor(d, 9.0, 5.3, "Hugging Face\n(veri kaynağı)")
    d.ax.add_patch(Rectangle((1.45, 0.5), 7.0, 5.55, fc="white", ec=INK, lw=1.1, zorder=1))
    d.text(1.6, 0.68, "TestZede (masaüstü arayüz + komut satırı)", weight="bold", size=FS + 0.5)

    xa = 3.35
    main = [
        ("Kod ve test kodunu yükle\n(Kod Yükle) — US-3", 1.27),
        ("Çağrı grafiğini görüntüle — US-1", 1.89),
        ("Kod metriklerini hesapla,\nCSV'ye aktar — US-2", 2.51),
        ("RL ile test üret — US-3, US-4", 3.13),
        ("Coverage hesapla — US-3", 3.75),
        ("Mutasyon analizi yap — US-5", 4.37),
        ("Toplu test çalıştır,\nrapor al — US-6", 4.99),
        ("Veri setlerini indir ve ayır\n(download, make-splits)", 5.61),
    ]
    boxes = [usecase(d, xa, y, t, w=2.85) for t, y in main]
    for b in boxes:
        link(d, user, b, "line", src=("right", 0.35), dst=("left", 0.5))
    opt = usecase(d, 6.65, 0.95, "Tahmin (opsiyonel,\npuansız)", dashed=True, w=1.95)
    link(d, user, opt, "line", src=("top", 0.5), via=((0.65, 0.95),), dst=("left", 0.5), color=GREY)

    validate = usecase(d, 6.65, 1.6, "Kodu doğrula\n(sözdizimi, satır no.)", w=1.95)
    pick = usecase(d, 6.65, 2.22, "HumanEval görevi seç", w=1.95)
    save = usecase(d, 6.65, 2.85, "Testleri kaydet", w=1.95)
    run = usecase(d, 6.65, 4.1, "Testleri alt süreçte\nçalıştır (coverage)", w=1.95)
    report = usecase(d, 6.65, 4.99, "Rapor yaz\n(CSV / HTML / XLSX)", w=1.95)
    verify = usecase(d, 6.65, 5.61, "SHA-256 ile doğrula", w=1.95)

    def rel(a: Box, b: Box, text: str, at: float = 0.5) -> None:
        link(d, a, b, "dep", label=text, label_at=at, label_dy=-0.06)

    rel(boxes[0], validate, "«include»")
    rel(pick, boxes[1], "«extend»")
    rel(pick, boxes[2], "«extend»")
    rel(save, boxes[3], "«extend»")
    rel(boxes[3], run, "«include»", 0.3)
    rel(boxes[4], run, "«include»", 0.45)
    rel(boxes[5], run, "«include»", 0.45)
    rel(boxes[6], run, "«include»", 0.3)
    rel(boxes[6], report, "«include»")
    rel(boxes[7], verify, "«include»")
    link(
        d,
        hf,
        boxes[7],
        "line",
        src=("left", 0.6),
        via=((8.3, 5.78), (8.3, 5.97), (3.35, 5.97)),
        dst=("bottom", 0.5),
    )
    note(
        d,
        0.08,
        4.35,
        ("Test üretiminde", "LLM kullanılmaz", "(Sözleşme 2.1)."),
        size=FS - 1.5,
    )
    return d.save("01-kullanim-durumu")


# --------------------------------------------------------------------------- 2. paket


def package_diagram() -> Path:
    d = Diagram(9.6, 6.3, "Paket / Bileşen Diyagramı — katmanlar ve import bağımlılıkları")
    bands = [
        (0.45, 1.45, "Sunum"),
        (1.6, 2.5, "Uygulama (Facade)"),
        (2.65, 5.2, "Çekirdek"),
        (5.35, 6.2, "Ortak"),
    ]
    for top, bottom, name in bands:
        d.ax.add_patch(
            Rectangle((0.1, top), 9.4, bottom - top, fc="#FAFBFD", ec="#C9D1E0", lw=0.8, zorder=0)
        )
        d.text(0.18, top + 0.13, name, size=FS - 0.5, color=MUTED, style="italic")

    gui = package(
        d,
        1.3,
        0.8,
        2.6,
        0.55,
        "gui",
        ("PySide6 sayfaları, MainWindow, AppState,", "TaskRunner/Worker, tema"),
    )
    cli = package(
        d, 7.3, 0.8, 2.1, 0.55, "cli", ("testzede download | make-splits", "| batch | gui")
    )
    svc = package(
        d,
        1.55,
        1.95,
        5.35,
        0.45,
        "services",
        (
            "analysis_service · coverage_service · mutation_service",
            "rl_service · batch_service · test_loader · errors",
        ),
    )
    w = 1.45
    batch = package(d, 4.05, 3.0, w, 0.45, "batch", ("runner · report",))
    analysis = package(d, 0.35, 3.85, w, 0.5, "analysis", ("callgraph · metrics", "parsing"))
    prediction = package(d, 2.2, 3.85, w, 0.5, "prediction", ("baseline · learned", "stage"))
    rl = package(d, 4.05, 3.85, w, 0.5, "rl", ("env · agent · actions", "reward · trainer …"))
    mutation = package(d, 5.9, 3.85, w, 0.5, "mutation", ("engine · operators",))
    datasets = package(
        d, 7.75, 3.85, w, 0.5, "datasets", ("factory · loaders", "splits · download")
    )
    execution = package(d, 5.9, 4.7, w, 0.4, "execution", ("sandbox · coverage_runner", "executor"))
    logging_ = package(d, 0.75, 5.75, 1.75, 0.35, "logging_setup", ("Logger (Singleton)",))
    package(d, 3.0, 5.75, 2.4, 0.35, "domain", ("models.py — ortak veri modelleri",))
    package(d, 5.85, 5.75, 1.45, 0.35, "config", ("configs/*.yaml",))

    def dep(a: Box, b: Box, **kw) -> None:
        link(d, a, b, "dep", **kw)

    def at(box: Box, x: float) -> float:
        return (x - box.x) / box.w

    dep(gui, svc, src=("bottom", 0.5), dst=("top", at(svc, 2.6)))
    dep(gui, logging_, src=("left", 0.6), via=((0.22, 1.06), (0.22, 5.93)), dst=("left", 0.6))
    dep(cli, gui, src=("left", 0.6), dst=("right", 0.6), label="tembel import (gui)")
    dep(cli, batch, src=("bottom", 0.06), via=((7.43, 2.78), (5.2, 2.78)), dst=("top", 0.79))
    dep(cli, datasets, src=("bottom", at(cli, 8.95)), dst=("top", at(datasets, 8.95)))
    dep(cli, execution, src=("bottom", at(cli, 7.6)), via=((7.6, 5.0),), dst=("right", 0.75))
    dep(svc, batch, src=("bottom", at(svc, 4.6)), dst=("top", at(batch, 4.6)))
    dep(svc, analysis, src=("bottom", at(svc, 1.75)), dst=("top", 0.7))
    dep(svc, prediction, src=("bottom", at(svc, 2.95)), dst=("top", 0.7))
    dep(
        svc,
        rl,
        src=("bottom", at(svc, 3.9)),
        via=((3.9, 3.57), (4.55, 3.57)),
        dst=("top", at(rl, 4.55)),
    )
    dep(
        svc,
        mutation,
        src=("bottom", at(svc, 6.6)),
        via=((6.6, 3.55), (7.1, 3.55)),
        dst=("top", at(mutation, 7.1)),
    )
    dep(
        svc,
        datasets,
        src=("bottom", at(svc, 6.85)),
        via=((6.85, 2.92), (8.58, 2.92)),
        dst=("top", at(datasets, 8.58)),
    )
    dep(svc, execution, src=("bottom", at(svc, 5.72)), via=((5.72, 4.88),), dst=("left", 0.45))
    dep(batch, analysis, src=("left", 0.4), dst=("top", 0.8))
    dep(batch, prediction, src=("left", 0.85), dst=("top", 0.85))
    dep(batch, rl, src=("bottom", at(batch, 4.95)), dst=("top", at(rl, 4.95)))
    dep(batch, mutation, src=("right", 0.85), via=((6.85, 3.38),), dst=("top", at(mutation, 6.85)))
    dep(batch, datasets, src=("right", 0.4), via=((8.75, 3.18),), dst=("top", at(datasets, 8.75)))
    dep(prediction, rl, src=("right", 0.6), dst=("left", 0.6))
    dep(mutation, execution, src=("bottom", at(mutation, 7.0)), dst=("top", at(execution, 7.0)))
    brown = "#8A5A00"
    dep(rl, execution, src=("bottom", 0.75), via=((5.14, 5.05),), dst=("left", 0.85), color=brown)
    d.text(1.0, 4.82, "rl → execution yalnızca çalışma zamanında:", size=FS - 1.5, color=brown)
    d.text(1.0, 4.95, "rl.executor.Executor (Protocol) yerine", size=FS - 1.5, color=brown)
    d.text(1.0, 5.08, "execution.SandboxExecutor enjekte edilir.", size=FS - 1.5, color=brown)
    note(
        d,
        7.55,
        5.48,
        (
            "domain: tüm paketler import eder.",
            "config: services ve cli import eder.",
            "Ok: import eden → import edilen.",
        ),
        size=FS - 1.5,
    )
    return d.save("02-paket-bilesen")


# --------------------------------------------------------------------------- 3. sınıf


def class_domain() -> Path:
    d = Diagram(9.6, 3.3, "Sınıf Diyagramı (1/6) — domain: modüller arası ortak modeller")
    y = 0.6
    uml_class(
        d,
        0.2,
        y,
        "CodeUnit",
        (
            "uid: str",
            "source: str",
            "entry_point: str | None",
            "dataset: str | None",
            "seed_examples: tuple[str, ...]",
        ),
        stereo="dataclass(frozen)",
    )
    uml_class(
        d,
        2.75,
        y,
        "TestCase",
        ("name: str", "code: str", "origin: 'user' | 'rl'"),
        stereo="dataclass",
    )
    uml_class(
        d,
        4.95,
        y,
        "CoverageReport",
        (
            "covered_lines: int",
            "total_lines: int",
            "covered_branches: int",
            "total_branches: int",
            "per_function: dict[str, float]",
        ),
        ("«property» line_rate: float",),
        stereo="dataclass",
    )
    uml_class(
        d,
        7.6,
        y,
        "MutationReport",
        ("total: int", "killed: int", "survived: int", "timeout: int"),
        ("«property» score: float",),
        stereo="dataclass",
    )
    y2 = 2.05
    uml_class(d, 0.2, y2, "MetricSet", ("values: dict[str, float]",), stereo="dataclass")
    uml_class(
        d,
        2.0,
        y2,
        "RunStats",
        ("generated: int", "compiled: int", "execution_time_s: float"),
        ("«property» compilation_rate: float",),
        stereo="dataclass",
    )
    uml_class(
        d,
        4.35,
        y2,
        "Prediction",
        ("estimated_bugs: float", "optimum_test_count: int", "method: str"),
        stereo="dataclass",
    )
    note(
        d,
        6.3,
        2.05,
        (
            "line_rate = covered_lines / total_lines",
            "score = (killed + timeout) / total",
            "compilation_rate = compiled / generated",
            "(payda 0 ise 0.0)",
            "Modüller arası veri yalnızca bu modellerle taşınır;",
            "alan değişikliği 3 onay ister (ARCHITECTURE §2).",
        ),
    )
    return d.save("03a-sinif-domain")


def class_execution_mutation() -> Path:
    d = Diagram(9.6, 6.0, "Sınıf Diyagramı (2/6) — execution ve mutation")
    sandbox = uml_class(
        d,
        0.2,
        0.6,
        "sandbox",
        ("TARGET_MODULE = 'target'", "GENERATOR_LIMIT = 50"),
        ("call_function(unit, args_repr,", "    timeout=2.0) -> CallResult", "child_env() -> dict"),
        stereo="module",
    )
    call = uml_class(
        d,
        0.2,
        2.15,
        "CallResult",
        (
            "status: ok | raised |",
            "        timeout | error",
            "value_repr: str | None",
            "exc_type: str | None",
            "duration_s: float",
        ),
        stereo="dataclass(frozen)",
    )
    runner = uml_class(
        d,
        2.75,
        0.6,
        "coverage_runner",
        ("Outcome = passed | failed |", "          error | timeout"),
        (
            "run_tests(unit, tests,",
            "    timeout=10.0) -> ExecutionResult",
            "run_outcomes(unit, tests,",
            "    timeout=10.0) -> dict[str, Outcome]",
        ),
        stereo="module",
    )
    result = uml_class(
        d,
        2.75,
        2.35,
        "ExecutionResult",
        (
            "coverage: CoverageReport",
            "stats: RunStats",
            "covered_lines: frozenset[int]",
            "covered_branches: frozenset",
            "all_lines / all_branches",
            "test_outcomes: dict[str, Outcome]",
        ),
        stereo="dataclass",
    )
    executor = uml_class(
        d,
        5.75,
        0.6,
        "SandboxExecutor",
        (),
        (
            "call_function(unit, args_repr,",
            "    timeout=2.0) -> CallResult",
            "run_tests(unit, tests,",
            "    timeout=10.0) -> ExecutionResult",
        ),
    )
    proto = uml_class(
        d,
        5.75,
        2.0,
        "rl.executor.Executor",
        (),
        ("call_function(...)", "run_tests(...)"),
        stereo="interface (Protocol)",
    )
    link(d, sandbox, call, "dep", label="döndürür")
    link(d, runner, result, "dep", label="döndürür")
    link(
        d,
        executor,
        sandbox,
        "dep",
        src=("top", 0.3),
        via=((executor.x + executor.w * 0.3, 0.45), (1.3, 0.45)),
        dst=("top", 0.5),
        label="kullanır",
        label_at=0.5,
    )
    link(d, executor, runner, "dep", src=("left", 0.75), dst=("right", 0.85))
    link(d, executor, proto, "realize", label="yapısal olarak uyar")

    engine = uml_class(
        d,
        0.2,
        3.75,
        "MutationEngine",
        (
            "_max_mutants: int | None = 100",
            "_seed: int = 0",
            "_max_total_seconds = 120.0",
            "_workers = clamp(cpu-2, 1, 6)",
        ),
        (
            "run(source, tests, progress, cancel)",
            "    -> (MutationReport, RunStats)",
            "run_detailed(...) -> MutationRun",
            "_run_parallel(...)  # ThreadPool",
            "_check_baseline(baseline) -> set",
            "_sample(mutants) -> list",
        ),
    )
    run = uml_class(
        d,
        3.35,
        4.35,
        "MutationRun",
        (
            "report: MutationReport",
            "stats: RunStats",
            "survivors: list[Mutant]",
            "skipped_uncovered: int = 0",
        ),
        stereo="dataclass(frozen)",
    )
    mutant = uml_class(
        d,
        5.6,
        4.55,
        "Mutant",
        ("operator: str", "line: int", "description: str", "source: str"),
        stereo="dataclass(frozen)",
    )
    op = uml_class(
        d,
        7.55,
        2.9,
        "MutationOperator",
        ("name: str",),
        ("generate(source) -> list[Mutant]",),
        stereo="abstract (ABC)",
        abstract=True,
    )
    site = uml_class(d, 7.55, 3.95, "_SiteOperator", (), ("_sites(tree)", "generate(source)"))
    concrete = uml_class(
        d,
        7.55,
        4.95,
        "AOR · ROR · COR",
        ("ConstantReplacement (CONST)", "ReturnNone (RETURN_NONE)"),
        min_w=site.w,
    )
    link(d, site, op, "inherit")
    link(d, concrete, site, "inherit")
    link(d, engine, run, "dep", label="üretir", src=("right", 0.62))
    link(d, run, mutant, "compose", mult=(None, "0..*"), src=("right", 0.55))
    link(d, op, mutant, "dep", src=("bottom", 0.1), dst=("top", 0.8), label="üretir")
    link(
        d,
        engine,
        runner,
        "dep",
        src=("top", (2.3 - engine.x) / engine.w),
        via=((2.3, 2.1), (2.95, 2.1)),
        dst=("bottom", (2.95 - runner.x) / runner.w),
    )
    d.text(2.22, 3.35, "baseline: run_tests", size=FS - 1, ha="right", color=MUTED)
    d.text(2.22, 3.5, "mutant: run_outcomes", size=FS - 1, ha="right", color=MUTED)
    note(
        d,
        5.0,
        3.25,
        (
            "Strategy: generate_all(source) tüm",
            "operatörleri sırayla uygular;",
            "aynı kaynaklar tekilleşir.",
        ),
        targets=(op.side("left", 0.5),),
    )
    return d.save("03b-sinif-execution-mutation")


def class_rl() -> Path:
    d = Diagram(9.6, 6.15, "Sınıf Diyagramı (3/6) — rl: Q-learning ile test üretimi")
    cfg = uml_class(
        d,
        0.2,
        0.55,
        "EnvConfig",
        (
            "max_steps = 50",
            "patience = 10",
            "bins = 5",
            "call_timeout_s = 2.0",
            "run_timeout_s = 10.0",
        ),
        stereo="dataclass(frozen)",
    )
    ep = uml_class(
        d,
        0.2,
        1.95,
        "EpisodeState",
        (
            "tests: list[TestCase]",
            "covered_lines / all_lines",
            "covered_branches / all_branches",
            "seen_classes: set[str]",
            "curve: list[CurvePoint]",
            "best_input / best_gain",
            "generated / compiled",
            "step / stale_steps / last_ok",
        ),
        ("report() -> CoverageReport", "stats() -> RunStats"),
        stereo="dataclass",
    )
    curve = uml_class(
        d,
        0.2,
        4.3,
        "CurvePoint",
        ("step / tests: int", "line_rate / branch_rate"),
        stereo="dataclass(frozen)",
    )
    env = uml_class(
        d,
        2.65,
        0.55,
        "TestGenEnv",
        (
            "unit: CodeUnit",
            "executor: Executor",
            "weights: RewardWeights",
            "config: EnvConfig",
            "baseline: Sequence[TestCase]",
            "episode: EpisodeState",
        ),
        (
            "reset(seed) -> (obs, info)",
            "step(action) -> (obs, reward,",
            "    terminated, truncated, info)",
            "observe() -> int",
            "baseline_run()",
            "«property» fully_covered",
            "_run_action(action)",
        ),
    )
    ctx = uml_class(
        d,
        2.65,
        3.2,
        "ActionContext",
        ("params · seed_inputs · best_input",),
        stereo="dataclass(frozen)",
    )
    action = uml_class(
        d,
        2.65,
        4.0,
        "Action",
        ("name: str",),
        ("generate(ctx, rng) -> tuple | None", "value(spec, rng)"),
        stereo="abstract (ABC)",
        abstract=True,
    )
    value = uml_class(
        d,
        1.95,
        5.2,
        "_ValueAction (+6 alt sınıf)",
        ("BOUNDARY · EMPTY · NEGATIVE", "RANDOM_SMALL · RANDOM_LARGE", "SPECIAL_CHARS"),
    )
    docs = uml_class(d, 4.05, 5.2, "FromDocstring", ("FROM_DOCSTRING",))
    best = uml_class(d, 5.35, 5.2, "MutateBest", ("MUTATE_BEST",))
    proto = uml_class(
        d,
        5.35,
        0.55,
        "Executor",
        (),
        (
            "call_function(unit, args_repr,",
            "    timeout) -> CallOutcome",
            "run_tests(unit, tests,",
            "    timeout) -> TestRunOutcome",
        ),
        stereo="interface (Protocol)",
    )
    agent = uml_class(
        d,
        5.35,
        1.6,
        "QLearningAgent",
        (
            "q: ndarray[n_states, n_actions]",
            "learning_rate = 0.1",
            "discount = 0.9",
            "epsilon_greedy = 0.2",
        ),
        ("select_action(state, greedy) -> int", "update(s, a, r, s2, done)"),
    )
    reward = uml_class(
        d,
        5.35,
        3.3,
        "RewardWeights",
        (
            "alpha = 1.0   (Δline)",
            "beta = 2.0    (Δbranch)",
            "gamma = 0.5   (yeni çıktı)",
            "delta = 1.0   (geçersiz)",
            "epsilon = 0.05 (test başı)",
        ),
        stereo="dataclass(frozen)",
    )
    state = uml_class(
        d,
        8.15,
        3.3,
        "State",
        ("line_bin", "branch_bin", "last_ok", "step_bin"),
        stereo="frozen",
    )
    trainer = uml_class(
        d,
        7.85,
        0.55,
        "trainer",
        (),
        (
            "run_episode(env,",
            "    agent)",
            "generate_tests(",
            "    unit, executor,",
            "    config, agent,",
            "    seed, baseline)",
            "  -> EpisodeResult",
        ),
        stereo="module",
    )
    rlcfg = uml_class(
        d,
        7.45,
        4.45,
        "RLConfig",
        ("weights · env · agent", "episodes: int = 1"),
        ("from_mapping(config)", "make_agent(seed)", "  -> QLearningAgent"),
        stereo="dataclass(frozen)",
    )
    link(d, env, cfg, "assoc", src=("left", 0.12), dst=("right", 0.25))
    link(d, env, ep, "compose", src=("left", 0.62), dst=("right", 0.2), mult=(None, "1"))
    link(d, ep, curve, "compose", mult=(None, "0..*"))
    link(d, env, proto, "assoc", src=("right", 0.12), dst=("left", 0.4), label="executor")
    link(d, env, ctx, "dep", src=("bottom", 0.35), dst=("top", 0.35), label="kurar", label_dy=0.0)
    link(d, ctx, action, "line", src=("bottom", 0.5), dst=("top", 0.5))
    link(d, value, action, "inherit", src=("top", 0.6), dst=("bottom", 0.25))
    link(d, docs, action, "inherit", src=("top", 0.4), dst=("bottom", 0.75))
    link(
        d,
        best,
        action,
        "inherit",
        src=("top", 0.3),
        via=((best.x + best.w * 0.3, 5.05), (action.x + action.w * 0.92, 5.05)),
        dst=("bottom", 0.92),
    )
    link(
        d,
        env,
        reward,
        "assoc",
        src=("bottom", 0.8),
        via=((env.x + env.w * 0.8, 3.05), (5.1, 3.05), (5.1, 3.6)),
        dst=("left", 0.25),
    )
    link(
        d,
        env,
        state,
        "dep",
        src=("bottom", 0.95),
        via=((env.x + env.w * 0.95, 2.97), (8.55, 2.97)),
        dst=("top", (8.55 - 8.15) / state.w),
        label="discretize() → state_index()",
        label_at=0.55,
    )
    link(
        d,
        trainer,
        env,
        "dep",
        src=("top", 0.3),
        via=((trainer.x + trainer.w * 0.3, 0.43), (3.7, 0.43)),
        dst=("top", (3.7 - env.x) / env.w),
        label="TestGenEnv(...)",
    )
    link(
        d,
        trainer,
        agent,
        "dep",
        src=("bottom", 0.5),
        via=((trainer.x + trainer.w * 0.5, 2.2),),
        dst=("right", 0.53),
        label="run_episode",
    )
    link(d, rlcfg, reward, "assoc", src=("left", 0.3), dst=("right", 0.8))
    note(
        d,
        6.45,
        5.7,
        ("Strategy: 8 eylem ACTION_REGISTRY'de;", "ajan eylemi indeksle seçer."),
        size=FS - 1.5,
    )
    return d.save("03c-sinif-rl")


def class_datasets_batch() -> Path:
    d = Diagram(9.6, 5.95, "Sınıf Diyagramı (4/6) — datasets ve batch")
    loader = uml_class(
        d,
        0.2,
        0.55,
        "DatasetLoader",
        ("name: ClassVar[str]", "data_dir: Path"),
        (
            "load() -> LoadResult",
            "source_files() -> list[Path]",
            "__iter__() -> Iterator[CodeUnit]",
        ),
        stereo="abstract (ABC)",
        abstract=True,
    )
    factory = uml_class(
        d,
        2.6,
        0.55,
        "DatasetFactory",
        ("_loaders: dict[str, type]",),
        ("register(loader)", "names() -> list[str]", "get(name, data_dir)", "  -> DatasetLoader"),
    )
    he = uml_class(d, 0.2, 2.25, "HumanEvalLoader", ("name = 'humaneval'",))
    s67 = uml_class(d, 1.62, 2.25, "Small67Loader", ("name = 'small67'",))
    tgb = uml_class(d, 2.85, 2.25, "_TestGenEvalBase", ("splits: ClassVar",), ("row_keys()",))
    tg = uml_class(d, 1.35, 3.3, "TestGenEvalLoader", ("name = 'testgeneval'",))
    tgl = uml_class(d, 2.85, 3.3, "TestGenEvalLiteLoader", ("name = 'testgeneval-lite'",))
    result = uml_class(
        d,
        0.2,
        4.15,
        "LoadResult",
        (
            "dataset: str",
            "units: tuple[CodeUnit]",
            "skipped: tuple[Skipped…]",
            "stats: Mapping[str, int]",
        ),
        ("skip_counts()",),
        stereo="dataclass(frozen)",
    )
    skipped = uml_class(d, 2.25, 4.15, "SkippedUnit", ("uid · reason · detail",), stereo="frozen")
    split = uml_class(
        d,
        2.25,
        4.8,
        "SplitDefinition",
        (
            "name · units · sources (SHA-256)",
            "strict_files · missing_datasets",
            "stats · extractor_version",
        ),
        ("to_json() / from_json()",),
        stereo="dataclass(frozen)",
    )
    link(d, he, loader, "inherit", src=("top", 0.5), dst=("bottom", 0.32))
    link(d, s67, loader, "inherit", src=("top", 0.4), dst=("bottom", 0.82))
    link(
        d,
        tgb,
        loader,
        "inherit",
        src=("top", 0.3),
        via=((tgb.x + tgb.w * 0.3, 2.05), (loader.x + loader.w * 0.95, 2.05)),
        dst=("bottom", 0.95),
    )
    link(
        d,
        tg,
        tgb,
        "inherit",
        src=("top", 0.8),
        via=((tg.x + tg.w * 0.8, 3.12), (tgb.x + tgb.w * 0.2, 3.12)),
        dst=("bottom", 0.2),
    )
    link(
        d,
        tgl,
        tgb,
        "inherit",
        src=("top", 0.3),
        dst=("bottom", (tgl.x + tgl.w * 0.3 - tgb.x) / tgb.w),
    )
    link(d, factory, loader, "dep", src=("left", 0.4), dst=("right", 0.27), label="get()")
    link(
        d,
        loader,
        result,
        "dep",
        src=("left", 0.6),
        via=((0.1, loader.y + loader.h * 0.6), (0.1, 4.5)),
        dst=("left", 0.33),
    )
    d.text(0.14, 3.9, "load()", size=FS - 1, color=MUTED)
    link(d, result, skipped, "compose", src=("right", 0.2), dst=("left", 0.4), mult=(None, "0..*"))
    note(
        d,
        2.6,
        1.62,
        ("Factory: get(name) adına göre", "kayıtlı yükleyiciyi örnekler"),
        size=FS - 1.5,
        targets=(factory.side("bottom", 0.5),),
    )

    cfg = uml_class(
        d,
        4.85,
        0.55,
        "BatchConfig",
        (
            "rl: RLConfig",
            "seed: int | None = 0",
            "share_agent: bool = True",
            "suite_timeout_s: float = 60.0",
            "mutation: MutationStage | None",
            "prediction: PredictionStage | None",
        ),
        ("from_mapping(config)",),
        stereo="dataclass(frozen)",
    )
    runner = uml_class(
        d,
        4.85,
        2.35,
        "runner",
        (),
        (
            "run_split(split, executor, config)",
            "run_dataset(dataset, executor, config)",
            "run_batch(units, ...)",
            "    -> (results, stopped)",
            "run_unit(...) -> UnitResult",
            "measure_suite(unit, tests, executor)",
            "mutation_stage(engine)",
        ),
        stereo="module",
    )
    outcome = uml_class(
        d,
        4.85,
        4.3,
        "BatchOutcome",
        ("results: list[UnitResult]", "reports: dict[str, list[Path]]", "stopped: bool"),
        stereo="dataclass",
    )
    unit = uml_class(
        d,
        7.65,
        4.3,
        "UnitResult",
        (
            "uid · dataset",
            "test_count",
            "metrics · coverage",
            "mutation · stats",
            "prediction",
            "error: str | None",
        ),
        stereo="dataclass",
    )
    meta = uml_class(
        d,
        8.35,
        0.55,
        "ReportMeta",
        ("dataset", "split", "split_hash", "config", "created_at"),
        stereo="frozen",
    )
    report = uml_class(
        d,
        7.85,
        2.35,
        "report",
        (),
        (
            "write_report(results,",
            "  out_dir, meta, formats)",
            "to_frame(results)",
            "summarize(frame)",
        ),
        stereo="module",
    )
    link(
        d,
        runner,
        cfg,
        "dep",
        src=("top", 0.4),
        dst=("bottom", (runner.x + runner.w * 0.4 - cfg.x) / cfg.w),
        label="okur",
    )
    link(
        d,
        runner,
        outcome,
        "dep",
        src=("bottom", 0.3),
        dst=("top", (runner.x + runner.w * 0.3 - outcome.x) / outcome.w),
        label="döndürür",
    )
    link(d, outcome, unit, "compose", src=("right", 0.3), dst=("left", 0.2), mult=(None, "0..*"))
    link(d, runner, report, "dep", src=("right", 0.25), dst=("left", 0.3), label="yazar")
    link(
        d,
        report,
        meta,
        "dep",
        src=("top", 0.7),
        dst=("bottom", (report.x + report.w * 0.7 - meta.x) / meta.w),
    )
    link(
        d,
        runner,
        factory,
        "dep",
        src=("left", 0.2),
        via=((4.7, runner.y + runner.h * 0.2), (4.7, 1.15)),
        dst=("right", 0.6),
        label="run_dataset",
        label_at=0.45,
    )
    link(d, runner, split, "dep", src=("left", 0.8), dst=("right", 0.35), label="load_split_units")
    return d.save("03d-sinif-datasets-batch")


def class_services() -> Path:
    d = Diagram(9.6, 5.25, "Sınıf Diyagramı (5/6) — services: GUI ile çekirdek arasındaki cephe")
    uml_class(
        d,
        0.2,
        0.55,
        "AnalysisService",
        ("data_dir: Path",),
        (
            "call_graph(source) -> CallGraphView",
            "metrics(source) -> MetricsView",
            "prediction(source) -> PredictionView",
            "export_metrics_csv(view, path)",
            "humaneval_available() -> bool",
            "humaneval_tasks() -> list[SampleTask]",
        ),
    )
    batch = uml_class(
        d,
        0.2,
        2.3,
        "batch_service",
        (),
        (
            "targets(data_dir) -> list[Target]",
            "run(target, ..., progress,",
            "    should_stop) -> BatchOutcome",
        ),
        stereo="module",
    )
    target = uml_class(
        d,
        0.2,
        3.6,
        "Target",
        ("kind: 'split' | 'dataset'", "name: str", "available: bool"),
        ("«property» label",),
        stereo="dataclass(frozen)",
    )
    uml_class(
        d,
        2.95,
        0.55,
        "CoverageService",
        (),
        ("run(source, tests,", "    timeout=10.0) -> ExecutionResult"),
    )
    mutation = uml_class(
        d,
        2.95,
        1.5,
        "MutationService",
        ("_engine: MutationEngine | None",),
        ("run(source, tests, progress, cancel)", "run_detailed(...) -> MutationRun"),
    )
    proto = uml_class(
        d,
        2.95,
        2.75,
        "MutationEngine",
        (),
        ("run(...)", "run_detailed(...)"),
        stereo="interface (Protocol)",
    )
    core = uml_class(
        d,
        2.95,
        3.85,
        "mutation.engine.MutationEngine",
        (),
        ("create_mutation_service(max_mutants=100)", "  bu motoru bağlar"),
        fill="#F2F2F2",
    )
    rl = uml_class(
        d,
        5.85,
        0.55,
        "rl_service",
        ("USER_UID = 'user/kod'",),
        (
            "list_functions(source) -> list[str]",
            "build_unit(source, entry_point)",
            "load_rl_config(path) -> RLConfig",
            "generate(source, entry_point, ...)",
            "    -> GenerationResult",
            "tests_module(result, module_name)",
        ),
        stereo="module",
    )
    gen = uml_class(
        d,
        5.85,
        2.4,
        "GenerationResult",
        ("unit · tests · coverage · stats", "curve · steps · baseline", "user_outcome: str | None"),
        stereo="dataclass",
    )
    uml_class(
        d,
        5.85,
        3.55,
        "test_loader",
        (),
        ("load_tests(test_source,", "    module_name) -> list[TestCase]"),
        stereo="module",
    )
    uml_class(d, 8.45, 2.4, "ServiceError", ("message: str",), stereo="Exception")
    link(d, mutation, proto, "assoc", label="_engine")
    link(d, core, proto, "realize", label="yapısal olarak uyar")
    link(d, rl, gen, "dep", label="döndürür")
    link(d, batch, target, "dep")
    note(
        d,
        5.85,
        4.45,
        (
            "Facade: her servis çekirdeğin bir alt kümesini GUI'ye tek",
            "giriş noktası olarak sunar. Çekirdek hataları (MutationError,",
            "DatasetError, SignatureError …) ServiceError'a çevrilir;",
            "Worker bu mesajı kullanıcıya olduğu gibi gösterir.",
        ),
        size=FS - 1,
    )
    return d.save("03e-sinif-services")


def class_gui() -> Path:
    d = Diagram(
        9.6, 6.45, "Sınıf Diyagramı (6/6) — gui: sayfalar, paylaşılan durum ve arka plan işleri"
    )
    window = uml_class(
        d,
        0.2,
        0.6,
        "MainWindow",
        (
            "state: AppState",
            "pages: list[BasePage]",
            "nav: QListWidget",
            "stack: QStackedWidget",
            "theme_switch: ThemeSwitch",
        ),
        (
            "page(title) -> BasePage",
            "_on_row_changed(row)",
            "  → stack + on_enter()",
            "closeEvent(e) → shutdown()",
        ),
        stereo="QMainWindow",
    )
    state = uml_class(
        d,
        2.85,
        0.6,
        "AppState",
        (
            "source: str",
            "tests: list[TestCase]",
            "execution_result",
            "mutation_run",
            "module_name: str | None",
        ),
        ("reset()",),
        stereo="dataclass",
    )
    theme = uml_class(
        d, 4.85, 0.6, "ThemeSwitch", (), ("switch(name, animate)",), stereo="QToolButton"
    )
    logger = uml_class(
        d,
        7.65,
        0.6,
        "Logger",
        ("_instance: Logger | None",),
        ("__new__() -> tek örnek", "configure(path)", "«property» logger"),
        stereo="Singleton",
    )
    handler = uml_class(
        d,
        7.65,
        1.85,
        "error_handler",
        (),
        ("install_global_handler()", "handle_exception(", "  type, exc, tb)"),
        stereo="module",
    )
    base = uml_class(
        d,
        2.85,
        2.45,
        "BasePage",
        ("title: str", "state: AppState"),
        ("on_enter()",),
        stereo="QWidget",
    )
    analysis = uml_class(
        d,
        5.1,
        2.45,
        "AnalysisPage",
        ("picker: SourcePicker", "_tasks: TaskRunner"),
        ("_compute(source)  «abstract»", "_render(result, label)", "run()"),
    )
    code = uml_class(
        d,
        0.2,
        3.6,
        "CodePage",
        (),
        (
            "validate() / validate_tests()",
            "load_file(path)",
            "(TaskRunner yok; 400 ms",
            " gecikmeli doğrulama)",
        ),
    )
    tasks = uml_class(
        d,
        2.45,
        3.6,
        "CoveragePage · MutationPage",
        ("RLPage · BatchPage",),
        ("_tasks: TaskRunner", "shutdown()"),
    )
    subs = uml_class(
        d,
        7.3,
        3.6,
        "CallGraphPage",
        ("MetricsPage", "PredictionPage"),
    )
    runner = uml_class(
        d,
        3.2,
        4.75,
        "TaskRunner",
        ("_thread: QThread | None", "_worker: Worker | None"),
        (
            "«property» busy",
            "start(job, on_finished,",
            "  on_failed, on_progress)",
            "request_stop()",
            "shutdown(timeout_ms)",
        ),
        stereo="QObject",
    )
    worker = uml_class(
        d,
        0.2,
        4.75,
        "Worker",
        ("«signal» progress(object)", "«signal» finished(object)", "«signal» failed(str)"),
        ("report(value)", "stop_requested() -> bool", "run()"),
        stereo="QObject",
    )
    link(d, window, state, "compose", src=("right", 0.15), dst=("left", 0.15), mult=(None, "1"))
    link(d, window, base, "compose", src=("right", 0.8), dst=("left", 0.3), mult=(None, "8"))
    link(
        d,
        window,
        theme,
        "compose",
        src=("top", 0.75),
        via=((window.x + window.w * 0.75, 0.47), (theme.x + theme.w * 0.5, 0.47)),
        dst=("top", 0.5),
    )
    link(
        d,
        base,
        state,
        "assoc",
        src=("top", 0.5),
        dst=("bottom", (base.x + base.w * 0.5 - state.x) / state.w),
        label="paylaşır",
    )
    link(d, analysis, base, "inherit", src=("left", 0.3), dst=("right", 0.3))
    link(d, code, base, "inherit", src=("top", 0.6), dst=("bottom", 0.15))
    link(
        d,
        tasks,
        base,
        "inherit",
        src=("top", 0.55),
        dst=("bottom", (tasks.x + tasks.w * 0.55 - base.x) / base.w),
    )
    link(d, subs, analysis, "inherit", src=("top", 0.3), dst=("right", 0.75))
    link(
        d,
        tasks,
        runner,
        "compose",
        src=("bottom", 0.6),
        dst=("top", (tasks.x + tasks.w * 0.6 - runner.x) / runner.w),
        label="_tasks",
        label_dy=0.0,
    )
    link(
        d,
        analysis,
        runner,
        "compose",
        src=("bottom", 0.3),
        via=((analysis.x + analysis.w * 0.3, 4.6), (runner.x + runner.w * 0.85, 4.6)),
        dst=("top", 0.85),
    )
    link(d, runner, worker, "compose", src=("left", 0.3), dst=("right", 0.3), mult=(None, "0..1"))
    link(
        d,
        handler,
        logger,
        "dep",
        src=("top", 0.5),
        dst=("bottom", (handler.x + handler.w * 0.5 - logger.x) / logger.w),
    )
    note(
        d,
        6.0,
        4.85,
        (
            "Observer: Worker QThread'de çalışır, sonucu",
            "Qt sinyalleriyle bildirir; GUI iş parçacığı",
            "bloklanmaz. Sayfalar yalnızca services/",
            "cephelerini çağırır (çekirdek importları",
            "yalnızca TYPE_CHECKING altında).",
        ),
        size=FS - 1,
    )
    return d.save("03f-sinif-gui")


# --------------------------------------------------------------------------- 4. sıralama


class Sequence:
    def __init__(
        self,
        d: Diagram,
        parts: list[tuple[str, str]],
        *,
        x0: float,
        dx: float,
        top: float,
        bottom: float,
        actor_keys: tuple[str, ...] = (),
    ) -> None:
        self.d = d
        self.x: dict[str, float] = {}
        for i, (key, label) in enumerate(parts):
            x = x0 + i * dx
            self.x[key] = x
            if key in actor_keys:
                actor(d, x, top + 0.2, label)
                start = top + 0.85
            else:
                lines = label.split("\n")
                w = min(dx - 0.08, max(text_width(s, FS - 0.5) for s in lines) + 0.16)
                h = LINE * len(lines) + 0.12
                d.ax.add_patch(Rectangle((x - w / 2, top), w, h, fc=HEAD, ec=INK, lw=0.9, zorder=4))
                d.text(x, top + h / 2, label, size=FS - 0.5, ha="center", weight="bold")
                start = top + h
            d.line([(x, start), (x, bottom)], dashed=True, color=GREY, lw=0.7, zorder=1)

    def act(self, key: str, y1: float, y2: float, level: int = 0) -> None:
        x = self.x[key] + level * 0.05
        self.d.ax.add_patch(
            Rectangle((x - 0.05, y1), 0.1, y2 - y1, fc="white", ec=INK, lw=0.8, zorder=3)
        )

    def msg(
        self,
        y: float,
        a: str,
        b: str,
        text: str,
        *,
        ret: bool = False,
        size: float = FS - 1,
        la: int = 0,
        lb: int = 0,
    ) -> None:
        xa, xb = self.x[a] + la * 0.05, self.x[b] + lb * 0.05
        if a == b:
            pts = [(xa + 0.05, y), (xa + 0.35, y), (xa + 0.35, y + 0.15), (xa + 0.1, y + 0.15)]
            self.d.line(pts, dashed=ret)
            self.d.head(pts[-1], pts[-2], "open")
            self.d.text(xa + 0.4, y + 0.07, text, size=size, color="#222222")
            return
        sign = 1 if xb > xa else -1
        p = (xa + 0.05 * sign, y)
        q = (xb - 0.05 * sign, y)
        self.d.line([p, q], dashed=ret)
        self.d.head(q, p, "open" if ret else "filled")
        self.d.text(
            (p[0] + q[0]) / 2,
            y - 0.075,
            text,
            size=size,
            ha="center",
            color=MUTED if ret else "#222222",
            bg="white",
        )

    def frag(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        label: str,
        guard: str = "",
        splits: tuple[tuple[float, str], ...] = (),
    ) -> None:
        d = self.d
        d.ax.add_patch(Rectangle((x1, y1), x2 - x1, y2 - y1, fc="none", ec=INK, lw=0.8, zorder=2))
        w = text_width(label, FS - 1, SANS, "bold") + 0.16
        pts = [
            (x1, y1),
            (x1 + w, y1),
            (x1 + w, y1 + 0.1),
            (x1 + w - 0.06, y1 + 0.16),
            (x1, y1 + 0.16),
        ]
        d.ax.add_patch(Polygon(pts, closed=True, fc=HEAD, ec=INK, lw=0.8, zorder=2))
        d.text(x1 + 0.05, y1 + 0.08, label, size=FS - 1, weight="bold")
        if guard:
            d.text(x1 + w + 0.06, y1 + 0.09, guard, size=FS - 1.5, color=MUTED, style="italic")
        for yy, g in splits:
            d.line([(x1, yy), (x2, yy)], dashed=True, lw=0.7)
            d.text(x1 + 0.06, yy + 0.09, g, size=FS - 1.5, color=MUTED, style="italic")


def sequence_batch() -> Path:
    d = Diagram(9.6, 8.25, "Sıralama Diyagramı (1/3) — uçtan uca hat: bir birim için toplu test")
    parts = [
        ("u", "Kullanıcı"),
        ("page", "BatchPage"),
        ("worker", "Worker\n(QThread)"),
        ("svc", "batch_service"),
        ("run", "batch.runner"),
        ("rl", "trainer +\nTestGenEnv"),
        ("ex", "Sandbox-\nExecutor"),
        ("sub", "alt süreç\n(python -I)"),
        ("mut", "Mutation-\nEngine"),
        ("rep", "batch.report"),
    ]
    s = Sequence(d, parts, x0=0.45, dx=0.97, top=0.5, bottom=8.15, actor_keys=("u",))
    step = 0.26
    y = 1.45
    s.msg(y, "u", "page", "Başlat")
    page_y = y
    y += step
    s.msg(y, "page", "worker", "start(job)")
    worker_y = y
    y += step
    s.msg(y, "worker", "svc", "run(target, limit, …)")
    svc_y = y
    y += step
    s.msg(y, "svc", "run", "run_split / run_dataset")
    run_y = y
    outer = y + 0.1
    y += step + 0.12
    s.msg(y, "run", "run", "compute_metrics(source)")
    y += step + 0.12
    s.msg(y, "run", "rl", "generate_tests(unit, executor, cfg, agent, seed)")
    rl_y = y
    inner = y + 0.1
    y += step + 0.12
    s.msg(y, "rl", "ex", "call_function()  oracle")
    s.act("ex", y, y + step + 0.04)
    y += step
    s.msg(y, "ex", "sub", "subprocess.run(timeout=2)")
    y += step
    s.msg(y, "ex", "rl", "CallResult", ret=True)
    y += step
    s.msg(y, "rl", "rl", "synthesize() → TestCase")
    y += step + 0.12
    s.msg(y, "rl", "ex", "run_tests(unit, [test])")
    s.act("ex", y, y + step + 0.04)
    y += step
    s.msg(y, "ex", "sub", "coverage run --branch -m pytest")
    y += step
    s.msg(y, "ex", "rl", "ExecutionResult", ret=True)
    y += 0.1
    s.frag(
        4.95,
        inner,
        7.75,
        y,
        "loop",
        "[her adım; epizot × config.episodes]",
    )
    y += step
    s.msg(y, "rl", "run", "EpisodeResult", ret=True)
    s.act("rl", rl_y, y)
    y += step
    s.msg(y, "run", "ex", "measure_suite: run_tests(tests, 60 sn)")
    y += step
    s.msg(y, "run", "mut", "mutation_stage: run_detailed(source, tests)")
    s.act("mut", y, y + step + 0.04)
    y += step
    s.msg(y, "mut", "sub", "run_outcomes × mutant (paralel)")
    y += step
    s.msg(y, "mut", "run", "MutationReport", ret=True)
    y += step
    s.msg(y, "run", "worker", "progress(i, n, UnitResult)", ret=True)
    y += 0.1
    s.frag(3.55, outer, 9.3, y, "loop", "[her birim; önce should_stop() sorulur]")
    y += step
    s.msg(y, "run", "rep", "write_report(results, out_dir, meta, formats)")
    y += step
    s.msg(y, "run", "svc", "BatchOutcome", ret=True)
    s.act("run", run_y, y)
    y += step
    s.msg(y, "svc", "worker", "BatchOutcome", ret=True)
    s.act("svc", svc_y, y)
    y += step
    s.msg(y, "worker", "page", "finished(BatchOutcome) sinyali", ret=True)
    s.act("worker", worker_y, y)
    s.act("page", page_y, y + 0.15)
    return d.save("04a-sirali-toplu-hat")


def sequence_gui() -> Path:
    d = Diagram(9.6, 6.2, "Sıralama Diyagramı (2/3) — arayüzde kod yükle → coverage → mutasyon")
    parts = [
        ("u", "Kullanıcı"),
        ("code", "CodePage"),
        ("state", "AppState"),
        ("cov", "CoveragePage"),
        ("mutp", "MutationPage"),
        ("worker", "TaskRunner /\nWorker"),
        ("csvc", "CoverageService"),
        ("msvc", "MutationService\n→ MutationEngine"),
        ("runner", "coverage_runner\n(alt süreç)"),
    ]
    s = Sequence(d, parts, x0=0.45, dx=1.05, top=0.5, bottom=6.1, actor_keys=("u",))
    y = 1.45
    s.msg(y, "u", "code", "kaynak + test kodu yapıştır / Dosya Aç")
    s.act("code", y, y + 0.8)
    y += 0.25
    s.msg(y, "code", "code", "check_source(), load_tests()  (400 ms gecikmeli)")
    y += 0.33
    s.msg(y, "code", "state", "source, tests, module_name yaz")
    y += 0.4
    s.msg(y, "u", "cov", "Çalıştır")
    s.act("cov", y, y + 1.3)
    y += 0.25
    s.msg(y, "cov", "state", "source, tests oku")
    y += 0.25
    s.msg(y, "cov", "worker", "start(job)")
    s.act("worker", y, y + 0.7)
    y += 0.22
    s.msg(y, "worker", "csvc", "run(source, tests, timeout=10)")
    s.act("csvc", y, y + 0.35)
    s.msg(y + 0.17, "csvc", "runner", "run_tests(unit, tests)")
    y += 0.37
    s.msg(y, "csvc", "worker", "ExecutionResult", ret=True)
    y += 0.2
    s.msg(y, "worker", "cov", "finished(result)", ret=True)
    y += 0.25
    s.msg(y, "cov", "state", "execution_result yaz; tabloyu ve renkli satırları çiz")
    y += 0.42
    s.msg(y, "u", "mutp", "Çalıştır (en fazla N mutant, varsayılan 100)")
    s.act("mutp", y, y + 1.3)
    y += 0.25
    s.msg(y, "mutp", "worker", "start(job, on_progress)")
    s.act("worker", y, y + 0.75)
    y += 0.22
    s.msg(y, "worker", "msvc", "run_detailed(source, tests, progress, cancel)")
    s.act("msvc", y, y + 0.45)
    s.msg(y + 0.2, "msvc", "runner", "baseline + run_outcomes × mutant")
    y += 0.42
    s.msg(y, "msvc", "worker", "MutationRun", ret=True)
    y += 0.2
    s.msg(y, "worker", "mutp", "progress(biten, toplam) … finished(run)", ret=True)
    y += 0.25
    s.msg(y, "mutp", "state", "mutation_run yaz; skor ve hayatta kalanları göster")
    return d.save("04b-sirali-arayuz")


def sequence_errors() -> Path:
    d = Diagram(9.6, 6.3, "Sıralama Diyagramı (3/3) — hata ve zaman aşımı akışı")
    parts = [
        ("u", "Kullanıcı"),
        ("page", "CoveragePage"),
        ("worker", "Worker\n(QThread)"),
        ("svc", "CoverageService"),
        ("runner", "coverage_runner"),
        ("sub", "alt süreç\n(pytest)"),
        ("hook", "error_handler\n(sys.excepthook)"),
    ]
    s = Sequence(d, parts, x0=0.5, dx=1.42, top=0.5, bottom=6.2, actor_keys=("u",))
    y = 1.45
    s.msg(y, "u", "page", "Çalıştır (T3: sonsuz döngülü test)")
    page_y = y
    y += 0.25
    s.msg(y, "page", "worker", "start(job)")
    worker_y = y
    top = y + 0.1
    y += 0.4
    s.msg(y, "worker", "svc", "run(source, tests)")
    y += 0.25
    s.msg(y, "svc", "runner", "run_tests(timeout=10.0)")
    y += 0.25
    s.msg(y, "runner", "sub", "subprocess.run(..., timeout=10)")
    y += 0.25
    s.msg(y, "sub", "runner", "süre doldu → TimeoutExpired", ret=True)
    y += 0.25
    s.msg(y, "runner", "runner", "çalıştırılan tüm testler → 'timeout'")
    y += 0.35
    s.msg(y, "runner", "worker", "ExecutionResult (coverage boş)", ret=True)
    y += 0.22
    s.msg(y, "worker", "page", "finished → 'Zaman aşımı'", ret=True)
    alt2 = y + 0.15
    y += 0.42
    s.msg(y, "svc", "worker", "ServiceError(mesaj)", ret=True)
    y += 0.22
    s.msg(y, "worker", "page", "failed(mesaj) → kırmızı durum", ret=True)
    alt3 = y + 0.15
    y += 0.42
    s.msg(y, "worker", "worker", "log.exception(...)")
    y += 0.3
    s.msg(y, "worker", "page", "failed('Beklenmeyen hata: …')", ret=True)
    s.frag(
        1.55,
        top,
        8.9,
        y + 0.15,
        "alt",
        "[test zaman aşımına uğrar]",
        splits=(
            (alt2, "[boş / geçersiz kaynak ya da boş test listesi]"),
            (alt3, "[beklenmeyen istisna]"),
        ),
    )
    s.act("worker", worker_y, y)
    s.act("page", page_y, y + 0.1)
    y += 0.5
    s.msg(y, "page", "hook", "GUI iş parçacığında yakalanmamış istisna")
    s.act("hook", y, y + 0.35)
    y += 0.25
    s.msg(y, "hook", "u", "Logger'a yaz + 'Beklenmeyen Hata' kutusu; uygulama açık kalır", ret=True)
    return d.save("04c-sirali-hata-zaman-asimi")


# --------------------------------------------------------------------------- 5. etkinlik


def action_box(d: Diagram, cx: float, cy: float, text: str, w: float | None = None) -> Box:
    lines = text.split("\n")
    w = w or max(text_width(s) for s in lines) + 0.3
    h = LINE * len(lines) + 0.14
    d.ax.add_patch(
        FancyBboxPatch(
            (cx - w / 2, cy - h / 2),
            w,
            h,
            boxstyle="round,pad=0,rounding_size=0.09",
            fc=FILL,
            ec=INK,
            lw=0.9,
            zorder=3,
        )
    )
    d.text(cx, cy, text, ha="center")
    return Box(cx - w / 2, cy - h / 2, w, h)


def decision(d: Diagram, cx: float, cy: float, text: str = "") -> Box:
    r = 0.17
    pts = [(cx, cy - r), (cx + r * 1.3, cy), (cx, cy + r), (cx - r * 1.3, cy)]
    d.ax.add_patch(Polygon(pts, closed=True, fc=HEAD, ec=INK, lw=0.9, zorder=3))
    if text:
        d.text(cx + r * 1.3 + 0.07, cy - 0.12, text, size=FS - 1, color=MUTED, style="italic")
    return Box(cx - r * 1.3, cy - r, 2 * r * 1.3, 2 * r, shape="diamond")


def flow(
    d: Diagram,
    a: Box,
    b: Box,
    guard: str | None = None,
    *,
    src: tuple[str, float] = ("bottom", 0.5),
    dst: tuple[str, float] = ("top", 0.5),
    via: tuple[tuple[float, float], ...] = (),
    gx: float = 0.06,
    gy: float = 0.1,
) -> None:
    p, q = a.side(*src), b.side(*dst)
    pts = [p, *via, q]
    d.line(pts)
    d.head(q, pts[-2], "filled")
    if guard:
        d.text(p[0] + gx, p[1] + gy, guard, size=FS - 1, color=MUTED, style="italic")


def activity_rl() -> Path:
    d = Diagram(6.2, 8.9, "Etkinlik Diyagramı — RL test üretimi (generate_tests)")
    cx = 2.6
    start = Box(cx - 0.09, 0.5, 0.18, 0.18)
    d.ax.add_patch(Circle(start.center, 0.09, fc=INK, ec=INK, zorder=4))
    a1 = action_box(
        d,
        cx,
        0.98,
        "ajanı kur: RLConfig.make_agent(seed)\n(toplu çalıştırmada paylaşılan Q-tablosu)",
    )
    a2 = action_box(
        d,
        cx,
        1.55,
        "reset(): parametreleri ve docstring tohumlarını çıkar;\nkullanıcı testleri varsa coverage'ları ile başla",
    )
    d1 = decision(d, cx, 2.1, "tam kapsanıyor mu?")
    a3 = action_box(d, cx, 2.6, "select_action(obs): ε-greedy (ε = 0.2)")
    a4 = action_box(d, cx, 3.1, "Action.generate(ctx, rng) → girdi")
    d2 = decision(d, cx, 3.6, "girdi var mı?")
    a5 = action_box(d, cx, 4.1, "oracle: call_function() alt süreçte (2 sn)")
    a6 = action_box(d, cx, 4.6, "synthesize(): assert / pytest.raises testi")
    d3 = decision(d, cx, 5.1, "test üretildi mi?")
    a7 = action_box(d, cx, 5.6, "run_tests(unit, [test]) — coverage ölçümü")
    d4 = decision(d, cx, 6.1, "test geçti mi?")
    a8 = action_box(
        d, cx, 6.62, "coverage'ı birleştir; Δcoverage > 0 ya da\nyeni çıktı sınıfı ise testi tut"
    )
    a9 = action_box(
        d, cx, 7.25, "ödül: α·Δline + β·Δbranch + γ·yeni − δ·geçersiz − ε\nQ(s,a) güncelle"
    )
    d5 = decision(d, cx, 7.85, "bitti mi?")
    a10 = action_box(d, 5.0, 2.1, "epizot sonucu\n(EpisodeResult)", w=1.45)
    d6 = decision(d, 5.0, 2.95, "epizot kaldı mı?")
    a11 = action_box(d, 5.0, 3.75, "en iyi epizodu seç:\nbranch, satır, az test", w=1.45)
    end = Box(4.91, 4.3, 0.18, 0.18)
    d.ax.add_patch(Circle(end.center, 0.1, fc="white", ec=INK, lw=1.0, zorder=4))
    d.ax.add_patch(Circle(end.center, 0.06, fc=INK, ec=INK, zorder=5))
    flow(d, start, a1)
    flow(d, a1, a2)
    flow(d, a2, d1)
    flow(d, d1, a3, "[hayır]")
    flow(d, a3, a4)
    flow(d, a4, d2)
    flow(d, d2, a5, "[evet]")
    flow(d, a5, a6)
    flow(d, a6, d3)
    flow(d, d3, a7, "[evet]")
    flow(d, a7, d4)
    flow(d, d4, a8, "[evet]")
    flow(d, a8, a9)
    flow(d, a9, d5)
    xl = 0.25
    for dec in (d2, d3, d4):
        flow(
            d,
            dec,
            a9,
            None,
            src=("left", 0.5),
            dst=("left", 0.5),
            via=((xl, dec.center[1]), (xl, a9.center[1])),
        )
        d.text(
            dec.x - 0.45, dec.center[1] - 0.1, "[hayır]", size=FS - 1, color=MUTED, style="italic"
        )
    d.text(xl + 0.05, 5.95, "geçersiz adım:\n−δ cezası", size=FS - 1.5, color=MUTED)
    flow(
        d,
        d5,
        a3,
        None,
        src=("right", 0.5),
        dst=("right", 0.5),
        via=((4.35, d5.center[1]), (4.35, a3.center[1])),
    )
    d.text(
        3.05,
        d5.center[1] + 0.2,
        "[hayır: adım < max_steps ve artışsız adım < patience]",
        size=FS - 1.5,
        color=MUTED,
        style="italic",
    )
    flow(d, d1, a10, "[evet]", src=("right", 0.5), dst=("left", 0.5), gx=0.12, gy=0.12)
    flow(
        d,
        d5,
        a10,
        None,
        src=("bottom", 0.5),
        dst=("right", 0.5),
        via=((cx, 8.4), (5.95, 8.4), (5.95, 2.1)),
    )
    d.text(
        cx + 0.08,
        8.28,
        "[evet: tam coverage (dal yoksa satır), max_steps ya da patience]",
        size=FS - 1.5,
        color=MUTED,
        style="italic",
    )
    flow(d, a10, d6, src=("bottom", 0.5), dst=("top", 0.5))
    flow(
        d,
        d6,
        a2,
        None,
        src=("left", 0.5),
        dst=("right", 0.5),
        via=((4.42, d6.center[1]), (4.42, a2.center[1])),
    )
    d.text(4.47, d6.center[1] - 0.1, "[evet]", size=FS - 1.5, color=MUTED, style="italic")
    flow(d, d6, a11, "[hayır]")
    flow(d, a11, end)
    return d.save("05-etkinlik-rl")


def main() -> None:
    for draw in (
        use_case_diagram,
        package_diagram,
        class_domain,
        class_execution_mutation,
        class_rl,
        class_datasets_batch,
        class_services,
        class_gui,
        sequence_batch,
        sequence_gui,
        sequence_errors,
        activity_rl,
    ):
        print(draw().name)


if __name__ == "__main__":
    main()
