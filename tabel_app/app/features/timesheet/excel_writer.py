"""Запись готового табеля в файл .xls без Microsoft Excel (через xlrd + xlwt).

Открывает канонический шаблон (шапка + 1 строка-прототип сотрудника + подписи),
переносит его оформление (шрифты, границы, заливка, объединения, ширины/высоты)
в новую книгу xlwt, размножает строку-прототип под нужное количество людей и
заполняет данные. Microsoft Excel НЕ требуется.

Стратегия:
  * строки шапки (0..19) копируются 1:1;
  * прототип сотрудника (строки 20..21) копируется N раз (employee_i -> 20+2i);
  * «хвост» (разделитель + подписи, строки 22..26) сдвигается вниз на 2*(N-1);
  * объединения и динамические ячейки (шапка/дни/итоги/подписи) переписываются.
"""

import os
from copy import deepcopy

import xlrd
import xlwt

from ...core.xls_util import ColourPalette, TemplateStyles, solid_fill

SHEET_NAME = "Лист1"
SHADE_RGB = (51, 51, 153)   # заливка нерабочих дней (как в исходном табеле)

# --- Раскладка шаблона (0-based) ---
T_HEADER_LAST = 19          # строки 0..19 — шапка (копируются 1:1)
T_EMP_TOP = 20              # строка-прототип: верх сотрудника
T_EMP_BOT = 21             # низ сотрудника
T_TAIL_FIRST = 22          # разделитель + подписи
T_TAIL_LAST = 26

ROW_ORG = 5                 # A6 — организация
ROW_DEPT = 8                # A9 — отделение
ROW_MONTH = 9               # A10 — месяц/год
ROW_HDR_TOP = 14            # номера дней 1-15
ROW_HDR_BOT = 18           # номера дней 16-31
COL_DAY_FIRST = 4          # E
COL_DAY_LAST = 19          # T

# Колонки сотрудника (0-based)
C_NUM = 0
C_FIO = 1
C_TAB = 2
C_OKLAD = 3
C_U = 20                    # итог: дни (верх) / часы (низ)
REASON_COLS = [(29, 30), (31, 32), (33, 34)]  # (код, дни) — «неявки по причинам»

# Подписи (0-based; COM: E=5, S=19, W=23, Y=25)
C_SIG_E = 4
C_SIG_S = 18
C_SIG_W = 22
C_SIG_Y = 24
T_SIG0, T_SIG1, T_SIG2 = 23, 24, 25  # строки подписей в шаблоне


class ExcelWriterError(Exception):
    pass


def day_cell(day):
    """(смещение строки 0=верх/1=низ, колонка) для дня месяца."""
    if day <= 15:
        return 0, COL_DAY_FIRST + (day - 1)
    return 1, COL_DAY_FIRST + (day - 16)


def _num(v):
    if v is None or v == "":
        return ""
    try:
        f = float(v)
        return int(f) if f == int(f) else round(f, 2)
    except (TypeError, ValueError):
        return v


def _mark(mark):
    return mark if isinstance(mark, (int, float)) else str(mark)


