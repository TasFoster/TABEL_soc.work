"""Расчёт чел/дней, перераспределения и начисления для «Приложения к табелю».

Чистые функции (без БД и Excel) — чтобы логику можно было проверять отдельно.

Алгоритм построения посуточных значений на сотрудника/сектор:
  1. База = постоянная нагрузка сотрудника по сектору (на каждый рабочий день).
  2. Переопределения по периодам (Period) заменяют значение на своих днях.
  3. Отсутствия (Absence) обнуляют ОБА сектора на днях отсутствия.
  4. Перераспределение (Redistribution) переносит value чел/день по сектору
     от одного сотрудника другому на указанные дни (после обнулений).
  Итог «Всего обслужено чел./дни» = сумма посуточных значений по рабочим дням.
  Начисление по сектору = оклад / (норма_сектор × раб.дни) × факт_сектор.
"""

from .model import SECTORS, THRESHOLD


def _days_range(day_from, day_to):
    lo, hi = sorted((int(day_from), int(day_to)))
    return range(lo, hi + 1)


def compute(workers, working_days, ndays, periods=None, absences=None,
            redistributions=None):
    """Посчитать всё приложение.

    workers — список model.Worker (только участвующие/активные).
    working_days — отсортированный список номеров рабочих дней месяца.
    ndays — число дней в месяце.
    Возвращает словарь с посуточной сеткой, итогами, начислением и предупреждениями.
    """
    periods = periods or []
    absences = absences or []
    redistributions = redistributions or []
    workset = set(working_days)
    nwork = len(working_days)

    by_id = {w.employee_id: w for w in workers}

    # day_value[(emp_id, sector)][day] = значение чел/день
    day_value = {}
    for w in workers:
        for sector in SECTORS:
            base = w.load(sector)
            day_value[(w.employee_id, sector)] = {d: base for d in working_days}

    # 2) периоды
    for p in periods:
        key = (p.employee_id, p.sector)
        if key not in day_value:
            continue
        for d in _days_range(p.day_from, p.day_to):
            if d in workset:
                day_value[key][d] = p.value

    # 3) отсутствия — обнуляют оба сектора
    for a in absences:
        for sector in SECTORS:
            key = (a.employee_id, sector)
            if key not in day_value:
                continue
            for d in _days_range(a.day_from, a.day_to):
                if d in workset:
                    day_value[key][d] = 0

    # 4) перераспределение
    for r in redistributions:
        for d in _days_range(r.day_from, r.day_to):
            if d not in workset:
                continue
            fk = (r.from_employee_id, r.sector)
            tk = (r.to_employee_id, r.sector)
            if fk in day_value:
                day_value[fk][d] = max(0, day_value[fk][d] - r.value)
            if tk in day_value:
                day_value[tk][d] = day_value[tk][d] + r.value

    # Сборка результатов
    workers_out = []
    daily_totals = {s: {d: 0 for d in working_days} for s in SECTORS}
    warnings = []
    for w in workers:
        wrow = {
            "employee_id": w.employee_id,
            "n": w.n,
            "fio": w.fio,
            "oklad": w.oklad,
            "grid": {},
            "totals": {},
            "norma": {"gor": w.norma_gor, "chast": w.norma_chast},
            "norma_cheldney": {},
            "nachisleno": {},
        }
        for sector in SECTORS:
            vals = day_value[(w.employee_id, sector)]
            grid = {d: (vals[d] if d in workset else None) for d in range(1, ndays + 1)}
            total = sum(vals[d] for d in working_days)
            wrow["grid"][sector] = grid
            wrow["totals"][sector] = total
            norma_cd = w.norma(sector) * nwork
            wrow["norma_cheldney"][sector] = norma_cd
            wrow["nachisleno"][sector] = (
                (w.oklad / norma_cd * total) if (w.oklad and norma_cd) else 0
            )
            for d in working_days:
                daily_totals[sector][d] += vals[d]
                if vals[d] > THRESHOLD[sector]:
                    warnings.append(
                        f"{w.fio}: день {d}, {('город' if sector=='gor' else 'частный')} "
                        f"{_fmt(vals[d])} > {THRESHOLD[sector]}"
                    )
        workers_out.append(wrow)

    grand = {s: sum(daily_totals[s].values()) for s in SECTORS}
    combined_daily = {d: daily_totals["gor"][d] + daily_totals["chast"][d]
                      for d in working_days}

    return {
        "working_days": list(working_days),
        "nworkdays": nwork,
        "ndays": ndays,
        "workers": workers_out,
        "daily_totals": daily_totals,
        "combined_daily": combined_daily,
        "grand_total": grand,
        "grand_combined": grand["gor"] + grand["chast"],
        "warnings": warnings,
    }


def freed_per_day(worker, sector, default_value=None):
    """Сколько чел/день освобождается у отсутствующего сотрудника по сектору
    (для авто-черновика перераспределения) — это его обычная нагрузка."""
    if default_value is not None:
        return default_value
    return worker.load(sector)


def _fmt(v):
    return int(v) if float(v) == int(v) else round(v, 2)
