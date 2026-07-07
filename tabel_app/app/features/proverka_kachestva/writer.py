"""Запись листа «Проверка качества» в .ods БЕЗ Excel — через odfpy (с нуля).

Один лист (landscape): объединённый заголовок, шапка из 6 колонок, строки проверок
(дата ДД.ММ.ГГ, соцработник, обслуживаемый, адрес, телефон, результат) и подпись.
Построение повторяет приёмы gos_zadanie/writer.py; ориентация листа задаётся
страничным стилем (PageLayout + MasterPage), т.к. таблица широкая.
"""

from odf.opendocument import OpenDocumentSpreadsheet
from odf.style import (MasterPage, PageLayout, PageLayoutProperties,
                       ParagraphProperties, Style, TableCellProperties,
                       TableColumnProperties, TextProperties)
from odf.table import CoveredTableCell, Table, TableCell, TableColumn, TableRow
from odf.text import P

FONT = "Arial"
BORDER = "0.5pt solid #000000"
NCOLS = 6

COLS = ["Дата", "Ф.И.О. Социального работника", "Ф.И.О. обслуживаемого",
        "Адрес проживания", "Телефон", "Результат контроля,наличие жалоб"]
WIDTHS = ["2.2cm", "5.0cm", "5.0cm", "6.5cm", "3.3cm", "5.0cm"]  # ~27см ⩽ A4-landscape


class ProverkaWriterError(Exception):
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
    f11 = dict(f, fontsize="11pt", fontsizeasian="11pt", fontsizecomplex="11pt")
    b11 = dict(f11, fontweight="bold", fontweightasian="bold", fontweightcomplex="bold")
    title = dict(f, fontsize="16pt", fontsizeasian="16pt", fontsizecomplex="16pt",
                 fontweight="bold", fontweightasian="bold", fontweightcomplex="bold",
                 fontstyle="italic", fontstyleasian="italic", fontstylecomplex="italic")
    bord = {"border": BORDER, "verticalalign": "middle", "wrapoption": "wrap"}

    add("Title", para={"textalign": "center"}, text=title)
    add("Hdr", cell=bord, para={"textalign": "center"}, text=b11)
    add("Data", cell=bord, para={"textalign": "start"}, text=f11)
    add("DataC", cell=bord, para={"textalign": "center"}, text=f11)
    add("Sign", para={"textalign": "start"}, text=f11)

    # ориентация листа — альбомная (таблица широкая)
    pl = PageLayout(name="pl1")
    pl.addElement(PageLayoutProperties(
        printorientation="landscape", pagewidth="29.7cm", pageheight="21cm",
        margintop="1cm", marginbottom="1cm", marginleft="1cm", marginright="1cm"))
    doc.automaticstyles.addElement(pl)
    mp = MasterPage(name="Standard", pagelayoutname="pl1")
    doc.masterstyles.addElement(mp)
    ta = Style(name="ta1", family="table", masterpagename="Standard")
    doc.automaticstyles.addElement(ta)
    st["ta1"] = ta

    # ширины колонок
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
    """Собрать .ods. ctx: {'title', 'sign', ...}; rows: список dict с ключами
    date/worker/client/address/phone/result (уже отсортированы по дате)."""
    doc = OpenDocumentSpreadsheet()
    st = _styles(doc)
    table = Table(name="Проверка качества", stylename=st["ta1"])
    for i in range(NCOLS):
        table.addElement(TableColumn(stylename=st[f"c{i}"]))

    def row(cells):
        r = TableRow()
        for c in cells:
            r.addElement(c)
        table.addElement(r)

    # заголовок (объединён по всем колонкам)
    row([_txt_cell(ctx.get("title", ""), "Title", span=NCOLS)] + _covered(NCOLS - 1))
    # шапка
    row([_txt_cell(c, "Hdr") for c in COLS])
    # данные
    for r in rows:
        row([_txt_cell(r.get("date", ""), "DataC"),
             _txt_cell(r.get("worker", ""), "Data"),
             _txt_cell(r.get("client", ""), "Data"),
             _txt_cell(r.get("address", ""), "Data"),
             _txt_cell(r.get("phone", ""), "Data"),
             _txt_cell(r.get("result") or "нет", "Data")])
    # разделитель + подпись (объединена на 5 колонок)
    row([_txt_cell("", "Sign")] * NCOLS)
    row([_txt_cell(ctx.get("sign", ""), "Sign", span=5)] + _covered(4)
        + [_txt_cell("", "Sign")])

    doc.spreadsheet.addElement(table)
    doc.save(out_path)
    return out_path
