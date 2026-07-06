"""Связующий слой: данные + календарь + расчёт -> контекст для записи в Excel."""

import datetime

from . import storage
from .calendar_ru import ProductionCalendar, month_title
from .excel_writer import generate as _generate
from .timesheet import build_marks, days_in_month


def get_calendar(settings=None):
    settings = settings or storage.load_settings()
    cal_data = storage.load_calendar()
    return ProductionCalendar(
        cal_data,
        settings.get("workday_hours", 8),
        settings.get("preholiday_hours", 7),
    )


def build_context(dept, year, month, absences_by_emp, settings=None, period=None):
    """Собрать контекст табеля.

    absences_by_emp: {employee_n: [{start, end, code}, ...]}.
    period: None — весь месяц; (day_from, day_to) — половина месяца (заполняются
    только дни периода, итоги/неявки — за период; форма Т-13 та же).
    """
    settings = settings or storage.load_settings()
    cal = get_calendar(settings)

    ndays = days_in_month(year, month)
    day_from, day_to = (1, ndays) if not period else (
        max(1, int(period[0])), min(ndays, int(period[1])))
    nonworking_days = [
        d for d in range(day_from, day_to + 1)
        if not cal.is_workday(datetime.date(year, month, d))
    ]

    employees_out = []
    for emp in dept["employees"]:
        absences = absences_by_emp.get(emp["n"], [])
        res = build_marks(year, month, cal, absences, day_from, day_to)
        employees_out.append(
            {
                "n": emp["n"],
                "fio": emp["fio"],
                "tab_number": emp.get("tab_number", ""),
                "oklad": emp.get("oklad", ""),
                "position": emp.get("position", ""),
                "marks": res["marks"],
                "worked_days": res["worked_days"],
                "worked_hours": res["worked_hours"],
                "reasons": res["reasons"],
            }
        )

    return {
        "organization": dept.get("organization", ""),
        "department_name": dept.get("name", ""),
        "month_title": month_title(month, year),
        "ndays": ndays,
        "nonworking_days": nonworking_days,
        "responsible_fio": dept.get("responsible_fio", ""),
        "responsible_position": dept.get("responsible_position", ""),
        "director_label": settings.get("director_label", ""),
        "director_fio": settings.get("director_fio", ""),
        "approve_line": settings.get("approve_line", ""),
        "hr_specialist_line": settings.get("hr_specialist_line", ""),
        "employees": employees_out,
    }


def generate_timesheet(dept, year, month, absences_by_emp, out_path,
                       settings=None, keep_open=False, period=None):
    context = build_context(dept, year, month, absences_by_emp, settings, period)
    return _generate(storage.template_path(), out_path, context, keep_open=keep_open)
