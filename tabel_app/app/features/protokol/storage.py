"""Состав отделений, план методического часа и черновики протоколов."""

import json
import re
from pathlib import Path

from ...core import storage
from ..timesheet import storage as timesheet
from ..timesheet.calendar_ru import ProductionCalendar

FEATURE = "protokol"
PACKAGE = str(Path(__file__).parent)


def department_number(department):
    return department.get("number") or re.search(r"№\s*(\d+)", department["name"])[1]


def list_departments():
    departments = []
    for dept in timesheet.load_departments()["departments"]:
        match = re.search(r"№\s*(\d+)", dept["name"])
        if match:
            departments.append(dict(dept, number=match[1]))
    known = {department_number(dept) for dept in departments}
    for number in ("5", "9"):
        if number not in known:
            departments.append({"name": f"ОСОД № {number}", "number": number, "employees": []})
    return departments


def load_calendar():
    return ProductionCalendar(timesheet.load_calendar())


def load_methodical_plans():
    path = Path(storage.feature_resource_dir(FEATURE, PACKAGE)) / "data/methodical_plans.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_legacy_plan():
    return storage.load_json(FEATURE, PACKAGE, "plan.json")


def _draft_filename(department, year, month):
    number = department_number(department)
    identity = department.get("_db_id")
    key = f"db_{identity}" if identity is not None else f"osod_{number}"
    return f"draft_{key}_{year:04d}_{month:02d}.json"


def load_draft(department, year, month):
    filename = _draft_filename(department, year, month)
    path = Path(storage.feature_data_dir(FEATURE)) / filename
    # Если отделение появилось в справочнике после сохранения черновика,
    # его прежний черновик остаётся доступен.
    if not path.exists() and department.get("_db_id") is not None:
        fallback = {"number": department_number(department)}
        path = path.with_name(_draft_filename(fallback, year, month))
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def save_draft(department, year, month, draft):
    storage.save_json(FEATURE, _draft_filename(department, year, month), draft)
