"""Запись плана работы отделения в .odt (OpenDocumentText) БЕЗ офисного пакета — odfpy.

План — текстовый документ: шапка «УТВЕРЖДАЮ» (справа), заголовок «ПЛАН …»
(по центру), таблица мероприятий (№ | Мероприятия | Сроки | Ответственный |
Результат) с разделами-подзаголовками и строками, подпись зав. отделением.
Данные приходят уже с подставленным годом и соцработником (см. service.build_plan).
"""

from odf.opendocument import OpenDocumentText
from odf.style import (MasterPage, PageLayout, PageLayoutProperties,
                       ParagraphProperties, Style, TableCellProperties,
                       TableColumnProperties, TableProperties, TextProperties)
from odf.table import CoveredTableCell, Table, TableCell, TableColumn, TableRow
from odf.text import P

FONT = "Times New Roman"
BORDER = "0.5pt solid #000000"
CONTENT_CM = 17.6  # ширина таблицы (портрет A4, поля 1.5 см → контент 18 см, запас)
HEAD_COLS = ("№", "Мероприятия", "Сроки", "Ответственный", "Результат")
DEFAULT_WIDTHS = [1.0, 10.6, 2.9, 2.4, 1.1]  # запасные доли колонок


class PlanyWriterError(Exception):
    pass


def _col_cm(col_widths):
    """Ширины 5 колонок в см, пропорционально масштабированные под CONTENT_CM."""
    vals = []
    for w in (col_widths or []):
        try:
            vals.append(float(str(w).replace("pt", "").strip()))
        except ValueError:
            vals.append(0.0)
    if len(vals) != 5 or sum(vals) <= 0:
        vals = DEFAULT_WIDTHS
    total = sum(vals)
    return [round(v / total * CONTENT_CM, 2) for v in vals]


def _styles(doc, col_cm):
    st = {}
    f = {"fontname": FONT, "fontnameasian": FONT, "fontnamecomplex": FONT}

    def font(size, bold=False):
        d = dict(f, fontsize="%dpt" % size, fontsizeasian="%dpt" % size,
                 fontsizecomplex="%dpt" % size)
        if bold:
            d.update(fontweight="bold", fontweightasian="bold", fontweightcomplex="bold")
        return d

    def para(name, *, align="start", text=None, space_before=None, space_after=None):
        s = Style(name=name, family="paragraph")
        pp = {"textalign": align}
        if space_before:
            pp["margintop"] = space_before
        if space_after:
            pp["marginbottom"] = space_after
        s.addElement(ParagraphProperties(**pp))
        if text:
            s.addElement(TextProperties(**text))
        doc.styles.addElement(s)
        st[name] = s

    # абзацы вне таблицы
    para("Utv", align="end", text=font(11))
    para("Title", align="center", text=font(14, True), space_before="0.3cm")
    para("Subtitle", align="center", text=font(12, True))
    para("Sign", align="start", text=font(11), space_before="0.3cm")
    # абзацы в ячейках
    para("CellL", align="start", text=font(9))
    para("CellC", align="center", text=font(9))
    para("Hdr", align="center", text=font(9, True))
    para("Sect", align="start", text=font(10, True))

    # стиль таблицы
    ts = Style(name="PlanTable", family="table")
    ts.addElement(TableProperties(width="%.2fcm" % CONTENT_CM, align="center"))
    doc.automaticstyles.addElement(ts)
    st["table"] = ts

    # стили колонок
    for i, cm in enumerate(col_cm):
        cs = Style(name="PlanCol%d" % i, family="table-column")
        cs.addElement(TableColumnProperties(columnwidth="%.2fcm" % cm))
        doc.automaticstyles.addElement(cs)
        st["col%d" % i] = cs

    # стили ячеек (границы + перенос + отступ)
    base = {"border": BORDER, "padding": "0.05cm", "verticalalign": "middle"}
    for name in ("Cell", "SectCell", "HdrCell"):
        cs = Style(name=name, family="table-cell")
        cs.addElement(TableCellProperties(**base))
        doc.automaticstyles.addElement(cs)
        st[name] = cs
    return st


def _cell(st, cell_style, para_style, text):
    c = TableCell(stylename=st[cell_style], valuetype="string")
    for line in (text or "").split("\n"):
        c.addElement(P(stylename=st[para_style], text=line))
    if not (text or "").strip():
        c.addElement(P(stylename=st[para_style], text=""))
    return c


def generate(out_path, plan):
    """plan — dict: header[], title (dict month/year уже внутри строк header), sections[],
    footer[], col_widths[]. Данные уже с годом и соцработником."""
    doc = OpenDocumentText()

    # страница A4 портрет
    pl = PageLayout(name="PL")
    pl.addElement(PageLayoutProperties(
        pagewidth="21cm", pageheight="29.7cm", printorientation="portrait",
        margintop="1.5cm", marginbottom="1.5cm", marginleft="1.5cm", marginright="1.5cm"))
    doc.automaticstyles.addElement(pl)
    doc.masterstyles.addElement(MasterPage(name="Standard", pagelayoutname="PL"))

    col_cm = _col_cm(plan.get("col_widths"))
    st = _styles(doc, col_cm)

    # --- шапка «УТВЕРЖДАЮ» и заголовок ---
    header = plan.get("header", [])
    # отделяем заголовок (с «ПЛАН») от блока «УТВЕРЖДАЮ»
    plan_idx = next((i for i, h in enumerate(header) if h.strip().upper() == "ПЛАН"), None)
    utv = header if plan_idx is None else header[:plan_idx]
    title = [] if plan_idx is None else header[plan_idx:]
    for line in utv:
        doc.text.addElement(P(stylename=st["Utv"], text=line))
    for i, line in enumerate(title):
        style = "Title" if line.strip().upper() == "ПЛАН" else "Subtitle"
        doc.text.addElement(P(stylename=st[style], text=line))
    doc.text.addElement(P(stylename=st["Subtitle"], text=""))  # отбивка перед таблицей

    # --- таблица ---
    table = Table(name="План", stylename=st["table"])
    for i in range(5):
        table.addElement(TableColumn(stylename=st["col%d" % i]))
    # шапка таблицы
    hr = TableRow()
    for head in HEAD_COLS:
        hr.addElement(_cell(st, "HdrCell", "Hdr", head))
    table.addElement(hr)
    # разделы и строки
    for sec in plan.get("sections", []):
        sr = TableRow()
        sc = TableCell(stylename=st["SectCell"], valuetype="string", numbercolumnsspanned=5)
        sc.addElement(P(stylename=st["Sect"], text=sec.get("title", "")))
        sr.addElement(sc)
        for _ in range(4):
            sr.addElement(CoveredTableCell())
        table.addElement(sr)
        for row in sec.get("rows", []):
            tr = TableRow()
            cells = (list(row) + [""] * 5)[:5]
            tr.addElement(_cell(st, "Cell", "CellC", cells[0]))   # №
            tr.addElement(_cell(st, "Cell", "CellL", cells[1]))   # мероприятие
            tr.addElement(_cell(st, "Cell", "CellC", cells[2]))   # сроки
            tr.addElement(_cell(st, "Cell", "CellC", cells[3]))   # ответственный
            tr.addElement(_cell(st, "Cell", "CellL", cells[4]))   # результат
            table.addElement(tr)
    doc.text.addElement(table)

    # --- подпись ---
    for line in plan.get("footer", []):
        doc.text.addElement(P(stylename=st["Sign"], text=line))

    doc.save(out_path)
    return out_path
