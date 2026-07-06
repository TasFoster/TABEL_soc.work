"""Формирование «Приложения к табелю» в .xls без Microsoft Excel (через xlwt).

Лист строится программно (без шаблона), потому что исходный образец свёрстан
неаккуратно. Раскладка повторяет образец по смыслу 1:1:

  ЛЕВЫЙ блок «Расчёт …»  — детальная сетка по дням 1..N, по 2 строки на
                          сотрудника (гор. / част), колонка «Всего обслужено
                          чел./дни».
  ПРАВЫЙ блок «Приложение …» — сводка: Норма/день, Всего обслужено, плюс
                          начисление (оклад / (норма×раб.дни) × факт).

Microsoft Excel НЕ требуется: файл .xls пишется библиотекой xlwt.
"""

import os

import xlwt

from ...core.xls_util import ColourPalette, col_width, solid_fill, thin_borders

SHEET_NAME = "Приложение"
SHADE_WEEKEND = 0xE6E6E6  # светло-серый для нерабочих дней
BASE_FONT = "Calibri"
BASE_PT = 11

# Левый блок (1-based колонки)
L_NUM = 1
L_FIO = 2
L_SEC = 3
L_DAY1 = 4

# Строки
ROW_TITLE = 1
ROW_BRANCH = 2
ROW_OSOD = 3
ROW_HDR = 4
ROW_DAYNUM = 5
FIRST_WORKER_ROW = 6

_HORZ = {"center": xlwt.Alignment.HORZ_CENTER,
         "left": xlwt.Alignment.HORZ_LEFT,
         "right": xlwt.Alignment.HORZ_RIGHT}


class ExcelWriterError(Exception):
    pass


def _fmt(v):
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return int(f) if f == int(f) else round(f, 2)
    except (TypeError, ValueError):
        return v


class _Styles:
    """Кеш стилей xlwt по сигнатуре (чтобы не плодить XF-записи)."""

    def __init__(self, palette):
        self.pal = palette
        self._cache = {}

    def get(self, *, bold=False, align="center", wrap=False, fill=None,
            border=True, size=BASE_PT):
        key = (bold, align, wrap, fill, border, size)
        st = self._cache.get(key)
        if st is not None:
            return st
        st = xlwt.XFStyle()
        f = xlwt.Font()
        f.name = BASE_FONT
        f.height = size * 20
        f.bold = bold
        st.font = f
        al = xlwt.Alignment()
        al.horz = _HORZ[align]
        al.vert = xlwt.Alignment.VERT_CENTER
        al.wrap = 1 if wrap else 0
        st.alignment = al
        if border:
            st.borders = thin_borders()
        if fill is not None:
            st.pattern = solid_fill(self.pal.index_hex(fill))
        self._cache[key] = st
        return st


