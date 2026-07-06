"""Хранилище функции «Отчёт по госзаданию» поверх общего core.storage.

Справочник услуг (services_seed.json) — редактируемый JSON: на первом запуске
копируется из ресурсов в data/gos_zadanie/, дальше правится пользователем.
"""

import os

from ...core import db as _db
from ...core import storage as _core

FEATURE = "gos_zadanie"
_PKG = os.path.dirname(os.path.abspath(__file__))


def soc_worker_fios():
    """Полные ФИО соцработников из общей базы (для подстановки в отчёт)."""
    try:
        return _db.employee_worker_fios()
    except Exception:  # noqa: BLE001
        return []


def load_services():
    """Список услуг справочника: [{'name','category','order'}]."""
    data = _core.load_json(FEATURE, _PKG, "services_seed.json")
    return data.get("services", [])


def save_services(services):
    _core.save_json(FEATURE, "services_seed.json", {"services": services})
