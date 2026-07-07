"""Хранилище функции «Проверка качества» поверх общей БД (app.db).

В реестре телефонов клиентов нет. Их вводят вручную в окне, а тут они
запоминаются по ФИО клиента, чтобы подставляться в следующий раз. Всё остальное
(соцработники, клиенты, адреса) берётся из входного реестра .xls на лету.
"""

from ...core import db as _db

FEATURE = "proverka_kachestva"


def load_phone(client_fio):
    """Сохранённый телефон клиента (или '' если нет)."""
    return _db.pk_phone_load(client_fio)


def save_phone(client_fio, phone):
    """Запомнить телефон клиента (upsert по ФИО)."""
    _db.pk_phone_save(client_fio, phone)


def load_all_phones():
    """Все сохранённые телефоны как {ФИО: телефон}."""
    return _db.pk_phones_load_all()
