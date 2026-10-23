"""Markdown dokümanını STD ile aynı görünümde Word (.docx) dosyasına çevirir.

``docs/TestZede-STD.docx`` şablon olarak kullanılır: stiller, kapak sayfası, alt bilgi ve
sayfa düzeni oradan kopyalanır, gövde Markdown'dan yeniden yazılır. Yalnızca bu depodaki
SDD ve Gereksinim Raporu'nun kullandığı Markdown alt kümesi desteklenir: ``#``/``##``/``###``
başlıklar, paragraflar, ``-`` ve ``1.`` listeler, ``|`` tablolar, ``![…](yol)`` resimler,
``*Şekil …*`` resim altı yazıları, satır içi ``**kalın**`` ve ```kod```.

İlk numaralı başlıktan (``# 1. …``) önceki satırlar atlanır; kapak bilgisi komut satırından
verilir. Geniş resimler yatay sayfaya yerleştirilir.

Gerekenler: ``python-docx`` (proje bağımlılığı değildir; ayrıca kurulu bir Python'da çalıştırın).

Kullanım (depo kökünden)::

    python docs/tools/md_to_docx.py docs/TestZede-SDD.md docs/TestZede-SDD.docx \\
        --title "Software Design Document" --subtitle "Yazılım Tasarım Dokümanı (SDD)" \\
        --version 1.0 --date 22-10-2026 --footer "SDD v1.0"
"""

from __future__ import annotations

import argparse
import re
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Inches, Pt, RGBColor

DOCS = Path(__file__).resolve().parents[1]
TEMPLATE = DOCS / "TestZede-STD.docx"
INK = RGBColor(0x1F, 0x38, 0x64)
BORDER = "8C8C8C"
HEAD_FILL = "D9E2F3"
TABLE_WIDTH_DXA = 9026
CELL_PAD_DXA = 216  # hücrenin sol + sağ iç boşluğu (Word varsayılanı 108 + 108)
WORD_CAP = 12  # bundan uzun kelimeler (yollar, kod) yine satır kaydırabilir
COVER_PARAGRAPHS = 10  # şablonda kapak: boşluk, başlık, sürüm, tarih, ad, alt başlık, ekip ×4
INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|(?<!\*)\*[^*\s][^*]*\*(?!\*))")
IMAGE = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<path>[^)]+)\)$")
NUMBERED = re.compile(r"^(\d+)\. (.*)$")


def _set_text(paragraph, text: str) -> None:
    """Paragrafın ilk koşusunun metnini değiştirir, diğer koşuları siler."""
    runs = paragraph.runs
    runs[0].text = text
    for run in runs[1:]:
        run._element.getparent().remove(run._element)


def _longest_word(text: str) -> int:
    """Biçim işaretleri atılmış metindeki en uzun boşluksuz parçanın uzunluğu."""
    return max((len(w) for w in re.sub(r"\*\*|`", "", text).split()), default=0)


def _fit_widths(weights: list[float], floors: list[float], total: float) -> list[float]:
    """Genişliği ağırlıklara göre böler; alt sınırın altında kalan sütunu sınıra sabitler."""
    fixed: dict[int, float] = {}
    while True:
        rest = total - sum(fixed.values())
        free = [i for i in range(len(weights)) if i not in fixed]
        share = sum(weights[i] for i in free)
        widths = {i: rest * weights[i] / share for i in free}
        short = [i for i in free if widths[i] < floors[i]]
        if not short or len(short) == len(free):
            return [fixed.get(i, widths.get(i, 0.0)) for i in range(len(weights))]
        fixed.update((i, floors[i]) for i in short)


def _add_inline(paragraph, text: str, *, size: float | None = None, italic: bool = False) -> None:
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1])
            run.font.name = "Consolas"
        elif len(part) > 2 and part.startswith("*") and part.endswith("*"):
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        else:
            run = paragraph.add_run(part)
        if size is not None:
            run.font.size = Pt(size)
        if italic:
            run.italic = True


def _cell_borders(cell, fill: str | None) -> None:
    props = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), BORDER)
        borders.append(element)
    props.append(borders)
    if fill:
        shade = OxmlElement("w:shd")
        shade.set(qn("w:val"), "clear")
        shade.set(qn("w:color"), "auto")
        shade.set(qn("w:fill"), fill)
        props.append(shade)
    margins = OxmlElement("w:tcMar")
    for edge, value in (("top", 60), ("left", 100), ("bottom", 60), ("right", 100)):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:w"), str(value))
        element.set(qn("w:type"), "dxa")
        margins.append(element)
    props.append(margins)


