"""Форма 0504421 по образцу ноября 2026, запись XLS без Microsoft Office.

Шапка 0..13, пара строк сотрудника 14..15, подписи 16..22.
Часы стоят над кодом дня. Все дни месяца расположены горизонтально.
"""
import os
from copy import deepcopy

import xlrd
import xlwt

from ...core.xls_util import ColourPalette, TemplateStyles, repeat_print_rows, solid_fill

SHEET_NAME = "Лист_1"
T_HEADER_LAST = 13
T_EMP_TOP, T_EMP_BOT = 14, 15
T_TAIL_FIRST, T_TAIL_LAST = 16, 22
C_HALF, C_TOTAL = 22, 41


class ExcelWriterError(Exception):
    pass


def day_column(day):
    if not 1 <= day <= 31:
        raise ValueError("День должен быть в диапазоне 1–31")
    return 6 + day if day <= 15 else 9 + day


def generate(template_path, out_path, context, keep_open=False):
    """Размножить обезличенный прототип и заполнить форму данными контекста."""
    if not os.path.exists(template_path):
        raise ExcelWriterError(f"Не найден шаблон: {template_path}")
    employees = context["employees"]
    if not employees:
        raise ExcelWriterError("Нет сотрудников для формирования табеля.")
    rb = xlrd.open_workbook(template_path, formatting_info=True)
    sheet = rb.sheet_by_name(SHEET_NAME)
    wb = xlwt.Workbook(encoding="utf-8", style_compression=2)
    ws = wb.add_sheet(SHEET_NAME, cell_overwrite_ok=True)
    palette = ColourPalette(wb)
    styles = TemplateStyles(rb, wb, palette)
    weekend_colour = palette.index((192, 192, 192))
    shift = 2 * (len(employees) - 1)
    covered = {(r, c) for a, b, x, y in sheet.merged_cells
               for r in range(a, b) for c in range(x, y)}

    def destinations(r):
        if r < T_EMP_TOP:
            return [r]
        if r <= T_EMP_BOT:
            return [r + 2 * i for i in range(len(employees))]
        return [r + shift]

    for c, info in sheet.colinfo_map.items():
        ws.col(c).width = info.width
    for r in range(T_TAIL_LAST + 1):
        for target in destinations(r):
            info = sheet.rowinfo_map.get(r)
            if info:
                ws.row(target).height = info.height
                ws.row(target).height_mismatch = True
            for c in range(sheet.ncols):
                if (r, c) not in covered:
                    ws.write(target, c, sheet.cell_value(r, c), styles.cell_style(sheet, r, c))
    for a, b, x, y in sheet.merged_cells:
        for target in destinations(a):
            style = styles.cell_style(sheet, a, x)
            if a == T_EMP_TOP and b == T_EMP_BOT + 1:
                style = deepcopy(style)
                style.borders.bottom = xlwt.Borders.THIN
            ws.write_merge(target, target + b - a - 1, x, y - 1,
                           sheet.cell_value(a, x), style)

    day_by_col = {day_column(day): day for day in range(1, 32)}
    nonworking = set(context.get("nonworking_days", []))

    def write(r, c, value, source=None):
        src = r if source is None else source
        style = styles.cell_style(sheet, src, c)
        if src == T_EMP_TOP and c in (0, 1, 3, 5):
            style = deepcopy(style)
            style.borders.bottom = xlwt.Borders.THIN
        if src in (12, 13, T_EMP_TOP, T_EMP_BOT) and c in day_by_col:
            style = deepcopy(style)
            style.pattern = (solid_fill(weekend_colour)
                             if day_by_col[c] in nonworking else xlwt.Pattern())
        ws.write(r, c, value, style)

    write(5, 14, context.get("period_title", ""))
    write(6, 5, context.get("organization", ""))
    write(7, 5, context.get("department_name", ""))
    write(5, 39, context.get("report_date", ""))
    write(9, 39, context.get("formation_date", ""))
    write(8, 39, 0)  # первичный табель
    for day in range(1, 32):
        c = day_column(day)
        write(12, c, str(day) if day <= context.get("ndays", 31) else "")
        write(13, c, sheet.cell_value(13, c))
    if context.get("day_from", 1) > 1 or context.get("day_to", 31) < context.get("ndays", 31):
        write(12, C_TOTAL, "Всего дней (часов) явок (неявок) за период")

    for i, emp in enumerate(employees):
        top = T_EMP_TOP + 2 * i
        bot = top + 1
        for c, value in ((0, emp["n"]), (1, emp["fio"]),
                         (3, str(emp.get("tab_number", ""))), (5, emp.get("position", ""))):
            write(top, c, value, T_EMP_TOP)
        for day in range(1, 32):
            write(top, day_column(day), "", T_EMP_TOP)
            write(bot, day_column(day), "", T_EMP_BOT)
        half = []
        for day, mark in emp["marks"].items():
            day = int(day)
            c = day_column(day)
            worked = isinstance(mark, (int, float))
            write(top, c, mark if worked else "", T_EMP_TOP)
            write(bot, c, "Я" if worked else str(mark), T_EMP_BOT)
            if day <= 15 and worked:
                half.append(mark)
        write(top, C_HALF, len(half), T_EMP_TOP)
        write(bot, C_HALF, sum(half), T_EMP_BOT)
        write(top, C_TOTAL, emp["worked_days"], T_EMP_TOP)
        write(bot, C_TOTAL, emp["worked_hours"], T_EMP_BOT)

    # Кадровый ответственный и исполнитель отделения — разные подписи.
    for r, c, value in (
        (17, 3, context.get("timesheet_hr_position", "Начальник ОК")),
        (17, 12, context.get("timesheet_hr_fio", "")),
        (20, 3, context.get("responsible_position", "")),
        (20, 12, context.get("responsible_fio", "")),
        (19, 38, context.get("timesheet_accountant_fio", "")),
    ):
        write(r + shift, c, value, r)

    repeat_print_rows(wb, 0, T_HEADER_LAST)
    ws.header_str = ws.footer_str = b""
    ws.portrait = False
    ws.paper_size_code = 9  # A4, ширина — один лист, высота по числу сотрудников
    ws.fit_num_pages = 1
    ws.fit_width_to_pages = 1
    ws.fit_height_to_pages = 0
    ws.left_margin = ws.right_margin = 0.2
    ws.top_margin = ws.bottom_margin = 0.3
    wb.save(os.path.abspath(out_path))
    return os.path.abspath(out_path)
