"""Контроллер функции «Проезд»: поездки из файла + билеты со скана -> .ods.

Слой Controller (MVC): оркестрация сценария, без виджетов Tkinter.
  * prepare()     — прочитать поездки и (best-effort) распознать билеты со скана;
  * build_rows()  — собрать строки таблицы: даты по рабочим дням выбранного месяца
                    (среда — выходной, кроме переноса), привязка билетов 1-й->1-й,
                    нормализация серии к известной, цена по серии;
  * generate()    — записать .ods из (возможно отредактированных) строк таблицы.
"""

import calendar as _cal
import datetime
import re

from . import parser, storage
from .ods_writer import generate as _ods_generate

# Поездки совершаются по рабочим дням, КРОМЕ среды (методический день). Среда
# становится рабочей только по переносу — если она помечена как перенесённый
# рабочий день в производственном календаре (work_days). См. travel_days().
_WED = 2  # понедельник=0 … среда=2 (datetime.weekday)

# Колонки строки таблицы (логическая модель одной поездки).
ROW_KEYS = ("num", "date", "frm", "to", "purpose", "number", "series", "price")


# ----------------------------------------------------------------- подготовка
def prepare(trips_path, scan_path=None):
    """Прочитать поездки из файла и (best-effort) распознать билеты со скана.

    Даты здесь НЕ проставляются — их выставляет build_rows() по выбранному месяцу."""
    trips, header = parser.read_trips(trips_path)
    tickets = parser.ocr_tickets(scan_path) if scan_path else []
    return {"trips": trips, "header": header, "tickets": tickets,
            "ocr_available": parser.ocr_available()}


# ------------------------------------------------------------- рабочие дни/даты
def _parse_date(s):
    s = (s or "").strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _wed_is_working(d, cal):
    """Среда d рабочая, если на её НЕДЕЛЕ выпал рабочий день — т.е. один из пн/вт/чт/пт
    нерабочий (праздник/перенос). Тогда среда его компенсирует."""
    monday = d - datetime.timedelta(days=d.weekday())
    for off in (0, 1, 3, 4):  # пн, вт, чт, пт
        if not cal.is_workday(monday + datetime.timedelta(days=off)):
            return True
    return False


def travel_days(year, month, cal):
    """Список дат-поездок месяца.

    Рабочие дни поездок — пн/вт/чт/пт (не праздник). СРЕДА — методический (выходной)
    день, КРОМЕ случая, когда на её неделе выпал рабочий день (один из пн/вт/чт/пт стал
    нерабочим из-за праздника) — тогда среда становится рабочей и компенсирует его.
    Явно помеченные перенесённые рабочие дни (cal.is_extra_workday, напр. рабочая
    суббота) включаются всегда."""
    days = []
    nd = _cal.monthrange(year, month)[1]
    for dd in range(1, nd + 1):
        d = datetime.date(year, month, dd)
        if cal.is_extra_workday(d):        # явный перенос — рабочий всегда
            days.append(d)
            continue
        if not cal.is_workday(d):           # праздник или сб/вс
            continue
        if d.weekday() == _WED and not _wed_is_working(d, cal):
            continue                        # среда — выходной, если ничего не выпало
        days.append(d)
    return days


def _day_groups(items):
    """Разбить строки на дни ПО СТРУКТУРЕ отчёта: один день = 2 основные поездки +
    прилегающие к ним допы (помечены голубым → item['dop']=True). Считаем основные
    (не-доп) строки: каждые 2 основные с относящимися к ним допами = одна группа-день.
    Возвращает список групп — списков индексов строк."""
    groups, cur, mains = [], [], 0
    for i, it in enumerate(items):
        if it.get("dop"):
            cur.append(i)            # доп прилегает к текущему дню
            continue
        if mains >= 2:               # уже 2 основные — начинается новый день
            groups.append(cur)
            cur, mains = [], 0
        cur.append(i)
        mains += 1
    if cur:
        groups.append(cur)
    return groups


