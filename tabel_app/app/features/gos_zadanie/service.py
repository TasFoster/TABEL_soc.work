"""Контроллер «Отчёта по госзаданию»: источник -> разбор -> категоризация -> .ods."""

import calendar
import re

from . import parser, storage
from .model import DOP, MAIN, ServiceCatalog
from .writer import generate as _write

MONTHS = ["", "январь", "февраль", "март", "апрель", "май", "июнь",
          "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]

DEFAULT_ZAV = "Шершнева Т.И."


def prepare(source_path):
    """Распарсить источник и разнести услуги по категориям через справочник.

    Неизвестные услуги дописываются в справочник как «дополнительные»
    (пользователь может переклассифицировать). Возвращает данные для записи."""
    data = parser.parse_source(source_path)
    cat = ServiceCatalog(storage.load_services())

    main_services, dop_services, new_services = [], [], []
    changed = False
    for name in data["service_names"]:
        c = cat.category_of(name)
        if c is None:
            cat.add(name, DOP)
            c = DOP
            changed = True
            new_services.append(name)
        if c == MAIN:
            main_services.append(name)
        elif c == DOP:
            dop_services.append(name)
        # skip — не выводим
    if changed:
        try:
            storage.save_services(cat.to_list())
        except Exception:  # noqa: BLE001 — справочник не должен ломать формирование
            pass

    main_services.sort(key=cat.order_of)
    dop_services.sort(key=cat.order_of)
    data["main_services"] = main_services
    data["dop_services"] = dop_services
    data["new_services"] = new_services
    return data


def format_sign(name):
    """ФИО -> «И.О.Фамилия» для подписи. Принимает «Фамилия Имя Отчество» и «Фамилия И.О.»."""
    s = (name or "").strip()
    if not s:
        return ""
    parts = s.split()
    if len(parts) >= 3 and all(len(p) > 2 for p in parts[1:3]):
        return f"{parts[1][0]}.{parts[2][0]}.{parts[0]}"
    m = re.match(r"([А-ЯЁA-Z][а-яёa-z\-]+)\s+([А-ЯЁA-Z])\.?\s*([А-ЯЁA-Z])\.?", s)
    if m:
        return f"{m.group(2)}.{m.group(3)}.{m.group(1)}"
    return s


def generate(prepared, out_path, worker=None, dept=None, month=None, year=None, zav=None):
    """Сформировать отчёт. Реквизиты можно переопределить (из окна), иначе — из источника."""
    m = month or prepared.get("month") or 0
    y = year or prepared.get("year") or ""
    period = prepared.get("period_str") or ""
    if m and y:                       # период за выбранный месяц (1-е … последнее число)
        try:
            last = calendar.monthrange(int(y), int(m))[1]
            period = f"01.{int(m):02d}.{int(y)}-{last:02d}.{int(m):02d}.{int(y)}"
        except (ValueError, TypeError):
            pass
    ctx = {
        "worker": (worker or prepared.get("worker") or "").strip(),
        "worker_sign": format_sign(worker or prepared.get("worker") or ""),
        "dept": (dept or prepared.get("dept") or "").strip(),
        "month_name": MONTHS[m] if 0 < m < len(MONTHS) else "",
        "year": y,
        "period_str": period,
        "zav": (zav or DEFAULT_ZAV).strip(),
        "zav_sign": format_sign(zav or DEFAULT_ZAV),
    }
    _write(out_path, ctx, prepared["clients"],
           prepared["main_services"], prepared["dop_services"])
    return out_path