def _norm(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


def generate(template_path, out_path, context, keep_open=False):
    """Сформировать табель (см. build_context в service.py)."""
    template_path = os.path.abspath(template_path)
    out_path = os.path.abspath(out_path)
    if not os.path.exists(template_path):
        raise ExcelWriterError(f"Не найден шаблон: {template_path}")

    employees = context["employees"]
    n = len(employees)
    if n == 0:
        raise ExcelWriterError("Нет сотрудников для формирования табеля.")

    rb = xlrd.open_workbook(template_path, formatting_info=True)
    sheet = rb.sheet_by_name(SHEET_NAME)
    ncols = sheet.ncols

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet(SHEET_NAME, cell_overwrite_ok=True)
    palette = ColourPalette(wb)
    H = TemplateStyles(rb, wb, palette)
    blue_idx = palette.index(SHADE_RGB)
    shift = 2 * (n - 1)

    # --- объединённые ячейки шаблона ---
    merges = sheet.merged_cells
    covered, topleft = set(), set()
    for (rlo, rhi, clo, chi) in merges:
        topleft.add((rlo, clo))
        for r in range(rlo, rhi):
            for c in range(clo, chi):
                if (r, c) != (rlo, clo):
                    covered.add((r, c))

    def copy_cells(src_tr, out_r):
        """Скопировать все «свободные» ячейки строки шаблона в выходную строку."""
        for c in range(ncols):
            if (src_tr, c) in covered or (src_tr, c) in topleft:
                continue
            ws.write(out_r, c, _norm(sheet.cell(src_tr, c).value),
                     H.cell_style(sheet, src_tr, c))

    def set_height(src_tr, out_r):
        ri = sheet.rowinfo_map.get(src_tr)
        if ri is not None and ri.height_mismatch:
            ws.row(out_r).height_mismatch = True
            ws.row(out_r).height = ri.height

    # ширины колонок
    for c, ci in sheet.colinfo_map.items():
        if c < 256:
            ws.col(c).width = ci.width

    # 1) шапка 0..19
    for tr in range(0, T_HEADER_LAST + 1):
        copy_cells(tr, tr)
        set_height(tr, tr)
    # 2) сотрудники: размножить прототип
    for i in range(n):
        top = T_EMP_TOP + 2 * i
        copy_cells(T_EMP_TOP, top)
        copy_cells(T_EMP_BOT, top + 1)
        set_height(T_EMP_TOP, top)
        set_height(T_EMP_BOT, top + 1)
    # 3) хвост (разделитель + подписи) со сдвигом
    for tr in range(T_TAIL_FIRST, T_TAIL_LAST + 1):
        copy_cells(tr, tr + shift)
        set_height(tr, tr + shift)

    # --- объединения ---
    def out_ranges(rlo, rhi):
        if rhi - 1 <= T_HEADER_LAST:
            return [(rlo, rhi - 1)]
        if rlo == T_EMP_TOP and rhi - 1 <= T_EMP_BOT:
            span = rhi - 1 - rlo
            return [(T_EMP_TOP + 2 * i, T_EMP_TOP + 2 * i + span) for i in range(n)]
        return [(rlo + shift, rhi - 1 + shift)]

    for (rlo, rhi, clo, chi) in merges:
        val = _norm(sheet.cell(rlo, clo).value)
        style = H.cell_style(sheet, rlo, clo)
        for (o1, o2) in out_ranges(rlo, rhi):
            ws.write_merge(o1, o2, clo, chi - 1, val, style)

    # ============ переписать динамические ячейки ============

    # шапка: организация / отделение (центр) / месяц (центр)
    ws.write(ROW_ORG, 0, context.get("organization", ""), H.cell_style(sheet, ROW_ORG, 0))
    ws.write(ROW_DEPT, 0, context.get("department_name", ""), _centered(H, sheet, ROW_DEPT, 0))
    ws.write(ROW_MONTH, 0, context.get("month_title", ""), _centered(H, sheet, ROW_MONTH, 0))

    # заголовок с номерами дней: подсветить нерабочие дни целевого месяца
    nonworking = set(context.get("nonworking_days", []))
    ndays = context.get("ndays", 31)
    plain_top = _no_fill(H.cell_style(sheet, ROW_HDR_TOP, COL_DAY_FIRST))
    blue_top = _with_fill(plain_top, blue_idx)
    plain_bot = _no_fill(H.cell_style(sheet, ROW_HDR_BOT, COL_DAY_FIRST))
    blue_bot = _with_fill(plain_bot, blue_idx)
    for d in range(1, 16):
        c = COL_DAY_FIRST + (d - 1)
        st = blue_top if (d in nonworking and d <= ndays) else plain_top
        ws.write(ROW_HDR_TOP, c, _norm(sheet.cell(ROW_HDR_TOP, c).value), st)
    ws.write(ROW_HDR_TOP, COL_DAY_LAST,
             _norm(sheet.cell(ROW_HDR_TOP, COL_DAY_LAST).value), plain_top)
    for d in range(16, 32):
        c = COL_DAY_FIRST + (d - 16)
        st = blue_bot if (d in nonworking and d <= ndays) else plain_bot
        ws.write(ROW_HDR_BOT, c, _norm(sheet.cell(ROW_HDR_BOT, c).value), st)

    # сотрудники
    day_plain_top = _no_fill(H.cell_style(sheet, T_EMP_TOP, COL_DAY_FIRST))
    day_blue_top = _with_fill(day_plain_top, blue_idx)
    day_plain_bot = _no_fill(H.cell_style(sheet, T_EMP_BOT, COL_DAY_FIRST))
    day_blue_bot = _with_fill(day_plain_bot, blue_idx)
    st_num = H.cell_style(sheet, T_EMP_TOP, C_NUM)
    st_fio_top = H.cell_style(sheet, T_EMP_TOP, C_FIO)
    st_fio_bot = H.cell_style(sheet, T_EMP_BOT, C_FIO)
    st_tab = H.cell_style(sheet, T_EMP_TOP, C_TAB)
    st_oklad = H.cell_style(sheet, T_EMP_TOP, C_OKLAD)
    st_u_top = H.cell_style(sheet, T_EMP_TOP, C_U)
    st_u_bot = H.cell_style(sheet, T_EMP_BOT, C_U)

    for i, emp in enumerate(employees):
        top = T_EMP_TOP + 2 * i
        bot = top + 1
        ws.write(top, C_NUM, emp["n"], st_num)              # объединённая (верх)
        ws.write(top, C_FIO, emp["fio"], st_fio_top)
        ws.write(bot, C_FIO, emp.get("position", ""), st_fio_bot)
        ws.write(top, C_TAB, str(emp.get("tab_number", "")), st_tab)
        ws.write(top, C_OKLAD, _num(emp.get("oklad")), st_oklad)
        # очистить область дней (содержимое + заливку прототипа), затем отметки
        for c in range(COL_DAY_FIRST, COL_DAY_LAST + 1):
            ws.write(top, c, "", day_plain_top)
            ws.write(bot, c, "", day_plain_bot)
        for day, mark in emp["marks"].items():
            ro, c = day_cell(int(day))
            r = top + ro
            blue = (mark == "В")
            if ro == 0:
                st = day_blue_top if blue else day_plain_top
            else:
                st = day_blue_bot if blue else day_plain_bot
            ws.write(r, c, _mark(mark), st)
        ws.write(top, C_U, emp["worked_days"], st_u_top)
        ws.write(bot, C_U, emp["worked_hours"], st_u_bot)
        for j, reason in enumerate(emp.get("reasons", [])[: len(REASON_COLS)]):
            code_col, days_col = REASON_COLS[j]
            isbot = reason.get("first_day", 1) >= 16
            rr = bot if isbot else top
            src = T_EMP_BOT if isbot else T_EMP_TOP
            ws.write(rr, code_col, reason["code"], H.cell_style(sheet, src, code_col))
            ws.write(rr, days_col, reason["days"], H.cell_style(sheet, src, days_col))

    # подписи (со сдвигом)
    ws.write(T_SIG0 + shift, C_SIG_E,
             f" ответственное лицо________{context.get('responsible_fio', '')}",
             H.cell_style(sheet, T_SIG0, C_SIG_E))
    ws.write(T_SIG1 + shift, C_SIG_E,
             f"должность  {context.get('responsible_position', '')}",
             H.cell_style(sheet, T_SIG1, C_SIG_E))
    ws.write(T_SIG2 + shift, C_SIG_E, context.get("approve_line", ""),
             H.cell_style(sheet, T_SIG2, C_SIG_E))
    ws.write(T_SIG0 + shift, C_SIG_S, context.get("director_label", ""),
             H.cell_style(sheet, T_SIG0, C_SIG_S))
    ws.write(T_SIG0 + shift, C_SIG_W, "______", H.cell_style(sheet, T_SIG0, C_SIG_W))
    ws.write(T_SIG0 + shift, C_SIG_Y, f" {context.get('director_fio', '')}",
             H.cell_style(sheet, T_SIG0, C_SIG_Y))
    ws.write(T_SIG2 + shift, C_SIG_S, context.get("hr_specialist_line", ""),
             H.cell_style(sheet, T_SIG2, C_SIG_S))

    ws.portrait = False  # Т-13 — альбомная

    if os.path.exists(out_path):
        os.remove(out_path)
    wb.save(out_path)
    return out_path


def _centered(H, sheet, r, c):
    st = deepcopy(H.cell_style(sheet, r, c))
    st.alignment.horz = xlwt.Alignment.HORZ_CENTER
    return st


def _no_fill(style):
    st = deepcopy(style)
    st.pattern = xlwt.Pattern()  # NO_PATTERN
    return st


def _with_fill(style, colour_index):
    st = deepcopy(style)
    st.pattern = solid_fill(colour_index)
    return st
