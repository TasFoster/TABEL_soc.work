"""Ядро функции «Реестр по оплате»: разбор готового реестра .ods в модель,
правка строк (обновить/добавить/удалить/обнулить) и ПЕРЕСБОРКА живых формул
(Итого/Всего/деньги) с правильными адресами по итоговой раскладке.

Опирается на низкоуровневые ODS-утилиты reestr.ods_build (общий модуль).
"""

import os
import re

from odf.opendocument import load
from odf.text import P

from ..reestr import ods_build as ob
from ..reestr.ods_writer import (MONTHS_PREP, SHEET_DENGI, SHEET_DOP, SHEET_GOS,
                                  _sheets)
from ..reestr.parser import extract_contract
from ..reestr.journal import norm_fio
from ..reestr.num2words_ru import rubles_kopecks_in_words
from .model import DengiRow, DopRow, GosBlock, GosClient, RegistryModel

_DENGI_REF_RE = re.compile(r"\[Гос_\.I(\d+)\]")


class ReestrOplataError(Exception):
    pass


# --------------------------------------------------------------- чтение ячеек
def _num(cell):
    """Число из ячейки: office:value если есть, иначе из текста «285,00»."""
    if cell is None:
        return None
    v = ob._ga(cell, "value")
    if v not in (None, ""):
        try:
            f = float(v)
            return int(f) if f == int(f) else f
        except ValueError:
            pass
    t = ob.cell_text(cell).strip()
    if not t:
        return None
    s = t.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        f = float(s)
        return int(f) if f == int(f) else f
    except ValueError:
        return t   # напр. «бесплатно»


def _cells(row, upto=10):
    return ob.logical_cells(row, upto)


def _txt(cells, col):
    c = cells.get(col)
    return ob.cell_text(c).strip() if c is not None else ""


def _label(row):
    """Текст первого значимого столбца строки (кол.1 для Гос_/Доп)."""
    return _txt(_cells(row, 2), 1)


def _is_num(s):
    return bool(re.fullmatch(r"\d+", (s or "").strip()))


# --------------------------------------------------------------- разбор Гос_
_DOP_LABELS = {"д.", "д"}


def _is_itogo_row(cells, label_b, label_c):
    """Строка Итого блока: SUM-формула в E ИЛИ метка «Итого» в B/C.

    В реальном (руками собранном) реестре метка «Итого» стоит то в столбце B,
    то в C, а иногда отсутствует вовсе — надёжный признак это SUM-формула в E.
    """
    e_formula = (ob._ga(cells.get(4), "formula") or "").upper()
    if "SUM(" in e_formula:
        return True
    return label_b.startswith(("Итого", "итого")) or label_c.startswith(("Итого", "итого"))


def _parse_gos(m):
    """Разбор листа Гос_ с якорем по точным маркерам «Социальный работник».

    Каждый блок — от маркера до следующего маркера (или до «Всего»). Имя
    работника — строка сразу за маркером; строка Итого определяется по формуле,
    а не по тексту метки (см. _is_itogo_row). Так разбор устойчив к «грязным»
    строкам ручного реестра (метка Итого в C, мусор в B, «Всего» в конце).
    """
    rows = list(ob.logical_rows(m.gos_table))

    for _start, row, _rep in rows:                # ячейка письма (сумма прописью)
        cells = _cells(row, 8)
        for col in range(1, 9):
            if "Предоставляем денежные средства" in _txt(cells, col):
                m.gos_letter_cell = cells.get(col)
                break
        if m.gos_letter_cell is not None:
            break

    marker_ix, vsego_ix = [], None
    for i, (_start, row, _rep) in enumerate(rows):
        label_b = _txt(_cells(row, 2), 1)
        if label_b == "Социальный работник":
            marker_ix.append(i)
        elif vsego_ix is None and label_b.startswith("Всего"):
            vsego_ix = i
            m.gos_vsego_row = row

    for bi, start_ix in enumerate(marker_ix):
        end_ix = marker_ix[bi + 1] if bi + 1 < len(marker_ix) else len(rows)
        block = GosBlock(worker_fio="", marker_row=rows[start_ix][1],
                         name_row=rows[start_ix + 1][1], itogo_row=None)
        block.worker_fio = _txt(_cells(block.name_row, 2), 1)
        for j in range(start_ix + 2, end_ix):
            row = rows[j][1]
            cells = _cells(row, 8)
            label_b, label_c = _txt(cells, 1), _txt(cells, 2)
            if label_b.startswith("Всего"):
                continue
            if _is_itogo_row(cells, label_b, label_c):
                block.itogo_row = row
                continue
            if label_b.lower() in _DOP_LABELS:
                block.dop_lines.append(_gos_client(row, cells, is_dop=True))
            elif _is_num(label_b) and label_c:
                block.clients.append(_gos_client(row, cells, is_dop=False))
        m.gos_blocks.append(block)
    return m


