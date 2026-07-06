"""Чтение источника «Отчёт по количеству оказанных услуг … в разбивке» (.xls, xlrd).

Файл — выгрузка по ОДНОМУ соцработнику за месяц: шапка (организация, отделение,
период, «Социальный работник …»), строка заголовков (№п/п, ФИО, Дата рождения, Пол,
Всего услуг, далее колонки услуг) и строки получателей. Колонки ищутся по заголовкам.
"""

import re

import xlrd

from .model import Client, normalize

_PERIOD_RE = re.compile(r"с\s*(\d{2}\.\d{2}\.\d{4})\s*по\s*(\d{2}\.\d{2}\.\d{4})")
_DEPT_RE = re.compile(r"№\s*(\d+)")


class GosParseError(Exception):
    pass


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return 0.0


def _cells(sheet, r):
    return [sheet.cell_value(r, c) for c in range(sheet.ncols)]


def _find_worker(rows_text):
    """ФИО соцработника из строки «… Социальный работник <ФИО>»."""
    for t in rows_text:
        low = t.lower()
        i = low.find("социальный работник")
        if i >= 0:
            name = t[i + len("социальный работник"):].strip(" :.-\t")
            if name:
                return name
    return ""


def _find_dept(rows_text):
    """Номер отделения из строки с «Отделение … №N»."""
    for t in rows_text:
        if "отделени" in t.lower():
            m = _DEPT_RE.search(t)
            if m:
                return m.group(1)
    return ""


def _find_period(rows_text):
    """(period_str, start_date) из строки «за период с DD.MM.YYYY по DD.MM.YYYY»."""
    for t in rows_text:
        m = _PERIOD_RE.search(t)
        if m:
            return f"{m.group(1)}-{m.group(2)}", m.group(1)
    return "", ""


def _find_header_row(sheet):
    """Строка заголовков таблицы: есть ячейка с «ФИО» и ячейка с «всего услуг»."""
    for r in range(sheet.nrows):
        vals = [normalize(v) for v in _cells(sheet, r)]
        has_fio = any("фио" in v for v in vals)
        has_total = any("всего услуг" in v for v in vals)
        if has_fio and has_total:
            return r
    return -1


def _build_colmap(sheet, hr):
    """Разметка колонок по строке заголовков hr.

    Возвращает (special, services): special={'num','fio','birth','sex','total'}->col,
    services=[(col, оригинальное_название)] — всё, что после «Всего услуг» и непусто.
    """
    special = {}
    headers = {}
    for c in range(sheet.ncols):
        raw = sheet.cell_value(hr, c)
        n = normalize(raw)
        headers[c] = (str(raw).strip(), n)
        if "total" not in special and "всего услуг" in n:
            special["total"] = c
        elif "fio" not in special and "фио" in n:
            special["fio"] = c
        elif "birth" not in special and ("дата рождения" in n or n == "дата рожд"):
            special["birth"] = c
        elif "sex" not in special and n == "пол":
            special["sex"] = c
        elif "num" not in special and ("п п" in n or n in ("n", "no", "номер")):
            special["num"] = c
    total_col = special.get("total", -1)
    services = []
    for c in range(sheet.ncols):
        if c in special.values():
            continue
        raw, n = headers[c]
        if not n:
            continue
        if total_col >= 0 and c <= total_col:
            continue          # до «Всего услуг» — это служебные колонки
        services.append((c, raw))
    return special, services


def parse_source(path):
    """Распарсить источник. Вернуть словарь с реквизитами, услугами и клиентами."""
    wb = xlrd.open_workbook(path)
    sheet = wb.sheet_by_index(0)
    rows_text = [" ".join(str(v) for v in _cells(sheet, r) if str(v).strip())
                 for r in range(min(sheet.nrows, 12))]

    hr = _find_header_row(sheet)
    if hr < 0:
        raise GosParseError("Не найдена строка заголовков (ожидались «ФИО» и «Всего услуг»).")
    special, services = _build_colmap(sheet, hr)
    if "fio" not in special:
        raise GosParseError("Не найдена колонка «ФИО гражданина».")

    fio_col = special["fio"]
    num_col = special.get("num")
    birth_col = special.get("birth")
    sex_col = special.get("sex")
    total_col = special.get("total")

    clients = []
    for r in range(hr + 1, sheet.nrows):
        fio = str(sheet.cell_value(r, fio_col)).strip()
        if not fio:
            if clients:
                break          # пустая строка после клиентов — таблица кончилась
            continue
        if normalize(fio).startswith(("итог", "всего", "подпис")):
            break
        # строка-получатель: №п/п число ИЛИ просто непустое ФИО-похожее
        num_ok = True
        if num_col is not None:
            num_ok = isinstance(sheet.cell_value(r, num_col), (int, float))
        if not num_ok and not re.search(r"[А-Яа-яЁё]{2,}", fio):
            continue
        counts = {}
        for c, name in services:
            counts[name] = _num(sheet.cell_value(r, c))
        clients.append(Client(
            fio=fio,
            birth=str(sheet.cell_value(r, birth_col)).strip() if birth_col is not None else "",
            sex=str(sheet.cell_value(r, sex_col)).strip() if sex_col is not None else "",
            total=_num(sheet.cell_value(r, total_col)) if total_col is not None else 0.0,
            counts=counts,
        ))

    period_str, start = _find_period(rows_text)
    month = year = None
    if start:
        try:
            _d, mm, yy = start.split(".")
            month, year = int(mm), int(yy)
        except ValueError:
            pass

    return {
        "worker": _find_worker(rows_text),
        "dept": _find_dept(rows_text),
        "period_str": period_str,
        "month": month,
        "year": year,
        "service_names": [name for _c, name in services],
        "clients": clients,
    }
