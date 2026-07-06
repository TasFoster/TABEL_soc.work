"""Расчёт отметок табеля для сотрудника за месяц.

Логика (выведена из заполненного образца, форма Т-13):
  • Рабочий день  -> число часов (8, либо 7 в предпраздничный день).
  • Выходной/праздник -> «В».
  • Период отсутствия (Б/ОТ/ОЖ и т.п.) перекрывает ВСЕ календарные дни периода,
    включая выходные внутри него (в эти дни ставится код, а не «В»).
  • Итог «дни» = число отработанных дней, «часы» = сумма отработанных часов.
  • «Неявки по причинам» = список (код, число дней) по каждому виду отсутствия.
"""

import calendar as _pycal
import datetime


def days_in_month(year, month):
    return _pycal.monthrange(year, month)[1]


def _absence_code_for_day(day, absences):
    """Возвращает код отсутствия для дня (или None). Первый подходящий период побеждает."""
    for a in absences:
        if a["start"] <= day <= a["end"]:
            return a["code"]
    return None


def build_marks(year, month, cal, absences, day_from=1, day_to=None):
    """Строит отметки сотрудника за месяц или его часть (полмесяца).

    absences: список словарей {"start": int, "end": int, "code": str}.
    day_from..day_to — заполняемый период (по умолчанию весь месяц). Отметки,
    итоги и неявки считаются ТОЛЬКО за дни периода; дни вне периода в marks не
    попадают (в табеле остаются пустыми).
    Возвращает словарь с ключами:
        ndays, marks (day->int|str), worked_days, worked_hours, reasons (list[(code, days)]).
    """
    ndays = days_in_month(year, month)
    day_from = max(1, int(day_from))
    day_to = ndays if day_to is None else min(ndays, int(day_to))
    marks = {}
    for day in range(day_from, day_to + 1):
        date = datetime.date(year, month, day)
        code = _absence_code_for_day(day, absences)
        if code:
            marks[day] = code
        elif cal.is_workday(date):
            marks[day] = cal.hours(date)
        else:
            marks[day] = "В"

    worked_days = sum(1 for m in marks.values() if isinstance(m, (int, float)))
    worked_hours = sum(m for m in marks.values() if isinstance(m, (int, float)))

    # Неявки по причинам: коды в порядке первого появления, с подсчётом дней
    # и днём первого появления (нужен, чтобы выбрать строку — верх/низ).
    order = []
    counts = {}
    first_day = {}
    for day in range(day_from, day_to + 1):
        m = marks[day]
        if isinstance(m, str) and m != "В":
            if m not in counts:
                order.append(m)
                counts[m] = 0
                first_day[m] = day
            counts[m] += 1
    reasons = [
        {"code": code, "days": counts[code], "first_day": first_day[code]}
        for code in order
    ]

    return {
        "ndays": ndays,
        "marks": marks,
        "worked_days": worked_days,
        "worked_hours": int(worked_hours) if float(worked_hours).is_integer() else worked_hours,
        "reasons": reasons,
    }


def validate_absences(absences, ndays):
    """Проверяет периоды отсутствия. Возвращает список текстовых ошибок (пустой = всё ок)."""
    errors = []
    for i, a in enumerate(absences, 1):
        s, e = a.get("start"), a.get("end")
        code = a.get("code")
        if not code:
            errors.append(f"Период {i}: не указан код отсутствия.")
            continue
        if not isinstance(s, int) or not isinstance(e, int):
            errors.append(f"Период {i} ({code}): даты должны быть числами.")
            continue
        if s < 1 or e > ndays or s > e:
            errors.append(f"Период {i} ({code}): неверный диапазон {s}–{e} (в месяце {ndays} дн.).")
    return errors
