"""Помощники для построения .ods без Excel (на базе odfpy).

Реестр строится размножением строк-прототипов шаблона. odfpy хранит таблицу
как дерево элементов, где повторяющиеся строки/столбцы сжаты атрибутами
``number-rows-repeated`` / ``number-columns-repeated``. Эти помощники дают
логическую адресацию (строка, столбец), расщепляя повторы по мере надобности,
и операции вставки/удаления строк, сохраняющие оформление.
"""

from odf.element import Element, Text
from odf.table import TableRow
from odf.text import P, S

TABLENS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
OFFICENS = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"


def _ga(el, name):
    try:
        return el.getAttribute(name)
    except Exception:
        return None


def _del_attr(el, ns, local):
    key = (ns, local)
    if key in el.attributes:
        del el.attributes[key]


def _row_rep(row):
    return int(_ga(row, "numberrowsrepeated") or 1)


def _col_rep(cell):
    return int(_ga(cell, "numbercolumnsrepeated") or 1)


def _clone(el):
    """Глубокая копия ПОДДЕРЕВА элемента (только qname/атрибуты/потомки).

    Узлы odfpy хранят ссылки вверх и вбок (ownerDocument, parentNode,
    next/previousSibling), поэтому copy.deepcopy тянет за собой весь документ.
    Копируем поддерево вручную — быстро и без лишних связей.
    """
    if el.nodeType == 3:  # текстовый узел
        return Text(data=el.data)
    new = Element(qname=el.qname, qattributes=dict(el.attributes), check_grammar=False)
    for ch in el.childNodes:
        new.addElement(_clone(ch), check_grammar=False)
    return new


def _insert_after(parent, new, ref):
    kids = parent.childNodes
    idx = kids.index(ref)
    nxt = kids[idx + 1] if idx + 1 < len(kids) else None
    parent.insertBefore(new, nxt)   # ref=None -> append


# --------------------------------------------------------------- строки

def logical_rows(table):
    """Список (логический_индекс, элемент-строка, повтор) по порядку."""
    out = []
    idx = 0
    for row in table.getElementsByType(TableRow):
        rep = _row_rep(row)
        out.append((idx, row, rep))
        idx += rep
    return out


def row_at(table, logical_idx):
    """Вернуть элемент-строку для логического индекса.

    Если строка попадает в «сжатый» повтор (>1), повтор расщепляется на
    отдельные строки, и возвращается нужная.
    """
    for start, row, rep in logical_rows(table):
        if start <= logical_idx < start + rep:
            if rep == 1:
                return row
            return _split_row(table, row, rep, logical_idx - start)
    return None


def _split_row(table, row, rep, want):
    _del_attr(row, TABLENS, "number-rows-repeated")
    rows = [row]
    prev = row
    for _ in range(rep - 1):
        cl = _clone(row)
        _insert_after(table, cl, prev)
        rows.append(cl)
        prev = cl
    return rows[want]


def remove_row(table, row):
    table.removeChild(row)


def insert_rows_before(table, new_rows, ref_row):
    for r in new_rows:
        table.insertBefore(r, ref_row)


def clone_row(row):
    return _clone(row)


# --------------------------------------------------------------- ячейки

def logical_cells(row, upto):
    """{логический_столбец: элемент-ячейка} для столбцов 0..upto.

    Повторяющиеся ячейки в этом диапазоне расщепляются на отдельные.
    Хвостовые повторы (за upto) не трогаются.
    """
    lc = {}
    pos = 0
    for cell in list(row.childNodes):
        if pos > upto:
            break
        crep = _col_rep(cell)
        if crep == 1:
            lc[pos] = cell
            pos += 1
            continue
        # повтор в диапазоне — расщепить
        need_end = min(upto, pos + crep - 1)
        n_ind = need_end - pos + 1
        _del_attr(cell, TABLENS, "number-columns-repeated")
        lc[pos] = cell
        prev = cell
        for k in range(1, n_ind):
            cl = _clone(cell)
            _insert_after(row, cl, prev)
            lc[pos + k] = cl
            prev = cl
        remaining = crep - n_ind
        if remaining > 0:
            filler = _clone(cell)
            if remaining > 1:
                filler.setAttribute("numbercolumnsrepeated", str(remaining))
            _insert_after(row, filler, prev)
        pos += crep
    return lc


def _disp(num):
    return str(int(num)) if float(num) == int(num) else f"{num:.2f}".replace(".", ",")


def set_value(cell, value):
    """Записать значение в ячейку, сохранив её стиль.

    None/'' -> пустая ячейка; число -> float; иначе строка. Накрытые
    (covered) ячейки не трогаем.
    """
    if cell is None or cell.qname[1] == "covered-table-cell":
        return
    for ch in list(cell.childNodes):
        cell.removeChild(ch)
    if value is None or value == "":
        _del_attr(cell, OFFICENS, "value")
        _del_attr(cell, OFFICENS, "value-type")
        return
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, (int, float)):
        cell.setAttribute("valuetype", "float")
        num = int(value) if float(value) == int(value) else round(float(value), 2)
        cell.setAttribute("value", str(num))
        cell.addElement(P(text=_disp(num)))
    else:
        _del_attr(cell, OFFICENS, "value")
        cell.setAttribute("valuetype", "string")
        cell.addElement(_p_with_spaces(str(value)))


def _p_with_spaces(text):
    """Абзац <text:p>, где пробелы кодируются так, чтобы не «схлопнуться».

    XML/ODF сжимает ведущие и повторные пробелы; чтобы сохранить отступы и
    двойные пробелы (как в письмах и подписях), их кодируют элементом <text:s>.
    """
    p = P()
    buf = ""
    emitted = False
    i, n = 0, len(text)
    while i < n:
        if text[i] == " ":
            j = i
            while j < n and text[j] == " ":
                j += 1
            run = j - i
            if buf:
                p.addText(buf)
                buf = ""
                emitted = True
            if not emitted:
                p.addElement(S(c=run))          # ведущие пробелы — целиком в <text:s>
            elif run == 1:
                p.addText(" ")
            else:
                p.addText(" ")
                p.addElement(S(c=run - 1))
            emitted = True
            i = j
        else:
            buf += text[i]
            i += 1
    if buf:
        p.addText(buf)
    return p


def put_row(row, col_values, width=None):
    """Записать значения в строку: col_values — dict {столбец: значение}."""
    upto = width if width is not None else max(col_values)
    lc = logical_cells(row, upto)
    for col, val in col_values.items():
        set_value(lc.get(col), val)
    return lc


def cell_text(cell):
    out = []
    for p in cell.getElementsByType(P):
        for n in p.childNodes:
            if n.nodeType == 3:
                out.append(n.data)
            elif n.qname[1] == "s":          # <text:s c="N"/> — N пробелов
                c = n.getAttribute("c")
                out.append(" " * (int(c) if c else 1))
    return "".join(out)
