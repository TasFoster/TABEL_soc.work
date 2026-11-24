"""Версии чек-листов функций в общей базе приложения."""

from contextlib import closing
from dataclasses import dataclass
import json

from . import db


@dataclass(frozen=True)
class Checklist:
    version: int = 0
    items: tuple[str, ...] = ()

    def message(self, feature_title):
        lines = [f"Раздел: {feature_title}", f"Версия чек-листа: {self.version}", ""]
        lines.extend(f"{number}. {item}" for number, item in enumerate(self.items, start=1))
        if not self.items:
            lines.append("Чек-лист пуст.")
        return "\n".join(lines)


class ChecklistConflict(ValueError):
    """Сохранённая версия изменилась с момента открытия редактора."""


def _read(conn, feature_key):
    row = conn.execute("SELECT version, items FROM feature_checklists WHERE feature_key = ?",
                       (feature_key,)).fetchone()
    if row is None:
        return Checklist()
    return Checklist(row["version"], tuple(json.loads(row["items"])))


def load(feature_key):
    db.ensure_seeded()
    with closing(db.get_conn()) as conn:
        return _read(conn, feature_key)


def save(feature_key, items, expected_version):
    db.ensure_seeded()
    items = tuple(items)
    with closing(db.get_conn()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        current = _read(conn, feature_key)
        if items == current.items:
            return current
        if current.version != expected_version:
            raise ChecklistConflict("Чек-лист изменился в другом окне. Откройте его заново перед сохранением.")
        result = Checklist(current.version + 1, items)
        conn.execute(
            "INSERT INTO feature_checklists(feature_key, version, items) VALUES (?, ?, ?) "
            "ON CONFLICT(feature_key) DO UPDATE SET version=excluded.version, items=excluded.items",
            (feature_key, result.version, json.dumps(items, ensure_ascii=False)),
        )
    return result