def _gos_client(row, cells, is_dop):
    fio_full = _txt(cells, 2)
    contract_raw = _txt(cells, 3)
    return GosClient(
        row=row, is_dop_line=is_dop,
        num=int(_label(row)) if _is_num(_label(row)) else 0,
        fio_full=fio_full, fio_norm=norm_fio(fio_full),
        contract_raw=contract_raw, contract=extract_contract(contract_raw),
        e_oplata=_num(cells.get(4)), f_koplate=_num(cells.get(5)),
        peresmotr=_txt(cells, 6), h_dop=_num(cells.get(7)))


# --------------------------------------------------------------- разбор Доп
def _parse_dop(m):
    for _start, row, _rep in ob.logical_rows(m.dop_table):
        cells = _cells(row, 10)
        label = _txt(cells, 1)
        if m.dop_letter_cell is None:
            for col in range(1, 11):
                if "Предоставляем денежные средства" in _txt(cells, col):
                    m.dop_letter_cell = cells.get(col)
                    break
        if label.startswith("ИТОГО") or label.startswith("Итого"):
            m.dop_itogo_row = row
            continue
        if _is_num(label) and _txt(cells, 2):
            fio_full = _txt(cells, 2)
            contract_raw = _txt(cells, 3)
            m.dop_rows.append(DopRow(
                row=row, num=int(label), fio_full=fio_full, fio_norm=norm_fio(fio_full),
                contract_raw=contract_raw, contract=extract_contract(contract_raw),
                date=_txt(cells, 4), summa=_num(cells.get(5)) or 0.0, mark=_txt(cells, 10)))
    return m


# --------------------------------------------------------------- разбор деньги
def _parse_dengi(m):
    # карта {1-based номер строки Гос_ -> GosBlock} по строкам Итого
    itg_by_rownum = {}
    for start, row, _rep in ob.logical_rows(m.gos_table):
        for b in m.gos_blocks:
            if b.itogo_row is row:
                itg_by_rownum[start + 1] = b
    for _start, row, _rep in ob.logical_rows(m.dengi_table):
        cells = _cells(row, 3)
        label0 = _txt(cells, 0)
        worker = _txt(cells, 1)
        formula = ob._ga(cells.get(2), "formula") or ""
        if label0.startswith("Итого") or worker.startswith("Итого"):
            m.dengi_itogo_row = row
            continue
        if _is_num(label0) and worker:
            ref = None
            mo = _DENGI_REF_RE.search(formula)
            if mo:
                ref = itg_by_rownum.get(int(mo.group(1)))
            if ref is None:
                ref = m.block_by_worker(worker)
            m.dengi_rows.append(DengiRow(row=row, worker_fio=worker, ref_block=ref))
    return m


def load_model(ods_path):
    doc = load(ods_path)
    sheets = _sheets(doc)
    gos = sheets.get(SHEET_GOS)
    if gos is None:
        raise ReestrOplataError("В файле не найден лист «Гос_» — это не реестр по оплате.")
    m = RegistryModel(doc=doc, gos_table=gos,
                      dop_table=sheets.get(SHEET_DOP), dengi_table=sheets.get(SHEET_DENGI))
    _parse_gos(m)
    if not m.gos_blocks:
        raise ReestrOplataError("Не распознан формат реестра (нет блоков соцработников).")
    if m.dop_table is not None:
        _parse_dop(m)
    if m.dengi_table is not None:
        _parse_dengi(m)
    return m


