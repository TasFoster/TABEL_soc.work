"""Контроллер функции «Услуги-Деньги»: входы -> агрегаты -> заполнение шаблона."""

import json
import os

from . import parser, storage
from .writer import generate as _generate

MONTHS = ["", "январь", "февраль", "март", "апрель", "май", "июнь",
          "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
MONTHS_PREP = ["", "январе", "феврале", "марте", "апреле", "мае", "июне",
               "июле", "августе", "сентябре", "октябре", "ноябре", "декабре"]


def prepare(path_071, path_benefit, prev_path=None):
    """Прочитать 071 и xlsx льготников, собрать данные для отчёта.

    prev_path — предыдущий отчёт «Услуги-Деньги» (.xlsx/.xls). Если задан, его H/I/J
    берутся за основу: новые H/I/J = предыдущие + текущие (накопительный отчёт за год).
    """
    data = parser.read_benefit(path_benefit)
    data["counts071"] = parser.read_071(path_071)
    data["prev_ud"] = (parser.read_prev_ud(prev_path)
                       if prev_path and os.path.exists(prev_path) else {})
    return data


def find_prev_report(month, year):
    """Найти отчёт «Услуги-Деньги» за ПРЕДЫДУЩИЙ месяц того же года в архиве документов.

    Возвращает путь к временной копии файла или None. В январе (month<=1) предыдущего
    месяца в этом году нет — возвращает None (накопление начинается заново)."""
    try:
        month = int(month)
        year = int(year)
    except (TypeError, ValueError):
        return None
    if month <= 1:
        return None
    from ...core import documents
    pm = month - 1
    for d in documents.list_documents():
        if d.get("feature") != "uslugi_dengi":
            continue
        try:
            p = json.loads(d.get("params") or "{}")
        except (ValueError, TypeError):
            p = {}
        if int(p.get("month") or 0) == pm and int(p.get("year") or 0) == year:
            return documents.extract_to_temp(d["id"])
    return None


def period_text(month, year, dept="9"):
    m = MONTHS[month] if 0 < month < len(MONTHS) else ""
    return f"За {m} {year} года в отделении №{dept}"


def generate(data, out_path, month=None, year=None, dept="9"):
    pt = period_text(month, year, dept) if (month and year) else None
    return _generate(storage.template_path(), out_path, data, pt)
