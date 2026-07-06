"""Хранилище данных функции «Реестр» поверх общей БД (app.db).

Клиенты, их группы (соцработники) и данные прошлого месяца теперь хранятся в единой
базе (core.db). Реквизиты шапки (адресат/директор/№ отделения) остаются статическим
JSON-конфигом — в программе они не редактируются. Форма словарей сохранена прежней,
поэтому service.py/gui.py не меняются.
"""

import os

from ...core import db as _db
from ...core import storage as _core

FEATURE = "reestr"
_PKG = os.path.dirname(os.path.abspath(__file__))


def load_settings():
    return _core.load_json(FEATURE, _PKG, "settings.json")


def save_settings(obj):
    _core.save_json(FEATURE, "settings.json", obj)


def template_path():
    return _core.template_path(FEATURE, _PKG, "reestr_template.ods")


def load_worker_map():
    """Привязка клиент(ФИО)→соцработник + порядок работников (из общей БД)."""
    return _db.reestr_map_load()


def save_worker_map(obj):
    _db.reestr_map_save(obj)


def load_prev():
    """Данные прошлого месяца (договоры и доп-клиенты) для пометок новый/пересмотр."""
    return _db.reestr_kv_load("prev_month", {"contracts": {}, "dop_ids": []})


def save_prev(obj):
    _db.reestr_kv_save("prev_month", obj)


def load_prev_journal():
    """Журнал договоров прошлого месяца (по ФИО) для сравнения новый/пересмотр/снят."""
    return _db.reestr_kv_load("prev_journal", {})


def save_prev_journal(obj):
    _db.reestr_kv_save("prev_journal", obj)
