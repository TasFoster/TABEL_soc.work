"""Контроллер «Графика проверок»: недели полугодия + ротация проверок -> .xlsx."""

import calendar
import datetime

from .writer import generate as _generate

MONTHS_NOM = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
              "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

DEFAULTS = {
    "org_full": "ГАУ СО «КЦСОН г. Саратова»",
    "district": "по Заводскому району",
    "director": "Колесниченко Е.И.",
    "zav": "Т.И. Шершнева",
    "dept_no": "9",
}

CHECK_WEEKDAY = 3  # четверг (как в образце): столбцы-недели по четвергам полугодия


def half_months(half):
    return range(1, 7) if int(half) == 1 else range(7, 13)


def half_year_weeks(half, year):
    """Список недель полугодия как (месяц, день) — по дням CHECK_WEEKDAY."""
    weeks = []
    for m in half_months(half):
        nd = calendar.monthrange(year, m)[1]
        for d in range(1, nd + 1):
            if datetime.date(year, m, d).weekday() == CHECK_WEEKDAY:
                weeks.append((m, d))
    return weeks


def build_schedule(workers, half, year):
    """Авто-ротация: каждую неделю — следующий активный соцработник по кругу.

    workers — [{'fio':..., 'self_control':bool}]. Самоконтроль исключается из ротации.
    Возвращает (weeks, marks): marks[(индекс_работника, индекс_недели)] = '///'."""
    weeks = half_year_weeks(half, year)
    active = [i for i, w in enumerate(workers) if not w.get("self_control")]
    marks = {}
    if active:
        for wk in range(len(weeks)):
            marks[(active[wk % len(active)], wk)] = "///"
    return weeks, marks


def generate(out_path, workers, half, year, dept_no=None, director=None, zav=None):
    weeks, marks = build_schedule(workers, half, year)
    ctx = {
        "org_full": DEFAULTS["org_full"], "district": DEFAULTS["district"],
        "director": director or DEFAULTS["director"],
        "zav": zav or DEFAULTS["zav"],
        "dept_no": dept_no or DEFAULTS["dept_no"],
        "half": int(half), "year": int(year),
    }
    return _generate(out_path, ctx, workers, weeks, marks)