# ============================================================ ПРАВКА И ФОРМУЛЫ
# Логические столбцы листа Гос_ (0=A): B=№,C=ФИО,D=договор,E/F=суммы,G=метка,H=доп,I=итого
GOS_NUM, GOS_FIO, GOS_DOG, GOS_E, GOS_F, GOS_G, GOS_H, GOS_I = 1, 2, 3, 4, 5, 6, 7, 8
# Логические столбцы листа Доп: F=сумма,G=без НДС,NDS=ставка,NDSVAL=сумма НДС,J=с НДС,K=метка
DOP_NUM, DOP_FIO, DOP_DOG, DOP_DATE = 1, 2, 3, 4
DOP_F, DOP_G, DOP_NDS, DOP_NDSVAL, DOP_J, DOP_K = 5, 6, 7, 8, 9, 10
DENGI_SUMMA = 2                         # столбец C листа деньги


def _dogovor(contract):
    return f"Договор №{contract}" if contract else ""


def _set_cell(row, col, value):
    """Записать значение в логическую ячейку строки, сохранив стиль."""
    cell = ob.logical_cells(row, col).get(col)
    if cell is not None:
        ob.set_value(cell, value)
    return cell


def _set_formula(row, col, formula, cached=None):
    """Проставить живую формулу в ячейку + кэш-значение (для показа до пересчёта)."""
    cell = ob.logical_cells(row, col).get(col)
    if cell is None:
        return None
    for ch in list(cell.childNodes):
        cell.removeChild(ch)
    cell.setAttribute("formula", formula)
    if cached is None:
        return cell
    num = int(cached) if float(cached) == int(cached) else round(float(cached), 2)
    cell.setAttribute("valuetype", "float")
    cell.setAttribute("value", str(num))
    cell.addElement(P(text=ob._disp(num)))
    return cell


def _numeric(v):
    return float(v) if isinstance(v, (int, float)) else 0.0


def _block_sum(block, which):
    """Сумма столбца блока Гос_ по строкам-клиентам: which in {'e','f','h'}."""
    tot = 0.0
    for c in block.clients + block.dop_lines:
        tot += _numeric({"e": c.e_oplata, "f": c.f_koplate, "h": c.h_dop}[which])
    return round(tot, 2)


# ------------------------------------------------------- операции над строками
def set_gos_sums(client, e, f):
    """Проставить E (оплата по договору) и F (к оплате) клиента Гос_."""
    _set_cell(client.row, GOS_E, e)
    _set_cell(client.row, GOS_F, f)
    client.e_oplata, client.f_koplate = e, f


def set_gos_dop(client, h):
    """Проставить H (доп-сумма) клиента Гос_; пусто при 0/None."""
    val = h if h else None
    _set_cell(client.row, GOS_H, val)
    client.h_dop = val


def set_gos_peresmotr(client, on):
    _set_cell(client.row, GOS_G, "Пересмотр" if on else None)
    client.peresmotr = "Пересмотр" if on else ""


def zero_gos_client(client):
    """«Обнулить» снятого клиента: E=F=0, доп-сумма пусто, строка остаётся."""
    set_gos_sums(client, 0, 0)
    set_gos_dop(client, None)


def renumber_block(block):
    """Перенумеровать обычных клиентов блока 1..N (строки «Д.» не трогаем)."""
    for i, c in enumerate(block.clients, 1):
        _set_cell(c.row, GOS_NUM, i)
        c.num = i


def add_gos_client(m, block, fio_full, contract, e, f, h=None, peresmotr=False):
    """Добавить обычного клиента в блок Гос_ (строка перед «Д.»/Итого)."""
    proto = block.clients[-1].row if block.clients else (
        block.dop_lines[-1].row if block.dop_lines else None)
    if proto is None:
        raise ReestrOplataError("Нет строки-прототипа клиента для добавления.")
    new_row = ob.clone_row(proto)
    ob.put_row(new_row, {GOS_FIO: fio_full, GOS_DOG: _dogovor(contract),
                         GOS_E: e, GOS_F: f, GOS_H: h if h else None,
                         GOS_G: "Пересмотр" if peresmotr else None})
    anchor = block.dop_lines[0].row if block.dop_lines else block.itogo_row
    m.gos_table.insertBefore(new_row, anchor)
    c = GosClient(row=new_row, is_dop_line=False, num=0,
                  fio_full=fio_full, fio_norm=norm_fio(fio_full),
                  contract_raw=_dogovor(contract), contract=contract,
                  e_oplata=e, f_koplate=f,
                  peresmotr="Пересмотр" if peresmotr else "", h_dop=h if h else None)
    block.clients.append(c)
    renumber_block(block)
    return c