def assign_dates(trips, year, month, cal, date_fmt="%d.%m.%Y"):
    """Проставить датам рабочие дни месяца ПО СТРУКТУРЕ (с нуля, не глядя на текущие
    даты): группа-день (2 основные + допы) i -> i-й рабочий день месяца (среда —
    выходной с компенсацией, см. travel_days). Возвращает (trips_new, note)."""
    tdays = travel_days(year, month, cal)
    groups = _day_groups(trips)
    new = [dict(t) for t in trips]
    for gi, group in enumerate(groups):
        if gi >= len(tdays):
            break
        ds = tdays[gi].strftime(date_fmt)
        for idx in group:
            new[idx]["date"] = ds
    ng, nd = len(groups), len(tdays)
    if ng == nd:
        note = f"Даты проставлены: {ng} дн. (2 поездки + допы на день; среда — выходной)."
    elif ng > nd:
        note = (f"⚠ Дней по структуре отчёта {ng}, а рабочих дней по календарю {nd}. "
                f"Проставлены первые {nd}; остальные {ng - nd} без даты — проверьте отчёт/месяц.")
    else:
        note = (f"Проставлено {ng} дн. (рабочих дней по календарю {nd}). Если дней должно "
                f"быть больше — проверьте отчёт/месяц.")
    return new, note


