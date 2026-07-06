"""Хранилище «Графика проверок»: отделения и соцработники из общей базы."""

from ...core import db as _db


def list_departments():
    _db.ensure_seeded()
    with _db.get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM departments ORDER BY sort_order, id")]


def soc_workers(dept_id):
    """ФИО соцработников отделения (по должности)."""
    _db.ensure_seeded()
    with _db.get_conn() as conn:
        rows = conn.execute(
            "SELECT fio, position FROM employees WHERE dept_id=? ORDER BY sort_order, n, id",
            (dept_id,)).fetchall()
    return [r["fio"] for r in rows if "работник" in (r["position"] or "").lower()]