def set_dop_sum(dop_row, summa):
    """Проставить сумму строки Доп (F/G/J; НДС «Без НДС», сумма НДС 0)."""
    for col in (DOP_F, DOP_G, DOP_J):
        _set_cell(dop_row.row, col, summa)
    dop_row.summa = summa


def _renumber_dop(m):
    for i, r in enumerate(m.dop_rows, 1):
        _set_cell(r.row, DOP_NUM, i)
        r.num = i


def add_dop_row(m, fio_full, contract, date, summa, mark="новый"):
    """Добавить строку в лист Доп (в алфавит по ФИО), проставить метку «новый»."""
    if not m.dop_rows:
        raise ReestrOplataError("Нет строки-прототипа Доп для добавления.")
    new_row = ob.clone_row(m.dop_rows[-1].row)
    ob.put_row(new_row, {DOP_FIO: fio_full, DOP_DOG: _dogovor(contract), DOP_DATE: date,
                         DOP_F: summa, DOP_G: summa, DOP_NDS: "Без НДС",
                         DOP_NDSVAL: 0, DOP_J: summa, DOP_K: mark})
    key = norm_fio(fio_full)
    idx = next((i for i, r in enumerate(m.dop_rows) if r.fio_norm > key), len(m.dop_rows))
    anchor = m.dop_rows[idx].row if idx < len(m.dop_rows) else m.dop_itogo_row
    m.dop_table.insertBefore(new_row, anchor)
    dr = DopRow(row=new_row, num=0, fio_full=fio_full, fio_norm=key,
                contract_raw=_dogovor(contract), contract=contract,
                date=date, summa=summa, mark=mark)
    m.dop_rows.insert(idx, dr)
    _renumber_dop(m)
    return dr


# ----------------------------------------------------- пересборка живых формул
def _row_index_map(table):
    """{id(строка): 1-based номер строки в таблице} по текущей раскладке."""
    return {id(row): start + 1 for start, row, _rep in ob.logical_rows(table)}


_LETTER_AMOUNT_RE = re.compile(r"(в объеме\s+)[\d\s.,]+\s*\(?[^)]*\)")
_LETTER_MONTH_RE = re.compile(r"(филиалом в\s+)[А-Яа-яёЁ]+(\s+)\d{4}")


def _money2(total):
    return f"{round(float(total), 2):.2f}".replace(".", ",")


def _update_letter(cell, total, month="", year=""):
    """Обновить письмо «Предоставляем денежные средства в объеме X (прописью)…».

    Заменяет сумму цифрами и прописью (в скобках); при заданных месяце/годе —
    и «…оказанных филиалом в <месяце> <год> г.» (нужно при правке реестра
    прошлого месяца по новому журналу). Остальной текст письма сохраняется.
    """
    if cell is None:
        return
    text = ob.cell_text(cell)
    if "в объеме" not in text:
        return
    words = rubles_kopecks_in_words(total)
    new = _LETTER_AMOUNT_RE.sub(
        lambda mo: f"{mo.group(1)}{_money2(total)} ({words})", text, count=1)
    if month and year:
        new = _LETTER_MONTH_RE.sub(
            lambda mo: f"{mo.group(1)}{month}{mo.group(2)}{year}", new, count=1)
    if new != text:
        ob.set_value(cell, new)


def rebuild_formulas(m, period=None):
    """Пересобрать все живые формулы по итоговой раскладке (правильные адреса).

    Гос_: Итого блока = SUM диапазона клиентов (E/F/H), I = H+F той же строки;
    Всего = сумма ячеек Итого всех блоков. Деньги: ссылка на I блока Гос_ +
    ИТОГО. Доп: ИТОГО = SUM(F/G/J). Кэш-значения проставляются для показа до
    пересчёта в редакторе. При заданном period=(начало,конец) обновляются и
    письма (сумма прописью + месяц/год).
    """
    month = year = ""
    if period and period[0]:
        try:
            _, mm, yy = period[0].split(".")
            month, year = MONTHS_PREP[int(mm)], yy
        except Exception:  # noqa: BLE001
            pass
    _rebuild_gos(m, month, year)
    if m.dengi_table is not None:
        _rebuild_dengi(m)
    if m.dop_table is not None:
        _rebuild_dop(m, month, year)