def _split_row(line: str) -> list[str]:
    # GFM'deki gibi ``\|`` hücre ayırıcı değil, düz ``|`` karakteridir.
    cells = re.split(r"(?<!\\)\|", line.strip().strip("|"))
    return [c.strip().replace("\\|", "|") for c in cells]


class Builder:
    def __init__(self, footer: str, cover: dict[str, str]) -> None:
        self.doc = Document(TEMPLATE)
        body = self.doc.element.body
        children = list(body)
        cover_xml = [deepcopy(c) for c in children[:COVER_PARAGRAPHS]]
        toc_title = deepcopy(children[COVER_PARAGRAPHS])
        for child in children:
            if child.tag != qn("w:sectPr"):
                body.remove(child)
        sect = body.find(qn("w:sectPr"))
        for element in [*cover_xml, toc_title]:
            sect.addprevious(element)
        paragraphs = self.doc.paragraphs
        _set_text(paragraphs[1], cover["title"])
        _set_text(paragraphs[2], f"Version {cover['version']}")
        _set_text(paragraphs[3], f"Date: {cover['date']}")
        subtitle = deepcopy(paragraphs[5]._element)
        paragraphs[1]._element.addnext(subtitle)
        _set_text(self.doc.paragraphs[2], cover["subtitle"])
        _set_text(self.doc.paragraphs[-1], "İçindekiler")
        self._toc()
        for paragraph in self.doc.sections[0].footer.paragraphs:
            for run in paragraph.runs:
                if "STD v1.0" in run.text:
                    run.text = run.text.replace("STD v1.0", footer)
        settings = self.doc.settings.element
        update = OxmlElement("w:updateFields")
        update.set(qn("w:val"), "true")
        settings.append(update)
        props = self.doc.core_properties
        props.title = f"TestZede — {cover['subtitle']}"
        props.author = "TestZede Proje Ekibi"
        props.last_modified_by = "TestZede Proje Ekibi"
        props.subject = cover["title"]
        props.comments = ""
        self.landscape = False
        self.first_heading = True

    def _toc(self) -> None:
        paragraph = self.doc.add_paragraph()
        for kind, text in (
            ("begin", None),
            ("instr", ' TOC \\o "1-2" \\h \\z \\u '),
            ("separate", None),
            ("text", "İçindekiler: Word'de alanı güncelleyin (sağ tık → Alanı Güncelleştir)."),
            ("end", None),
        ):
            run = paragraph.add_run()
            if kind == "instr":
                element = OxmlElement("w:instrText")
                element.set(qn("xml:space"), "preserve")
                element.text = text
                run._element.append(element)
            elif kind == "text":
                run.text = text
            else:
                element = OxmlElement("w:fldChar")
                element.set(qn("w:fldCharType"), kind)
                if kind == "begin":
                    element.set(qn("w:dirty"), "true")
                run._element.append(element)

    # ----------------------------------------------------------------- sayfa yönü

    def _orientation(self, landscape: bool) -> None:
        if landscape == self.landscape:
            return
        section = self.doc.add_section(WD_SECTION.NEW_PAGE)
        width, height = section.page_width, section.page_height
        if landscape != (width > height):
            section.page_width, section.page_height = height, width
        section.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
        self.landscape = landscape

    def _usable(self) -> tuple[float, float]:
        section = self.doc.sections[-1]
        width = section.page_width - section.left_margin - section.right_margin
        height = section.page_height - section.top_margin - section.bottom_margin
        return Emu(width).inches, Emu(height).inches

    # ----------------------------------------------------------------- bloklar

    def heading(self, level: int, text: str) -> None:
        self._orientation(False)
        paragraph = self.doc.add_paragraph(style=f"Heading {level}")
        _add_inline(paragraph, text)
        if level == 1:
            paragraph.paragraph_format.page_break_before = True
            self.first_heading = False

    def paragraph(self, text: str) -> None:
        self._orientation(False)
        paragraph = self.doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _add_inline(paragraph, text)

    def bullet(self, text: str, marker: str = "•") -> None:
        self._orientation(False)
        paragraph = self.doc.add_paragraph(style="List Paragraph")
        fmt = paragraph.paragraph_format
        fmt.left_indent = Inches(0.3)
        fmt.first_line_indent = Inches(-0.2)
        fmt.space_after = Pt(3)
        _add_inline(paragraph, f"{marker}\t{text}")
        fmt.tab_stops.add_tab_stop(Inches(0.3))

    def caption(self, text: str) -> None:
        paragraph = self.doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_inline(paragraph, text, size=9, italic=True)

    def image(self, path: Path) -> None:
        from PIL import Image  # python-docx bağımlılığı

        with Image.open(path) as img:
            px_w, px_h = img.size
            dpi = img.info.get("dpi", (200, 200))[0] or 200
        width_in, height_in = px_w / dpi, px_h / dpi
        landscape = width_in > 6.5
        self._orientation(landscape)
        max_w, max_h = self._usable()
        max_h -= 0.6  # resim altı yazısına yer
        scale = min(1.0, max_w / width_in, max_h / height_in)
        paragraph = self.doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.keep_with_next = True
        paragraph.add_run().add_picture(str(path), width=Inches(width_in * scale))

    def table(self, rows: list[list[str]]) -> None:
        self._orientation(False)
        header, *body = rows
        columns = len(header)
        table = self.doc.add_table(rows=1 + len(body), cols=columns)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        size = 9 if columns >= 3 else 10
        # Sütun genişliği hücrelerin ortalama uzunluğuna göre; uzun hücreler satır kaydırır.
        sample = body or rows
        lengths = [
            sum(len(r[i]) if i < len(r) else 0 for r in sample) / len(sample)
            for i in range(columns)
        ]
        weights = [min(max(n, 11.0), 50.0) for n in lengths]
        # Kısa kelimeler ("GER-001", "Zorunlu") ortadan bölünmesin: sütun en az en uzun
        # kelimesi kadar geniş olur, kalan genişlik ağırlıklara göre dağıtılır.
        floors = [
            min(max((_longest_word(r[i]) if i < len(r) else 0) for r in rows), WORD_CAP) * size * 11
            + CELL_PAD_DXA
            for i in range(columns)
        ]
        widths = _fit_widths(weights, floors, TABLE_WIDTH_DXA)
        # Sabit düzen: Word içeriğe göre otomatik sığdırırsa uzun yollar dar sütunları ezer.
        table.autofit = False
        layout = OxmlElement("w:tblLayout")
        layout.set(qn("w:type"), "fixed")
        table._tbl.tblPr.append(layout)
        for column, width in zip(table.columns, widths, strict=True):
            column.width = Emu(int(width * 635))
        for r, values in enumerate(rows):
            for c in range(columns):
                cell = table.cell(r, c)
                cell.width = Emu(int(widths[c] * 635))
                _cell_borders(cell, HEAD_FILL if r == 0 else None)
                paragraph = cell.paragraphs[0]
                paragraph.paragraph_format.space_after = Pt(0)
                text = values[c] if c < len(values) else ""
                text = text.replace("**", "") if r == 0 else text
                _add_inline(paragraph, text, size=size)
                if r == 0:
                    for run in paragraph.runs:
                        run.bold = True
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def save(self, out: Path) -> None:
        self.doc.save(out)


