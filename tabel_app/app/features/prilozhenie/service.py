"""Связующий слой «Приложения к табелю»: БД + календарь + расчёт -> .xls."""

import calendar as _cal
import datetime

from ..timesheet.calendar_ru import MONTHS_NOM, ProductionCalendar
from . import storage
from .calc import compute
from .excel_writer import generate as _generate


def days_in_month(year, month):
    return _cal.monthrange(year, month)[1]


def get_calendar():
    settings = {}
    cal_data = storage.get_calendar()
    return ProductionCalendar(cal_data, 8, 7)


def working_days(year, month, cal=None):
    cal = cal or get_calendar()
    nd = days_in_month(year, month)
    return [d for d in range(1, nd + 1)
            if cal.is_workday(datetime.date(year, month, d))]


def _month_lower(month):
    return MONTHS_NOM[month].lower()


def build_context(dept, year, month, workers, result):
    nd = days_in_month(year, month)
    per = f"{_month_lower(month)} {year} года"
    branch = dept.get("organization", "")
    pos = dept.get("responsible_position", "") or ""
    fio = dept.get("responsible_fio", "") or ""
    osod_line = f"{pos}  {fio}".strip()
    workers_ctx = []
    for w in result["workers"]:
        workers_ctx.append(w)
    return {
        "calc_title": f"Расчет приложения к табелю учета рабочего времени за {per}",
        "title": f"Приложение к табелю учета рабочего времени за {per}",
        "branch": branch,
        "osod_line": osod_line,
        "zav_line": osod_line,
        "month_title": f"{MONTHS_NOM[month]} {year} года",
        "ndays": nd,
        "working_days": result["working_days"],
        "workers": workers_ctx,
        "daily_totals": result["daily_totals"],
        "combined_daily": result["combined_daily"],
        "grand_total": result["grand_total"],
        "warnings": result["warnings"],
    }


def compute_month(dept_id, year, month):
    """Собрать данные и посчитать приложение (без записи в файл)."""
    storage.ensure_ready()
    dept = storage.get_department(dept_id)
    workers = storage.get_workers(dept_id, only_active=True)
    wd = working_days(year, month)
    nd = days_in_month(year, month)
    periods = storage.get_periods(dept_id, year, month)
    absences = storage.get_absences(dept_id, year, month)
    redistributions = storage.get_redistributions(dept_id, year, month)
    result = compute(workers, wd, nd, periods, absences, redistributions)
    return dept, workers, result


def generate_prilozhenie(dept_id, year, month, out_path, keep_open=False):
    dept, workers, result = compute_month(dept_id, year, month)
    context = build_context(dept, year, month, workers, result)
    _generate(out_path, context, keep_open=keep_open)
    return out_path, result
