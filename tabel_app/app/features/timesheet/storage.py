"""Хранилище данных функции «Табель» поверх общей БД (app.db).

Отделения/сотрудники, реквизиты/подписи и производственный календарь теперь живут
в единой базе (core.db) — тот же источник, что и у «Приложения к табелю». Форма
данных, которую видит GUI, сохранена прежней (словари), поэтому окна функции не
меняются. Шаблон 0504421 по-прежнему берётся из ресурсов через core.storage.
"""

import os

from ...core import db as _db
from ...core import storage as _core

FEATURE = "timesheet"
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))


def load_departments():
    return _db.departments_load()


def save_departments(obj):
    _db.departments_save(obj)


def load_settings():
    return _db.settings_load()


def save_settings(obj):
    _db.settings_save(obj)


def load_calendar():
    return _db.calendar_load()


def save_calendar(obj):
    _db.calendar_save(obj)


def template_path():
    return _core.template_path(FEATURE, _PKG_DIR, "f0504421_template.xls")


def load_absences(dept, year, month):
    """Отсутствия по постоянным id сотрудников, независимо от нумерации строк."""
    import json
    _db.ensure_seeded()
    result = {}
    with _db.get_conn() as conn:
        for emp in dept.get("employees", []):
            key = f"timesheet_absence:{emp['_db_id']}:{year}:{month}"
            row = conn.execute("SELECT value FROM settings_kv WHERE key=?", (key,)).fetchone()
            if row:
                result[emp['n']] = json.loads(row['value'])
    return result


def save_absences(dept, year, month, absences):
    import json
    _db.ensure_seeded()
    with _db.get_conn() as conn:
        for emp in dept.get("employees", []):
            key = f"timesheet_absence:{emp['_db_id']}:{year}:{month}"
            conn.execute("INSERT INTO settings_kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (key, json.dumps(absences.get(emp['n'], []), ensure_ascii=False)))


def indicators_key(employee_id, year, month, period=None):
    span = 'month' if period is None else f'{period[0]}-{period[1]}'
    return f'timesheet_indicators:{employee_id}:{year}:{month}:{span}'


def load_indicators(emp, year, month, period=None):
    import json
    _db.ensure_seeded()
    conn = _db.get_conn()
    try:
        row = conn.execute('SELECT value FROM settings_kv WHERE key=?',
                           (indicators_key(emp['_db_id'], year, month, period),)).fetchone()
        return json.loads(row['value']) if row else {}
    finally:
        conn.close()


def save_indicators(emp, year, month, values, period=None):
    import json
    _db.ensure_seeded()
    conn = _db.get_conn()
    try:
        with conn:
            conn.execute('INSERT INTO settings_kv(key,value) VALUES(?,?) '
                         'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                         (indicators_key(emp['_db_id'], year, month, period),
                          json.dumps(values, ensure_ascii=False)))
    finally:
        conn.close()