# ------------------------------------------------------------------- серии/цена
def _lev(a, b):
    """Расстояние Левенштейна (для привязки распознанной серии к известной)."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def normalize_series(raw, settings=None):
    """Привести распознанную серию к известной (settings.known_series).

    OCR обычного шрифта надёжно читает ЦИФРОВОЙ хвост (напр. 571/575/996), но
    путает буквы префикса (4МН -> ИН/АМН/Н). Поэтому привязываем по совпадению
    хвоста, а при неоднозначности — по близости к известной серии. Если хвост ни
    с чем не совпал — возвращаем нормализованную распознанную серию (для правки)."""
    settings = settings or storage.load_settings()
    known = [str(k).upper().replace(" ", "") for k in settings.get("known_series", [])]
    s = parser._norm_series(raw or "")
    if not s:
        return ""
    if s in known:
        return s
    m = re.search(r"(\d{3})\D*$", s)
    tail = m.group(1) if m else ""
    cands = [k for k in known if k.endswith(tail)] if tail else []
    if len(cands) == 1:
        return cands[0]
    if len(cands) > 1:
        return min(cands, key=lambda k: _lev(s, k))
    return s


def default_price_for(series, settings=None):
    """Цена по префиксу серии (4МН->35, ВА->43), иначе default_price."""
    settings = settings or storage.load_settings()
    series = (series or "").strip().upper()
    for prefix, val in settings.get("series_prices", {}).items():
        if series.startswith(prefix.upper()):
            return val
    return settings.get("default_price", 35)


# ----------------------------------------------------------------- строки таблицы
def build_rows(prepared, year, month, settings=None):
    """Собрать строки таблицы для отображения/правки и (затем) формирования.

    Возвращает (rows, note). rows — список dict с ключами ROW_KEYS. Билеты
    привязываются по порядку 1-й->1-я поездка; серия нормализуется к известной,
    цена считается по серии. Даты проставляются по рабочим дням месяца."""
    settings = settings or storage.load_settings()
    trips, note = assign_dates(prepared["trips"], year, month, storage.load_calendar())
    ocr = prepared.get("tickets", [])
    rows = []
    for i, trip in enumerate(trips):
        num, ser_raw = ocr[i] if i < len(ocr) else ("", "")
        series = normalize_series(ser_raw, settings)
        rows.append({
            "num": i + 1,
            "date": trip.get("date", ""),
            "frm": trip.get("frm", ""),
            "to": trip.get("to", ""),
            "purpose": trip.get("purpose", ""),
            "number": (num or "").strip(),
            "series": series,
            "price": default_price_for(series, settings),
            "dop": bool(trip.get("dop")),
        })
    return rows, note


def reassign_dates(rows, year, month):
    """Пересчитать только даты у текущих (возможно отредактированных) строк по
    выбранному месяцу, сохраняя остальные колонки. Возвращает (rows, note)."""
    return assign_dates(rows, year, month, storage.load_calendar())


# ----------------------------------------------------------------- лексикон подсказок
def build_lexicon(rows, settings=None):
    """Словарь подсказок по колонкам: накопленная история + текущая таблица + ФИО из
    общей базы (Реестр). Возвращает {place, purpose, series, number} (списки)."""
    settings = settings or storage.load_settings()
    hist = storage.load_lexicon()
    place = set(hist.get("place", []))
    purpose = set(hist.get("purpose", []))
    series = set(hist.get("series", []))
    number = set(hist.get("number", []))
    for r in rows or []:
        for k in ("frm", "to"):
            v = str(r.get(k, "")).strip()
            if v:
                place.add(v)
        if str(r.get("purpose", "")).strip():
            purpose.add(str(r["purpose"]).strip())
        if str(r.get("series", "")).strip():
            series.add(str(r["series"]).strip())
        if str(r.get("number", "")).strip():
            number.add(str(r["number"]).strip())
    for f in storage.reestr_fio():
        if f and f.strip():
            place.add(f.strip())
    for s in settings.get("known_series", []):
        series.add(str(s))
    return {"place": sorted(place), "purpose": sorted(purpose),
            "series": sorted(series), "number": sorted(number)}


def update_lexicon(rows):
    """Пополнить историю подсказок значениями из rows (при формировании отчёта)."""
    hist = storage.load_lexicon()

    def merge(key, vals):
        cur = set(hist.get(key, []))
        cur |= {v for v in vals if v}
        hist[key] = sorted(cur)

    merge("place", [str(r.get("frm", "")).strip() for r in rows]
          + [str(r.get("to", "")).strip() for r in rows])
    merge("purpose", [str(r.get("purpose", "")).strip() for r in rows])
    merge("series", [str(r.get("series", "")).strip() for r in rows])
    merge("number", [str(r.get("number", "")).strip() for r in rows])
    storage.save_lexicon(hist)


# ------------------------------------------------------------------- контекст/вывод
def _month_index(month_upper, settings):
    mu = (month_upper or "").strip().upper()
    lst = [m.upper() for m in settings.get("months_upper", [])]
    return lst.index(mu) if mu in lst else 0


def _appl_date(midx, year):
    try:
        y = int(year)
    except (TypeError, ValueError):
        return ""
    nm = midx + 1
    if nm > 12:
        nm, y = 1, y + 1
    return f"01.{nm:02d}.{y % 100:02d}"


def build_ctx(header, year, month, overrides=None):
    """Контекст заявления/отчёта. month — номер 1..12 (выбран в окне)."""
    overrides = overrides or {}
    s = storage.load_settings()
    worker_full = (overrides.get("worker_full") or header.get("worker_full", "")).strip()
    forms = storage.forms_for(worker_full)
    mu = s.get("months_upper", [])
    mp = s.get("months_prep", [])
    month_upper = mu[month] if 0 < month < len(mu) else header.get("month_upper", "")
    month_prep = mp[month] if 0 < month < len(mp) else ""
    return {
        "worker_full": worker_full,
        "position_line": (overrides.get("position_line") or header.get("position_line")
                          or s.get("position_line", "")),
        "month_upper": month_upper, "year": str(year), "month_prep": month_prep,
        "worker_genitive": overrides.get("worker_genitive") or forms["genitive"],
        "worker_short": overrides.get("worker_short") or forms["short"],
        "zav": overrides.get("zav") or s.get("zav", ""),
        "director_dative": overrides.get("director_dative") or s.get("director_dative", ""),
        "dept_no": overrides.get("dept_no") or s.get("dept_no", ""),
        "appl_date": overrides.get("appl_date") or _appl_date(month, year),
    }


def generate(rows, header, year, month, out_path, overrides=None):
    """Сформировать .ods из строк таблицы (уже отредактированных пользователем).

    rows — список dict с ключами ROW_KEYS; сумма = Σ price."""
    ctx = build_ctx(header, year, month, overrides)
    out = _ods_generate(storage.template_path(), out_path, ctx, rows)
    try:
        update_lexicon(rows)   # пополнить словарь подсказок (не критично при ошибке)
    except Exception:  # noqa: BLE001
        pass
    return out
