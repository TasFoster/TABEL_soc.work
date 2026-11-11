"""Подготовка черновика и экспорт протокола рабочего совещания."""

import calendar
from datetime import date, datetime, timedelta
import re

from . import storage, writer
from ..plany import service as plans
from ..timesheet.calendar_ru import MONTHS_NOM

REASONS = ("", "Отпуск", "Больничный", "Другая причина")


def last_working_wednesday(year, month, production_calendar):
    current = date(year, month, calendar.monthrange(year, month)[1])
    current -= timedelta(days=(current.weekday() - 2) % 7)
    while current.month == month:
        if production_calendar.is_workday(current):
            return current
        current -= timedelta(days=7)
    return None


def _plan_for(department, year, month):
    plans = storage.load_methodical_plans()
    plan = plans.get(storage.department_number(department), {}).get(str(month))
    if plan is None:
        topic = storage.load_legacy_plan().get(str(month), "")
        items = re.split(r"(?:^|\s)\d+\.\s+", topic)
        return [item.strip() for item in items if item.strip() and not item.lower().startswith("разное")], ""
    # Приводим годы периодических мероприятий к выбранному году,
    # сохраняя переход на следующий год в декабрьском плане.
    def shift_year(text):
        return re.sub(r"\b20\d{2}\b", lambda match: str(int(match[0]) + year - 2025), text)
    return [shift_year(item) for item in plan["agenda"]], plan["report"]


def new_draft(department, year, month, production_calendar):
    meeting = last_working_wednesday(year, month, production_calendar)
    agenda, report = _plan_for(department, year, month)
    report = reports_from_plan(department, year, month)
    return {
        "number": str(month),
        "date": meeting.strftime("%d.%m.%Y") if meeting else "",
        "head": department.get("responsible_fio", ""),
        "people": [{"name": employee["fio"], "present": True, "reason": ""}
                   for employee in department["employees"]
                   if "работник" in (employee.get("position") or "").lower()],
        "agenda": "\n".join(agenda),
        "planned_report": report,
        "speaker": "",
        "decisions": "",
        "other": "",
    }


def validate(draft, year, month):
    if not draft["number"].strip():
        raise ValueError("Укажите номер протокола.")
    try:
        meeting = datetime.strptime(draft["date"].strip(), "%d.%m.%Y").date()
    except ValueError as exc:
        raise ValueError("Введите дату совещания в формате ДД.ММ.ГГГГ.") from exc
    if (meeting.year, meeting.month) != (year, month):
        raise ValueError("Дата совещания должна относиться к выбранному месяцу и году.")
    if not any(p["present"] for p in draft["people"]):
        raise ValueError("Добавьте хотя бы одного присутствующего.")


def document_data(department, year, month, draft):
    validate(draft, year, month)
    present = [p["name"] for p in draft["people"] if p["present"]]
    absent = [f'{p["name"]} — {p["reason"].strip().lower()}' if p["reason"].strip() else p["name"]
              for p in draft["people"] if not p["present"]]
    agenda = [line.strip() for line in draft["agenda"].splitlines() if line.strip()]
    speaker = draft["speaker"].strip()
    report = draft["planned_report"].strip()
    if speaker and report.startswith("Отчёт социального работника "):
        report = "Отчёт социального работника."
    if report:
        agenda.extend(report.splitlines())
    agenda.append("Разное.")
    body = ["Повестка дня:", *(f"{i}. {line}" for i, line in enumerate(agenda, 1))]
    if speaker or report or draft["decisions"].strip():
        body.extend(("", "Слушали:"))
        if report:
            body.extend(report.splitlines())
        if speaker:
            body.append(f"Докладчик: {speaker}.")
        body.extend(draft["decisions"].splitlines())
    body.extend(("", "Разное:", *draft["other"].splitlines()))
    context = {"number": draft["number"], "date": draft["date"],
               "dept_no": storage.department_number(department), "zav": draft["head"]}
    return context, present, "\n".join(body), absent


def reports_from_plan(department, year, month):
    """Берём фактические строки заслушивания, включая правки в «Планах»."""
    plan = plans.build_plan(storage.department_number(department), month, year)
    return "\n".join(row[1].strip() for section in plan.get("sections", [])
                     for row in section.get("rows", [])
                     if len(row) > 1 and "заслуш" in row[1].lower())


def generate(path, department, year, month, draft):
    return writer.generate(path, *document_data(department, year, month, draft))


def preview(department, year, month, draft):
    """Те же абзацы и стили, что в экспортируемом ODT, без записи файла."""
    from odf.text import P
    from odf.teletype import extractText
    doc = writer.build_document(*document_data(department, year, month, draft))
    return [(extractText(p), "title" if p.getAttribute("stylename") == "ProtTitle" else "body")
            for p in doc.getElementsByType(P)]


def compare_drafts(before, after):
    """Построчные отличия всех пользовательских полей, включая участников."""
    import difflib
    labels = {"number": "Номер", "date": "Дата", "head": "Заведующая",
              "speaker": "Замена докладчика", "agenda": "Повестка",
              "planned_report": "Заслушивания", "decisions": "Решения", "other": "Разное"}
    def lines(draft):
        result = []
        for key, label in labels.items():
            result.append("[" + label + "]")
            result.extend(str(draft.get(key, "")).splitlines())
        result.append("[Участники]")
        for person in draft.get("people", []):
            result.append(f'{person["name"]} | {"Присутствует" if person["present"] else "Отсутствует"} | {person.get("reason", "")}')
        return result
    return list(difflib.unified_diff(lines(before), lines(after), fromfile="Исходная версия",
                                    tofile="Сравниваемая версия", lineterm=""))