def convert(source: Path, out: Path, footer: str, cover: dict[str, str]) -> None:
    builder = Builder(footer, cover)
    lines = source.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if re.match(r"^# \d+\.", line))
    i = start
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            builder.paragraph(" ".join(paragraph))
            paragraph.clear()

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            flush()
        elif line.startswith("#"):
            flush()
            level = len(line) - len(line.lstrip("#"))
            builder.heading(level, line[level:].strip())
        elif stripped.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = _split_row(lines[i])
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            builder.table(rows)
            continue
        elif match := IMAGE.match(stripped):
            flush()
            builder.image((source.parent / match["path"]).resolve())
        elif stripped.startswith("*Şekil") and stripped.endswith("*"):
            flush()
            builder.caption(stripped[1:-1])
        elif stripped.startswith("- "):
            flush()
            builder.bullet(stripped[2:])
        elif match := NUMBERED.match(stripped):
            flush()
            builder.bullet(match[2], marker=f"{match[1]}.")
        else:
            paragraph.append(stripped)
        i += 1
    flush()
    builder.save(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--subtitle", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--footer", required=True, help="alt bilgideki ad, örn. 'SDD v1.0'")
    args = parser.parse_args()
    cover = {
        "title": args.title,
        "subtitle": args.subtitle,
        "version": args.version,
        "date": args.date,
    }
    convert(args.source, args.out, args.footer, cover)
    print(args.out)


if __name__ == "__main__":
    main()
