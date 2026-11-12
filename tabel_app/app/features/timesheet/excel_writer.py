"""Форма 0504421 по образцу ноября 2026, запись XLS без Microsoft Office.

Шапка 0..13, пара строк сотрудника 14..15, подписи 16..22.
Часы стоят над кодом дня. Все дни месяца расположены горизонтально.
"""
import os
import math
import re
from copy import deepcopy

import xlrd
import xlwt

from ...core.xls_util import ColourPalette, TemplateStyles, repeat_print_rows, solid_fill

SHEET_NAME = "Лист_1"
T_HEADER_LAST = 13
T_EMP_TOP, T_EMP_BOT = 14, 15
T_TAIL_FIRST, T_TAIL_LAST = 16, 22
C_HALF, C_TOTAL = 21, 40


class ExcelWriterError(Exception):
    pass


def day_column(day):
    if not 1 <= day <= 31:
        raise ValueError("День должен быть в диапазоне 1–31")
    return 5 + day if day <= 15 else 8 + day


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

    formatted = {}

    def cell_style(r, c):
        key = (r, c)
        if key not in formatted:
            style = deepcopy(styles.cell_style(sheet, r, c))
            if r >= T_EMP_TOP or (r in (2, 3) and c == 12):
                style.font.height = 200
                style.font.bold = True
            if r in (T_EMP_TOP, T_EMP_BOT) and c in (1, 3, 5):
                style.alignment.wrap = False
                style.alignment.shri = True
            formatted[key] = style
        return formatted[key]

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
                    ws.write(target, c, sheet.cell_value(r, c), cell_style(r, c))
    merged_styles = {}
    for a, b, x, y in sheet.merged_cells:
        for target in destinations(a):
            style = cell_style(a, x)
            if a == T_EMP_TOP and b == T_EMP_BOT + 1:
                key = sheet.cell_xf_index(a, x)
                if key not in merged_styles:
                    merged = deepcopy(style)
                    merged.borders.bottom = xlwt.Borders.THIN
                    merged_styles[key] = merged
                style = merged_styles[key]
            ws.write_merge(target, target + b - a - 1, x, y - 1,
                           sheet.cell_value(a, x), style)

    day_by_col = {day_column(day): day for day in range(1, 32)}
    nonworking = set(context.get("nonworking_days", []))

    # Кеш только на время одной генерации: нет зависимости от следующего месяца.
    write_styles = {}

    def write(r, c, value, source=None):
        src = r if source is None else source
        key = (src, c)
        style = write_styles.get(key)
        if style is None:
            style = cell_style(src, c)
            if src == T_EMP_TOP and c in (0, 1, 3, 5):
                style = deepcopy(style)
                style.borders.bottom = xlwt.Borders.THIN
            if src in (12, 13, T_EMP_TOP, T_EMP_BOT) and c in day_by_col:
                style = deepcopy(style)
                style.pattern = (solid_fill(weekend_colour)
                                 if day_by_col[c] in nonworking else xlwt.Pattern())
            if src in (T_EMP_TOP, T_EMP_BOT) and c in (47, 48):
                style = deepcopy(style)
                style.alignment.wrap = True
            write_styles[key] = style
        ws.write(r, c, value, style)

    write(5, 13, context.get("period_title", ""))
    write(6, 5, context.get("organization", ""))
    write(7, 5, context.get("department_name", ""))
    write(5, 38, context.get("report_date", ""))
    write(9, 38, context.get("formation_date", ""))
    write(8, 5, "корректирующий" if context.get("correction_number", 0) else "первичный")
    write(8, 38, context.get("correction_number", 0))  # 0 — первичный, 1 и далее — корректирующий
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
                         (3, str(emp.get("tab_number", ""))), (5, re.sub(r"^соц\.\s*работник$", "социальный работник", emp.get("position", "").strip(), flags=re.I))):
            write(top, c, value, T_EMP_TOP)
        write(top, 4, emp.get("oklad", ""), T_EMP_TOP)
        indicators = emp.get("indicators", {})
        write(bot, 4, indicators.get("rate", ""), T_EMP_BOT)
        for col, prefix in ((45, "holiday"), (46, "night")):
            write(top, col, indicators.get(prefix + "_days", ""), T_EMP_TOP)
            write(bot, col, indicators.get(prefix + "_hours", ""), T_EMP_BOT)
        reasons = emp.get("reasons", [])
        for col, items in ((47, reasons[:1]), (48, reasons[1:])):
            if not items:
                continue
            write(top, col, "\n".join("О" if r["code"] == "ОТ" else r["code"] for r in items), T_EMP_TOP)
            write(bot, col, "\n".join(str(r["days"]) for r in items), T_EMP_BOT)
            if len(items) > 1:
                for row in (top, bot):
                    ws.row(row).height = max(ws.row(row).height, len(items) * 240)
                    ws.row(row).height_mismatch = True
        for day in range(1, 32):
            write(top, day_column(day), "", T_EMP_TOP)
            write(bot, day_column(day), "", T_EMP_BOT)
        half = []
        for day, mark in emp["marks"].items():
            day = int(day)
            c = day_column(day)
            worked = isinstance(mark, (int, float))
            write(top, c, mark if worked else "", T_EMP_TOP)
            write(bot, c, "Я" if worked else ("О" if mark == "ОТ" else str(mark)), T_EMP_BOT)
            if day <= 15 and worked:
                half.append(mark)
        write(top, C_HALF, len(half), T_EMP_TOP)
        write(bot, C_HALF, sum(half), T_EMP_BOT)
        write(top, C_TOTAL, emp["worked_days"], T_EMP_TOP)
        write(bot, C_TOTAL, emp["worked_hours"], T_EMP_BOT)

    # Кадровый ответственный и исполнитель отделения — разные подписи.
    for r, c, value in (
        (17, 3, context.get("timesheet_hr_position", "Начальник ОК")),
        (17, 11, context.get("timesheet_hr_fio", "")),
        (20, 3, context.get("responsible_position", "")),
        (20, 11, context.get("responsible_fio", "")),
        (19, 37, context.get("timesheet_accountant_fio", "")),
    ):
        write(r + shift, c, value, r)

    # Размеры идентификационных колонок по содержимому. Длинный текст
    # остаётся в одной строке с уменьшением до ширины ячейки.
    def width_for(values, minimum, maximum):
        return int(min(maximum, max(minimum, max((len(str(v)) for v in values), default=0) + 2)) * 256)
    fio_width = width_for([e["fio"] for e in employees], 28, 55)
    ws.col(1).width = max(ws.col(1).width, fio_width - ws.col(2).width)
    ws.col(3).width = max(ws.col(3).width, width_for([e.get("tab_number", "") for e in employees], 12, 24))
    ws.col(5).width = max(ws.col(5).width, width_for([e.get("position", "") for e in employees] + ["социальный работник"], 22, 38))
    for i, employee in enumerate(employees):
        for r in (T_EMP_TOP + 2*i, T_EMP_BOT + 2*i):
            ws.row(r).height = max(ws.row(r).height, 300)
            ws.row(r).height_mismatch = True
    # Разрывы только между целыми парами. Запас по высоте учитывает
    # повторяемую шапку и поля A4, масштаб печати никогда не увеличивает лист.
    header_height = sum(ws.row(r).height for r in range(14))
    budget = 10500 - header_height
    used, breaks = 0, []
    for i in range(len(employees)):
        top = T_EMP_TOP + 2*i
        height = ws.row(top).height + ws.row(top+1).height
        if height > budget:
            raise ExcelWriterError("Слишком много строк неявок у одного сотрудника для страницы A4.")
        if used and used + height > budget:
            breaks.append((top, 0, sheet.ncols-1))
            used = 0
        used += height
    tail_height = sum(ws.row(r+shift).height for r in range(T_TAIL_FIRST, T_TAIL_LAST+1))
    if used + tail_height > budget:
        breaks.append((T_TAIL_FIRST+shift, 0, sheet.ncols-1))
    ws.horz_page_breaks = breaks
    repeat_print_rows(wb, 0, T_HEADER_LAST)
    ws.header_str = ws.footer_str = b""
    ws.portrait = False
    ws.paper_size_code = 9  # A4, ширина — один лист, высота по числу сотрудников
    total_width_points = sum(ws.col(c).width / 256 * 7 * 0.75 for c in range(sheet.ncols))
    ws.print_scaling = max(10, min(100, math.floor(790 / total_width_points * 100)))
    ws.fit_num_pages = 0
    ws.fit_width_to_pages = 1
    ws.fit_height_to_pages = 0
    ws.left_margin = ws.right_margin = 0.2
    ws.top_margin = ws.bottom_margin = 0.3
    wb.save(os.path.abspath(out_path))
    return os.path.abspath(out_path)