def generate(out_path, context, keep_open=False):
    out_path = os.path.abspath(out_path)
    workers = context["workers"]
    if not workers:
        raise ExcelWriterError("Нет сотрудников для формирования приложения.")

    ndays = context["ndays"]
    working = set(context["working_days"])

    L_TOTAL = L_DAY1 + ndays              # колонка «Всего» левого блока
    R_BASE = L_TOTAL + 2                  # пропуск 1 колонка
    R_NUM = R_BASE
    R_FIO = R_BASE + 1
    R_SEC = R_BASE + 2
    R_NORMA = R_BASE + 3
    R_TOTAL = R_BASE + 4
    R_OKLAD = R_BASE + 5
    R_NORMACD = R_BASE + 6
    R_NACH = R_BASE + 7

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet(SHEET_NAME, cell_overwrite_ok=True)
    palette = ColourPalette(wb)
    S = _Styles(palette)

    written = set()

    def mark(r1, c1, r2, c2):
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                written.add((r, c))

    def put(r, c, val, style):
        ws.write(r - 1, c - 1, _fmt(val), style)
        written.add((r, c))

    def put_merge(r1, c1, r2, c2, val, style):
        ws.write_merge(r1 - 1, r2 - 1, c1 - 1, c2 - 1, _fmt(val), style)
        mark(r1, c1, r2, c2)

    # --- Заголовки (без рамок) ---
    put_merge(ROW_TITLE, L_NUM, ROW_TITLE, L_TOTAL, context.get("calc_title", ""),
              S.get(bold=True, border=False))
    put_merge(ROW_TITLE, R_NUM, ROW_TITLE, R_NACH, context.get("title", ""),
              S.get(bold=True, border=False))
    put_merge(ROW_BRANCH, L_NUM, ROW_BRANCH, L_TOTAL, context.get("branch", ""),
              S.get(border=False))
    put_merge(ROW_BRANCH, R_NUM, ROW_BRANCH, R_NACH, context.get("branch", ""),
              S.get(border=False))
    put_merge(ROW_OSOD, L_NUM, ROW_OSOD, L_TOTAL, context.get("osod_line", ""),
              S.get(align="left", border=False))
    put_merge(ROW_OSOD, R_NUM, ROW_OSOD, R_NACH, context.get("osod_line", ""),
              S.get(align="left", border=False))

    hdr = S.get(bold=True)
    hdr_wrap = S.get(bold=True, wrap=True)

    # --- Шапка таблицы (левый блок) ---
    put_merge(ROW_HDR, L_NUM, ROW_DAYNUM, L_NUM, "№", hdr)
    put_merge(ROW_HDR, L_FIO, ROW_DAYNUM, L_FIO, "ФИО соц. работника", hdr_wrap)
    put_merge(ROW_HDR, L_SEC, ROW_DAYNUM, L_SEC, "сектор", hdr_wrap)
    put_merge(ROW_HDR, L_DAY1, ROW_HDR, L_DAY1 + ndays - 1, "Дни", hdr)
    put_merge(ROW_HDR, L_TOTAL, ROW_DAYNUM, L_TOTAL, "Всего обслужено чел./дни", hdr_wrap)
    for d in range(1, ndays + 1):
        c = L_DAY1 + (d - 1)
        st = hdr if d in working else S.get(bold=True, fill=SHADE_WEEKEND)
        put(ROW_DAYNUM, c, d, st)

    # --- Шапка таблицы (правый блок) ---
    put_merge(ROW_HDR, R_NUM, ROW_DAYNUM, R_NUM, "№", hdr)
    put_merge(ROW_HDR, R_FIO, ROW_DAYNUM, R_FIO, "ФИО соц. работника", hdr_wrap)
    put_merge(ROW_HDR, R_SEC, ROW_DAYNUM, R_SEC, "сектор", hdr_wrap)
    put_merge(ROW_HDR, R_NORMA, ROW_DAYNUM, R_NORMA, "Норма", hdr_wrap)
    put_merge(ROW_HDR, R_TOTAL, ROW_DAYNUM, R_TOTAL, "Всего обслужено чел./дни", hdr_wrap)
    put_merge(ROW_HDR, R_OKLAD, ROW_DAYNUM, R_OKLAD, "Оклад", hdr_wrap)
    put_merge(ROW_HDR, R_NORMACD, ROW_DAYNUM, R_NORMACD, "Норма чел/дней", hdr_wrap)
    put_merge(ROW_HDR, R_NACH, ROW_DAYNUM, R_NACH, "Начислено, руб.", hdr_wrap)

    cell = S.get()
    cell_left = S.get(align="left")
    cell_wknd = S.get(fill=SHADE_WEEKEND)

    # --- Сотрудники ---
    SECT = (("gor", "гор."), ("chast", "част"))
    row = FIRST_WORKER_ROW
    for w in workers:
        top, bottom = row, row + 1
        put_merge(top, L_NUM, bottom, L_NUM, w["n"], cell)
        put_merge(top, L_FIO, bottom, L_FIO, w["fio"], cell_left)
        put_merge(top, R_NUM, bottom, R_NUM, w["n"], cell)
        put_merge(top, R_FIO, bottom, R_FIO, w["fio"], cell_left)
        put_merge(top, R_OKLAD, bottom, R_OKLAD, w["oklad"], cell)
        for i, (skey, slabel) in enumerate(SECT):
            rr = top + i
            put(rr, L_SEC, slabel, cell)
            grid = w["grid"][skey]
            for d in range(1, ndays + 1):
                c = L_DAY1 + (d - 1)
                put(rr, c, grid.get(d), cell if d in working else cell_wknd)
            put(rr, L_TOTAL, w["totals"][skey], cell)
            put(rr, R_SEC, slabel, cell)
            put(rr, R_NORMA, w["norma"][skey], cell)
            put(rr, R_TOTAL, w["totals"][skey], cell)
            put(rr, R_NORMACD, w["norma_cheldney"][skey], cell)
            put(rr, R_NACH, round(w["nachisleno"][skey], 2), cell)
        row += 2

    # --- Итоги (левый блок: город / частный по дням) ---
    dt = context["daily_totals"]
    gt = context["grand_total"]
    tot_gor_row = row
    tot_chast_row = row + 1
    bold_left = S.get(bold=True, align="left")
    bold_c = S.get(bold=True)
    bold_wknd = S.get(bold=True, fill=SHADE_WEEKEND)
    put(tot_gor_row, L_FIO, "Итого город", bold_left)
    put(tot_chast_row, L_FIO, "Итого частный", bold_left)
    for d in range(1, ndays + 1):
        c = L_DAY1 + (d - 1)
        if d in working:
            put(tot_gor_row, c, dt["gor"][d], bold_c)
            put(tot_chast_row, c, dt["chast"][d], bold_c)
        else:
            put(tot_gor_row, c, None, bold_wknd)
            put(tot_chast_row, c, None, bold_wknd)
    put(tot_gor_row, L_TOTAL, gt["gor"], bold_c)
    put(tot_chast_row, L_TOTAL, gt["chast"], bold_c)
    # правый блок: суммы «Всего»
    put(tot_gor_row, R_SEC, "гор.", bold_c)
    put(tot_chast_row, R_SEC, "част", bold_c)
    put(tot_gor_row, R_TOTAL, gt["gor"], bold_c)
    put(tot_chast_row, R_TOTAL, gt["chast"], bold_c)

    # --- Рамка таблицы: добить пустые ячейки сетки тонкими границами ---
    last_row = tot_chast_row
    empty_b = S.get()
    for r in range(ROW_HDR, last_row + 1):
        for c in list(range(L_NUM, L_TOTAL + 1)) + list(range(R_NUM, R_NACH + 1)):
            if (r, c) not in written:
                ws.write(r - 1, c - 1, "", empty_b)

    # --- Подписи (без рамок) ---
    sig = last_row + 2
    put(sig, L_FIO, context.get("zav_line", ""), S.get(align="left", border=False))

    # --- Ширины колонок ---
    ws.col(L_NUM - 1).width = col_width(4)
    ws.col(L_FIO - 1).width = col_width(26)
    ws.col(L_SEC - 1).width = col_width(6)
    for d in range(ndays):
        ws.col(L_DAY1 - 1 + d).width = col_width(3.5)
    ws.col(L_TOTAL - 1).width = col_width(11)
    ws.col(R_FIO - 1).width = col_width(26)
    ws.col(R_NORMA - 1).width = col_width(7)
    ws.col(R_TOTAL - 1).width = col_width(11)
    ws.col(R_OKLAD - 1).width = col_width(9)
    ws.col(R_NORMACD - 1).width = col_width(9)
    ws.col(R_NACH - 1).width = col_width(12)

    # --- Печать: альбомная, вписать в 1 страницу по ширине ---
    ws.portrait = False
    ws.fit_num_pages = 1
    ws.fit_width_to_pages = 1
    ws.fit_height_to_pages = 0

    if os.path.exists(out_path):
        os.remove(out_path)
    wb.save(out_path)
    return out_path
