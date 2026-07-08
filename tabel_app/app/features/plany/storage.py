"""Хранилище функции «Планы».

Шаблоны планов (задачи по месяцам для отд.5 и отд.9) — прикладной ресурс
(data/plany_templates.json), только для чтения; получены из исходных .doc один раз
(см. tools/parse_plany_doc.py). Выбранный соцработник «Заслушивания» запоминается
в общей БД по (отделение, год, месяц) — таблица plany_workers.
"""

import json
import os

from ...core import db as _db
from ...core import storage as _core

FEATURE = "plany"
_PKG = os.path.dirname(os.path.abspath(__file__))
_templates = None


def load_templates():
    """Прочитать (и закэшировать) JSON-шаблоны планов. Только для чтения."""
    global _templates
    if _templates is None:
        path = os.path.join(_core.feature_resource_dir(FEATURE, _PKG),
                            "data", "plany_templates.json")
        with open(path, "r", encoding="utf-8") as f:
            _templates = json.load(f)
    return _templates


def departments():
    """Список номеров отделений, для которых есть шаблоны (отсортирован)."""
    return sorted(load_templates()["departments"].keys(), key=lambda x: int(x))


def baseline_year():
    return int(load_templates().get("baseline_year", 2026))


def month_template(dept, month):
    """Шаблон месяца: dict с header/footer/sections/sign_* /col_widths."""
    return load_templates()["departments"][str(dept)]["months"][str(int(month))]


def default_worker(dept, month):
    """Соцработник «Заслушивания» из шаблона (значение по умолчанию)."""
    return month_template(dept, month).get("sign_worker", "")


# ------- запомненный соцработник по (отд, год, месяц) --------------------------
def worker_load(dept, year, month):
    return _db.plany_worker_load(dept, year, month)


def worker_save(dept, year, month, worker):
    _db.plany_worker_save(dept, year, month, worker)


def workers_all(dept, year):
    return _db.plany_workers_load_all(dept, year)
