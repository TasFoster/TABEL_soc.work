"""Чтение «Отчёта по количеству заключённых договоров» (журнала) — .xls через xlrd.

Журнал — плоский список договоров за месяц (и гос, и доп вместе): ФИО получателя,
тип договора, № договора, период действия, кол-во/сумма за месяц. Используется для
надёжного определения отметок «новый»/«пересмотр»/«снят» сравнением с прошлым месяцем
ПО ФИО (в самом реестре клиенты тоже сопоставляются по ФИО, а не по номеру строки).
"""

import re

import xlrd

from .parser import extract_contract, split_fio

_NORM_RE = re.compile(r"[^а-яёa-z0-9 ]")


def norm_fio(full):
    """ФИО -> канон для сравнения (без даты рождения, нижний регистр, без пунктуации)."""
    fio, _birth = split_fio(full)
    s = fio.lower().replace("ё", "е")
    return re.sub(r"\s+", " ", _NORM_RE.sub(" ", s)).strip()


def _kind(type_str):
    """Тип договора -> 'dop' (дополнительные услуги) | 'gos' (социальные услуги)."""
    t = (type_str or "").lower().replace("ё", "е")
    return "dop" if "дополнительных социальных услуг" in t else "gos"


def _s(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else str(v)
    return str(v).strip()


def _find_header(sheet):
    for r in range(min(sheet.nrows, 15)):
        joined = " ".join(_s(sheet.cell(r, c).value) for c in range(sheet.ncols)).lower()
        if "фио получател" in joined and "тип договора" in joined:
            return r
    return -1


def _colmap(sheet, hr):
    cm = {}
    for c in range(sheet.ncols):
        t = _s(sheet.cell(hr, c).value).lower()
        if not t:
            continue
        if "фио" in t and "fio" not in cm:
            cm["fio"] = c
        elif "тип договора" in t:
            cm["type"] = c
        elif "договора" in t and ("№" in t or "номер" in t) and "тип" not in t:
            cm["number"] = c
        elif "сумма" in t and "отчетн" in t:
            cm["sum_month"] = c
    return cm


def parse_journal(path):
    """Вернуть {'period':(start,end), 'by_fio': {norm_fio: {'gos':set(№), 'dop':set(№),
    'fio': исходное ФИО}}}."""
    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_index(0)

    period = ("", "")
    for r in range(min(sheet.nrows, 12)):
        for c in range(sheet.ncols):
            m = re.search(r"с\s*(\d{2}\.\d{2}\.\d{4})\s*по\s*(\d{2}\.\d{2}\.\d{4})",
                          _s(sheet.cell(r, c).value))
            if m:
                period = (m.group(1), m.group(2))
                break
        if period[0]:
            break

    hr = _find_header(sheet)
    if hr < 0:
        return {"period": period, "by_fio": {}}
    cm = _colmap(sheet, hr)
    c_fio = cm.get("fio", 3)
    c_type = cm.get("type")
    c_num = cm.get("number")

    by_fio = {}
    for r in range(hr + 1, sheet.nrows):
        full = _s(sheet.cell(r, c_fio).value) if c_fio is not None else ""
        if not full or not re.search(r"[А-Яа-яЁё]{2,}", full):
            continue
        key = norm_fio(full)
        if not key:
            continue
        kind = _kind(_s(sheet.cell(r, c_type).value)) if c_type is not None else "gos"
        number = extract_contract(_s(sheet.cell(r, c_num).value)) if c_num is not None else ""
        rec = by_fio.setdefault(key, {"gos": set(), "dop": set(), "fio": split_fio(full)[0]})
        if number:
            rec[kind].add(number)
    return {"period": period, "by_fio": by_fio}


def diff_marks(cur_by_fio, prev_by_fio):
    """Сравнить текущий журнал с прошлым (по ФИО). Вернуть (new_fios, peresmotr_fios, snyat).

    new_fios — у клиента появился доп-договор (или клиент новый и есть доп);
    peresmotr_fios — у существующего клиента сменился номер гос-договора;
    snyat — клиенты прошлого месяца, которых нет в текущем (информационно).
    """
    new_fios, peresmotr_fios = set(), set()
    prev_by_fio = prev_by_fio or {}
    if not prev_by_fio:
        return new_fios, peresmotr_fios, set()   # первый журнал — сравнивать не с чем
    for fio, cur in cur_by_fio.items():
        prev = prev_by_fio.get(fio)
        if prev is None:
            if cur.get("dop"):
                new_fios.add(fio)
            continue
        if set(cur.get("dop", ())) - set(prev.get("dop", ())):
            new_fios.add(fio)
        if set(cur.get("gos", ())) - set(prev.get("gos", ())):
            peresmotr_fios.add(fio)
    snyat = set(prev_by_fio) - set(cur_by_fio)
    return new_fios, peresmotr_fios, snyat


def to_storable(by_fio):
    """{norm_fio:{gos:set,dop:set,fio}} -> JSON-сериализуемый вид для сохранения."""
    return {k: {"gos": sorted(v["gos"]), "dop": sorted(v["dop"]), "fio": v.get("fio", "")}
            for k, v in by_fio.items()}