def _rebuild_gos(m, month="", year=""):
    rmap = _row_index_map(m.gos_table)
    itogo_rownums = []
    for b in m.gos_blocks:
        ir = rmap.get(id(b.itogo_row))
        rownums = [rmap[id(c.row)] for c in b.clients + b.dop_lines if id(c.row) in rmap]
        if ir is None or not rownums:
            continue
        r1, r2 = min(rownums), max(rownums)
        se, sf, sh = _block_sum(b, "e"), _block_sum(b, "f"), _block_sum(b, "h")
        _set_formula(b.itogo_row, GOS_E, f"of:=SUM([.E{r1}:.E{r2}])", se)
        _set_formula(b.itogo_row, GOS_F, f"of:=SUM([.F{r1}:.F{r2}])", sf)
        _set_formula(b.itogo_row, GOS_H, f"of:=SUM([.H{r1}:.H{r2}])", sh)
        _set_formula(b.itogo_row, GOS_I, f"of:=[.H{ir}]+[.F{ir}]", round(sf + sh, 2))
        itogo_rownums.append(ir)
    _update_letter(m.gos_letter_cell,
                   round(sum(_block_sum(b, "f") for b in m.gos_blocks), 2), month, year)
    if m.gos_vsego_row is None or not itogo_rownums:
        return
    vr = rmap.get(id(m.gos_vsego_row))
    for col, letter, key in ((GOS_E, "E", "e"), (GOS_F, "F", "f"), (GOS_H, "H", "h")):
        terms = "+".join(f"[.{letter}{ir}]" for ir in itogo_rownums)
        total = round(sum(_block_sum(b, key) for b in m.gos_blocks), 2)
        _set_formula(m.gos_vsego_row, col, f"of:={terms}", total)
    if vr is not None:
        tot = round(sum(_block_sum(b, "f") + _block_sum(b, "h") for b in m.gos_blocks), 2)
        _set_formula(m.gos_vsego_row, GOS_I, f"of:=[.F{vr}]+[.H{vr}]", tot)


def _rebuild_dengi(m):
    gmap = _row_index_map(m.gos_table)
    dmap = _row_index_map(m.dengi_table)
    cnums = []
    for d in m.dengi_rows:
        if d.ref_block is None:
            continue
        ir = gmap.get(id(d.ref_block.itogo_row))
        if ir is None:
            continue
        cached = round(_block_sum(d.ref_block, "f") + _block_sum(d.ref_block, "h"), 2)
        _set_formula(d.row, DENGI_SUMMA, f"of:=[{SHEET_GOS}.I{ir}]", cached)
        if id(d.row) in dmap:
            cnums.append(dmap[id(d.row)])
    if m.dengi_itogo_row is not None and cnums:
        r1, r2 = min(cnums), max(cnums)
        total = round(sum(_block_sum(d.ref_block, "f") + _block_sum(d.ref_block, "h")
                          for d in m.dengi_rows if d.ref_block), 2)
        _set_formula(m.dengi_itogo_row, DENGI_SUMMA, f"of:=SUM([.C{r1}:.C{r2}])", total)


def _rebuild_dop(m, month="", year=""):
    total = round(sum(r.summa for r in m.dop_rows), 2)
    _update_letter(m.dop_letter_cell, total, month, year)
    if m.dop_itogo_row is None or not m.dop_rows:
        return
    dmap = _row_index_map(m.dop_table)
    rownums = [dmap[id(r.row)] for r in m.dop_rows if id(r.row) in dmap]
    if not rownums:
        return
    r1, r2 = min(rownums), max(rownums)
    _set_formula(m.dop_itogo_row, DOP_F, f"of:=SUM([.F{r1}:.F{r2}])", total)
    _set_formula(m.dop_itogo_row, DOP_G, f"of:=SUM([.G{r1}:.G{r2}])", total)
    _set_formula(m.dop_itogo_row, DOP_J, f"of:=SUM([.J{r1}:.J{r2}])", total)


def save(m, out_path):
    out_path = os.path.abspath(out_path)
    if os.path.exists(out_path):
        os.remove(out_path)
    m.doc.save(out_path)
    return out_path
