"""Запись списка «Пересмотр» в .ods БЕЗ Excel — через odfpy (с нуля).

Один лист: объединённый заголовок, шапка (ФИО | Дата окончания срока), строки.
Приёмы те же, что в gos_zadanie/proverka_kachestva (OpenDocumentSpreadsheet, стили,
_txt_cell, _covered).
"""

from odf.opendocument import OpenDocumentSpreadsheet
from odf.style import (ParagraphProperties, Style, TableCellProperties,
                       TableColumnProperties, TextProperties)
from odf.table import CoveredTableCell, Table, TableCell, TableColumn, TableRow
from odf.text import P

FONT = "Times New Roman"
BORDER = "0.5pt solid #000000"
NCOLS = 2
COLS = ["Ф.И.О. обслуживаемого", "Дата окончания срока"]
WIDTHS = ["11cm", "4.5cm"]


class PeresmotrWriterError(Exception):
    pass


def _styles(doc):
    st = {}

    def add(name, *, family="table-cell", cell=None, para=None, text=None):
        s = Style(name=name, family=family)
        if cell:
            s.addElement(TableCellProperties(**cell))
        if para:
            s.addElement(ParagraphProperties(**para))
        if text:
            s.addElement(TextProperties(**text))
        doc.automaticstyles.addElement(s)
        st[name] = s
        return s

    f = {"fontname": FONT, "fontnameasian": FONT, "fontnamecomplex": FONT}
    f12 = dict(f, fontsize="12pt", fontsizeasian="12pt", fontsizecomplex="12pt")
    b12 = dict(f12, fontweight="bold", fontweightasian="bold", fontweightcomplex="bold")
    title = dict(f, fontsize="14pt", fontsizeasian="14pt", fontsizecomplex="14pt",
                 fontweight="bold", fontweightasian="bold", fontweightcomplex="bold")
    bord = {"border": BORDER, "verticalalign": "middle", "wrapoption": "wrap"}

    add("Title", para={"textalign": "center"}, text=title)
    add("Hdr", cell=bord, para={"textalign": "center"}, text=b12)
    add("Data", cell=bord, para={"textalign": "start"}, text=f12)
    add("DataC", cell=bord, para={"textalign": "center"}, text=f12)

    for i, w in enumerate(WIDTHS):
        cs = Style(name=f"c{i}", family="table-column")
        cs.addElement(TableColumnProperties(columnwidth=w))
        doc.automaticstyles.addElement(cs)
        st[f"c{i}"] = cs
    return st


def _txt_cell(text, style, span=1):
    c = TableCell(valuetype="string", stylename=style)
    if span > 1:
        c.setAttribute("numbercolumnsspanned", span)
        c.setAttribute("numberrowsspanned", 1)
    if text not in (None, ""):
        for line in str(text).split("\n"):
            c.addElement(P(text=line))
    else:
        c.addElement(P(text=""))
    return c


def _covered(n):
    return [CoveredTableCell() for _ in range(max(0, n))]


def generate(out_path, ctx, rows):
    """ctx: {'title'}; rows: список dict {fio, end}."""
    doc = OpenDocumentSpreadsheet()
    st = _styles(doc)
    table = Table(name="Пересмотр")
    for i in range(NCOLS):
        table.addElement(TableColumn(stylename=st[f"c{i}"]))

    def row(cells):
        r = TableRow()
        for c in cells:
            r.addElement(c)
        table.addElement(r)

    row([_txt_cell(ctx.get("title", ""), "Title", span=NCOLS)] + _covered(NCOLS - 1))
    row([_txt_cell(c, "Hdr") for c in COLS])
    for r in rows:
        row([_txt_cell(r.get("fio", ""), "Data"),
             _txt_cell(r.get("end", ""), "DataC")])

    doc.spreadsheet.addElement(table)
    doc.save(out_path)
    return out_path
