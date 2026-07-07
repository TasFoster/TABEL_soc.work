"""Контроллер «Проверки качества»: четверги месяца + разбор реестра -> .ods.

Соцработники, их обслуживаемые и адреса берутся из входного реестра .xls (тот же
формат, что и у функции «Реестр»): переиспользуем reestr.parser. Телефонов в реестре
нет — они хранятся отдельно (storage/БД) и подставляются в окне.
"""

import calendar
import datetime

from . import writer
from ..reestr import parser as reestr_parser

MONTHS_NOM = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
              "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

CHECK_WEEKDAY = 3  # четверг

DEFAULTS = {"dept_no": "9", "zav": "Шершнева Т.И."}


def month_num(name):
    """Номер месяца по названию (именительный падеж) или 0."""
    n = (name or "").strip().lower()
    for i, m in enumerate(MONTHS_NOM):
        if m and m.lower() == n:
            return i
    return 0


def month_thursdays(year, month):
    """Список всех четвергов месяца как datetime.date."""
    nd = calendar.monthrange(year, month)[1]
    return [datetime.date(year, month, d) for d in range(1, nd + 1)
            if datetime.date(year, month, d).weekday() == CHECK_WEEKDAY]


def format_date(d):
    """Дата в формате ДД.ММ.ГГ (напр. 17.07.25)."""
    return d.strftime("%d.%m.%y")


def split_workers(raw):
    """«Кошелева С.А., Смарунь Т.В.» -> ['Кошелева С.А.', 'Смарунь Т.В.'] (совместное
    обслуживание). Одиночное ФИО возвращается списком из одного элемента."""
    return [w.strip() for w in str(raw or "").split(",") if w.strip()]


def parse_workers_clients(path):
    """Разобрать реестр .xls в структуру для выбора.

    Возвращает {'order': [worker_fio, ...],
                'by_worker': {worker_fio: [(client_fio, address), ...]}}.
    ФИО клиента — без даты рождения (reestr.parser.split_fio уже отсекает её).
    При совместном обслуживании клиент попадает к каждому соцработнику из ячейки.
    Повторы клиента у одного соцработника убираются (порядок сохраняется).
    """
    reg = reestr_parser.parse_registry(path, "gos")
    order = []
    by = {}
    for rec in reg.records:
        client = (rec.fio or "").strip()
        if not client:
            continue
        address = (rec.address or "").strip()
        for w in split_workers(rec.worker):
            if w not in by:
                by[w] = []
                order.append(w)
            pair = (client, address)
            if pair not in by[w]:
                by[w].append(pair)
    return {"order": order, "by_worker": by}


def default_title(dept_no):
    return ("Проверка качества социального обслуживания заведующей отделением "
            f"социального обслуживания на дому №{dept_no}")


def default_sign(dept_no, zav):
    return f"Заведующий ОСОД № {dept_no} _________________ {zav}"


def _date_key(row):
    """Ключ сортировки строки по дате ДД.ММ.ГГ (нераспознанные — в конец)."""
    try:
        return datetime.datetime.strptime(row.get("date", ""), "%d.%m.%y").date()
    except ValueError:
        return datetime.date.max


def generate(out_path, ctx, rows):
    """Отсортировать строки по дате и записать .ods."""
    ordered = sorted(rows, key=_date_key)
    return writer.generate(out_path, ctx, ordered)
