"""Хранилище «Протокола»: отделения/соцработники из общей базы + план методчаса.

Присутствующие берутся из тех же employees, что и в «Графике проверок» (единый источник
истины — core.db). План методического часа (темы по месяцам) — JSON-справочник функции
(`data/plan.json`), сидится из дефолта и правится пользователем."""

import os

from ...core import db as _db
from ...core import storage as _core

FEATURE = "protokol"
_PKG = os.path.dirname(os.path.abspath(__file__))


def list_departments():
    _db.ensure_seeded()
    with _db.get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM departments ORDER BY sort_order, id")]


def soc_workers(dept_id):
    """ФИО соцработников отделения (по должности) — кандидаты в «Присутствовали»."""
    _db.ensure_seeded()
    with _db.get_conn() as conn:
        rows = conn.execute(
            "SELECT fio, position FROM employees WHERE dept_id=? ORDER BY sort_order, n, id",
            (dept_id,)).fetchall()
    return [r["fio"] for r in rows if "работник" in (r["position"] or "").lower()]


def load_plan():
    """План методчаса: {номер_месяца(str): тема}. Сид из data/plan.json, правится пользователем."""
    try:
        return _core.load_json(FEATURE, _PKG, "plan.json")
    except Exception:  # noqa: BLE001
        return {}


def save_plan(obj):
    _core.save_json(FEATURE, "plan.json", obj)


def load_calendar():
    """Производственный календарь (БД) — для расчёта последней рабочей среды месяца."""
    from ..timesheet.calendar_ru import ProductionCalendar
    return ProductionCalendar(_db.calendar_load(), 8, 7)
