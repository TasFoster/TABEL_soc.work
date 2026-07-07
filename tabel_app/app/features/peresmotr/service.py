"""Контроллер «Пересмотра»: из отчёта ИПСУ находит получателей, у которых
заканчивается срок обслуживания в заданном месяце/году.

Срок берётся из колонки «Срок предоставления услуги» (диапазон «дд.мм.гггг -
дд.мм.гггг»); окончанием считается ПОСЛЕДНЯЯ дата диапазона. Строки выводятся как
есть (без объединения дублей одного человека). Разбор ИПСУ переиспользуется из
функции «Реестр» (reestr.parser.parse_ipsu).
"""

import datetime
import re

from . import writer
from ..reestr import parser as reestr_parser

MONTHS_NOM = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
              "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

# Предложный падеж («в … 2027 г.») для заголовка
MONTHS_PREP = ["", "январе", "феврале", "марте", "апреле", "мае", "июне",
               "июле", "августе", "сентябре", "октябре", "ноябре", "декабре"]

_DATE_RE = re.compile(r"\d{2}\.\d{2}\.\d{4}")


def month_num(name):
    n = (name or "").strip().lower()
    for i, m in enumerate(MONTHS_NOM):
        if m and m.lower() == n:
            return i
    return 0


def end_date(srok):
    """Дата окончания срока = последняя дата в строке «Срок предоставления услуги».
    Возвращает datetime.date или None."""
    dates = _DATE_RE.findall(srok or "")
    if not dates:
        return None
    try:
        return datetime.datetime.strptime(dates[-1], "%d.%m.%Y").date()
    except ValueError:
        return None


def find_expiring(path, year, month):
    """Список получателей, чей срок обслуживания заканчивается в year/month.

    Возвращает список dict {fio, end} (end — строка дд.мм.гггг). Все подходящие
    строки ИПСУ как есть, порядок исходный.
    """
    records = reestr_parser.parse_ipsu(path)
    out = []
    for r in records:
        ed = end_date(r.srok)
        if ed and ed.year == year and ed.month == month:
            out.append({"fio": (r.fio or "").strip(),
                        "end": ed.strftime("%d.%m.%Y")})
    return out


def default_title(year, month):
    mn = MONTHS_PREP[month] if 1 <= month <= 12 else ""
    return ("Список получателей с окончанием срока обслуживания "
            f"в {mn} {year} г.")


def generate(out_path, ctx, rows):
    return writer.generate(out_path, ctx, rows)
