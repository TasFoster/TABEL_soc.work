"""Запись «Отчёта по госзаданию» в .ods БЕЗ Excel — через odfpy (с нуля).

Два листа: «Лист1» (госзадание — основные услуги) и «дополнительные».
Каждый: заголовок (объединён по колонкам), «Социальный работник …», шапка таблицы
(№, ФИО, услуги, Итого, Период), строки получателей, строка итогов, подписи.
"""

from odf.opendocument import OpenDocumentSpreadsheet
from odf.style import (ParagraphProperties, Style, TableCellProperties,
                       TableColumnProperties, TableProperties, TableRowProperties,
                       TextProperties)
from odf.table import CoveredTableCell, Table, TableCell, TableColumn, TableRow
from odf.text import P

FONT = "Times New Roman"
BORDER = "0.5pt solid #000000"


class GosWriterError(Exception):
    pass


def _fmt(v):
    """Число для ячейки: пусто при 0, целое без дроби, иначе с запятой."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if abs(v) < 1e-9:
        return None
    return int(round(v)) if abs(v - round(v)) < 1e-9 else round(v, 2)


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
    f10 = dict(f, fontsize="10pt", fontsizeasian="10pt", fontsizecomplex="10pt")
    f9 = dict(f, fontsize="9pt", fontsizeasian="9pt", fontsizecomplex="9pt")
    f12b = dict(f, fontsize="12pt", fontsizeasian="12pt", fontsizecomplex="12pt",
                fontweight="bold", fontweightasian="bold", fontweightcomplex="bold")
    b = dict(f9, fontweight="bold", fontweightasian="bold", fontweightcomplex="bold")
    bord = {"border": BORDER, "verticalalign": "middle", "wrapoption": "wrap"}

    add("Title", para={"textalign": "center"}, text=f12b)
    add("Sub", para={"textalign": "start"}, text=f10)
    add("Hdr", cell=bord, para={"textalign": "center"}, text=b)
    add("Num", cell=bord, para={"textalign": "center"}, text=f9)
    add("Fio", cell=bord, para={"textalign": "start"}, text=f10)
    add("Tot", cell=dict(bord, **{}), para={"textalign": "center"}, text=b)
    add("Sign", para={"textalign": "start"}, text=f10)

    # стили колонок (ширины)
    def col(name, width):
        s = Style(name=name, family="table-column")
        s.addElement(TableColumnProperties(columnwidth=width))
        doc.automaticstyles.addElement(s)
        st[name] = s
    col("cNum", "0.9cm")
    col("cFio", "5.2cm")
    col("cSvc", "1.7cm")
    col("cTot", "1.5cm")
    col("cPer", "3.4cm")

    rs = Style(name="rHdr", family="table-row")
    rs.addElement(TableRowProperties(useoptimalrowheight="true"))
    doc.automaticstyles.addElement(rs)
    st["rHdr"] = rs
    return st


def _txt_cell(text, style, span=1):
    c = TableCell(valuetype="string", stylename=style)
    if span > 1:
        c.setAttribute("numbercolumnsspanned", span)
        c.setAttribute("numberrowsspanned", 1)
    if text not in (None, ""):
        for i, line in enumerate(str(text).split("\n")):
            c.addElement(P(text=line))
    else:
        c.addElement(P(text=""))
    return c


def _num_cell(value, style):
    f = _fmt(value)
    if f is None:
        return _txt_cell("", style)
    c = TableCell(valuetype="float", value=f, stylename=style)
    s = str(int(f)) if isinstance(f, int) or float(f).is_integer() else str(f).replace(".", ",")
    c.addElement(P(text=s))
    return c


def _covered(n):
    return [CoveredTableCell() for _ in range(max(0, n))]


def _sheet(doc, st, name, title, ctx, services, clients, total_mode):
    """Один лист. total_mode: 'all' (Итого = Всего услуг) или 'sum' (Итого = сумма услуг листа)."""
    ncols = 2 + len(services) + 2          # №, ФИО, услуги…, Итого, Период
    table = Table(name=name)
    table.addElement(TableColumn(stylename=st["cNum"]))
    table.addElement(TableColumn(stylename=st["cFio"]))
    for _ in services:
        table.addElement(TableColumn(stylename=st["cSvc"]))
    table.addElement(TableColumn(stylename=st["cTot"]))
    table.addElement(TableColumn(stylename=st["cPer"]))

    def row(cells):
        r = TableRow()
        for c in cells:
            r.addElement(c)
        table.addElement(r)
        return r

    # заголовок (объединён по всем колонкам)
    row([_txt_cell(title, "Title", span=ncols)] + _covered(ncols - 1))
    row([_txt_cell(f"Социальный работник {ctx.get('worker','')}", "Sub", span=ncols)]
        + _covered(ncols - 1))

    # шапка
    hdr = TableRow(stylename=st["rHdr"])
    for v in ["№п/п", "ФИО гражданина"] + list(services) + ["Итого", "Период"]:
        hdr.addElement(_txt_cell(v, "Hdr"))
    table.addElement(hdr)

    # данные
    col_sums = [0.0] * len(services)
    tot_sum = 0.0
    period = ctx.get("period_str", "")
    idx = 0
    for cl in clients:
        svc_vals = [float(cl.counts.get(s, 0) or 0) for s in services]
        if total_mode == "sum":
            if sum(svc_vals) <= 0:
                continue                    # доп.лист — только клиенты с услугами
            itogo = sum(svc_vals)
        else:
            itogo = float(cl.total or 0)
        idx += 1
        for i, v in enumerate(svc_vals):
            col_sums[i] += v
        tot_sum += itogo
        cells = [_num_cell(idx, "Num"), _txt_cell(cl.fio, "Fio")]
        cells += [_num_cell(v, "Num") for v in svc_vals]
        cells += [_num_cell(itogo, "Num"), _txt_cell(period, "Num")]
        row(cells)

    # итоги
    tcells = [_txt_cell("", "Tot"), _txt_cell("Итого", "Tot")]
    tcells += [_num_cell(v, "Tot") for v in col_sums]
    tcells += [_num_cell(tot_sum, "Tot"), _txt_cell("", "Tot")]
    row(tcells)

    # подписи
    row([_txt_cell("", "Sign")] * ncols)
    sign = TableRow()
    soc = f"Соц. работник ________________ {ctx.get('worker_sign','')}"
    zav = f"Зав. отделением № {ctx.get('dept','')} __________________ /{ctx.get('zav_sign','')}/"
    left_span = max(1, len(services) // 2 + 2)
    sign.addElement(_txt_cell(soc, "Sign", span=left_span))
    for c in _covered(left_span - 1):
        sign.addElement(c)
    rest = ncols - left_span
    sign.addElement(_txt_cell(zav, "Sign", span=rest))
    for c in _covered(rest - 1):
        sign.addElement(c)
    table.addElement(sign)

    doc.spreadsheet.addElement(table)


def generate(out_path, ctx, clients, main_services, dop_services):
    doc = OpenDocumentSpreadsheet()
    st = _styles(doc)
    mn = ctx.get("month_name", "")
    yr = ctx.get("year", "")
    _sheet(doc, st, "Лист1",
           f"Отчет о выполнении государственного задания за {mn} {yr}",
           ctx, main_services, clients, total_mode="all")
    _sheet(doc, st, "дополнительные",
           f"Отчет о выполнении дополнительных услуг за {mn} {yr}",
           ctx, dop_services, clients, total_mode="sum")
    doc.save(out_path)
    return out_path
