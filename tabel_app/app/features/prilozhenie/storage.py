"""Хранилище функции «Приложение к табелю» поверх общей БД (app.db).

Даёт остальному коду функции простой доступ: отделения, сотрудники с их
постоянной нагрузкой (model.Worker), а также помесячные периоды, отсутствия
и перераспределения. Реквизиты/настройки берутся из общей таблицы settings_kv.
"""

import json
import os

from ...core import db as _db
from ...core import storage as _core
from .model import Absence, Period, Redistribution, Worker

FEATURE = "prilozhenie"
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))


def ensure_ready():
    _db.ensure_seeded()


# --------------------------------------------------------------- отделения
def list_departments():
    with _db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM departments ORDER BY sort_order, id"
        ).fetchall()
        return [dict(r) for r in rows]


def get_department(dept_id):
    with _db.get_conn() as conn:
        r = conn.execute("SELECT * FROM departments WHERE id=?", (dept_id,)).fetchone()
        return dict(r) if r else None


# --------------------------------------------------------------- сотрудники
def get_workers(dept_id, only_active=True):
    """Список model.Worker отделения с постоянной нагрузкой и нормой."""
    with _db.get_conn() as conn:
        rows = conn.execute(
            "SELECT e.id, e.n, e.fio, e.oklad, "
            "       COALESCE(l.load_gor,0)   AS load_gor, "
            "       COALESCE(l.load_chast,0) AS load_chast, "
            "       COALESCE(l.norma_gor,10) AS norma_gor, "
            "       COALESCE(l.norma_chast,8) AS norma_chast, "
            "       COALESCE(l.active,1)     AS active "
            "FROM employees e "
            "LEFT JOIN pril_load_default l ON l.employee_id = e.id "
            "WHERE e.dept_id=? ORDER BY e.sort_order, e.n, e.id",
            (dept_id,),
        ).fetchall()
    workers = []
    for r in rows:
        if only_active and not r["active"]:
            continue
        workers.append(Worker(
            employee_id=r["id"], n=r["n"], fio=r["fio"], oklad=r["oklad"] or 0,
            load_gor=r["load_gor"], load_chast=r["load_chast"],
            norma_gor=r["norma_gor"], norma_chast=r["norma_chast"],
            active=bool(r["active"]),
        ))
    # пронумеровать активных подряд (как в приложении)
    for i, w in enumerate(workers, 1):
        w.n = i
    return workers


def save_worker_load(employee_id, load_gor, load_chast, norma_gor, norma_chast, active):
    with _db.get_conn() as conn:
        conn.execute(
            "INSERT INTO pril_load_default(employee_id,load_gor,load_chast,"
            "norma_gor,norma_chast,active) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(employee_id) DO UPDATE SET "
            "load_gor=excluded.load_gor, load_chast=excluded.load_chast, "
            "norma_gor=excluded.norma_gor, norma_chast=excluded.norma_chast, "
            "active=excluded.active",
            (employee_id, load_gor, load_chast, norma_gor, norma_chast, int(bool(active))),
        )
        conn.commit()


# --------------------------------------------------------------- периоды
def get_periods(dept_id, year, month):
    with _db.get_conn() as conn:
        rows = conn.execute(
            "SELECT p.* FROM pril_period p JOIN employees e ON e.id=p.employee_id "
            "WHERE e.dept_id=? AND p.year=? AND p.month=?",
            (dept_id, year, month),
        ).fetchall()
        return [Period(r["employee_id"], r["sector"], r["day_from"], r["day_to"],
                       r["value"]) for r in rows]


def save_periods(dept_id, year, month, periods):
    """Заменить все периоды отделения за месяц."""
    with _db.get_conn() as conn:
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM employees WHERE dept_id=?", (dept_id,)).fetchall()]
        if ids:
            qmarks = ",".join("?" * len(ids))
            conn.execute(
                f"DELETE FROM pril_period WHERE year=? AND month=? "
                f"AND employee_id IN ({qmarks})",
                (year, month, *ids),
            )
        for p in periods:
            conn.execute(
                "INSERT INTO pril_period(employee_id,year,month,sector,day_from,"
                "day_to,value) VALUES(?,?,?,?,?,?,?)",
                (p.employee_id, year, month, p.sector, p.day_from, p.day_to, p.value),
            )
        conn.commit()


# --------------------------------------------------------------- отсутствия
def get_absences(dept_id, year, month):
    with _db.get_conn() as conn:
        rows = conn.execute(
            "SELECT a.* FROM pril_absence a JOIN employees e ON e.id=a.employee_id "
            "WHERE e.dept_id=? AND a.year=? AND a.month=?",
            (dept_id, year, month),
        ).fetchall()
        return [Absence(r["employee_id"], r["day_from"], r["day_to"], r["code"] or "")
                for r in rows]


def save_absences(dept_id, year, month, absences):
    with _db.get_conn() as conn:
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM employees WHERE dept_id=?", (dept_id,)).fetchall()]
        if ids:
            qmarks = ",".join("?" * len(ids))
            conn.execute(
                f"DELETE FROM pril_absence WHERE year=? AND month=? "
                f"AND employee_id IN ({qmarks})",
                (year, month, *ids),
            )
        for a in absences:
            conn.execute(
                "INSERT INTO pril_absence(employee_id,year,month,day_from,day_to,code)"
                " VALUES(?,?,?,?,?,?)",
                (a.employee_id, year, month, a.day_from, a.day_to, a.code),
            )
        conn.commit()


# ----------------------------------------------------------- перераспределение
def get_redistributions(dept_id, year, month):
    with _db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM pril_redistribution WHERE year=? AND month=? "
            "AND (from_employee_id IN (SELECT id FROM employees WHERE dept_id=?) "
            "  OR to_employee_id IN (SELECT id FROM employees WHERE dept_id=?))",
            (year, month, dept_id, dept_id),
        ).fetchall()
        return [Redistribution(r["sector"], r["from_employee_id"], r["to_employee_id"],
                               r["day_from"], r["day_to"], r["value"]) for r in rows]


def save_redistributions(dept_id, year, month, items):
    with _db.get_conn() as conn:
        conn.execute(
            "DELETE FROM pril_redistribution WHERE year=? AND month=? "
            "AND from_employee_id IN (SELECT id FROM employees WHERE dept_id=?)",
            (year, month, dept_id),
        )
        for r in items:
            conn.execute(
                "INSERT INTO pril_redistribution(year,month,sector,from_employee_id,"
                "to_employee_id,day_from,day_to,value) VALUES(?,?,?,?,?,?,?,?)",
                (year, month, r.sector, r.from_employee_id, r.to_employee_id,
                 r.day_from, r.day_to, r.value),
            )
        conn.commit()


# --------------------------------------------------------------- настройки
def get_setting(key, default=None):
    with _db.get_conn() as conn:
        r = conn.execute("SELECT value FROM settings_kv WHERE key=?", (key,)).fetchone()
        if not r:
            return default
        try:
            return json.loads(r["value"])
        except (ValueError, TypeError):
            return r["value"]


def get_calendar():
    """Производственный календарь из БД в формате {'2026': {holidays, short_days}}."""
    with _db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM calendar_years").fetchall()
    out = {}
    for r in rows:
        out[str(r["year"])] = {
            "holidays": json.loads(r["holidays"] or "[]"),
            "short_days": json.loads(r["short_days"] or "[]"),
            "work_days": json.loads(r["work_days"] or "[]"),
        }
    return out


def template_path():
    return _core.template_path(FEATURE, _PKG_DIR, "pril_template.xls")
