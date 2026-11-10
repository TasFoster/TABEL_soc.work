"""Регрессии протоколов по обращениям пользователей."""

from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from odf.opendocument import load
from odf.teletype import extractText
from odf.text import P

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.features.protokol import service, storage
from app.features.timesheet.calendar_ru import ProductionCalendar


class ProtocolTest(unittest.TestCase):
    def test_last_working_wednesday_checks_production_calendar(self):
        calendar = ProductionCalendar({"2026": {"holidays": ["11-25"]}})
        self.assertEqual(service.last_working_wednesday(2026, 11, calendar), date(2026, 11, 18))
        calendar.data["2026"]["work_days"] = ["11-25"]
        self.assertEqual(service.last_working_wednesday(2026, 11, calendar), date(2026, 11, 25))
        calendar.data["2026"] = {"holidays": ["11-04", "11-11", "11-18", "11-25"]}
        self.assertIsNone(service.last_working_wednesday(2026, 11, calendar))

    def test_plans_differ_by_department_and_month(self):
        plans = storage.load_methodical_plans()
        for department in ("5", "9"):
            self.assertEqual(set(plans[department]), {str(n) for n in range(1, 13)})
        first = service.new_draft({"number": "5", "employees": []}, 2026, 8, ProductionCalendar({}))
        second = service.new_draft({"number": "9", "employees": []}, 2026, 8, ProductionCalendar({}))
        self.assertTrue(first["planned_report"].startswith("Отчёт социального работника "))
        self.assertNotEqual(first["planned_report"], second["planned_report"])

    def test_draft_and_export_preserve_edited_rows(self):
        dept = {"number": "5", "_db_id": 15, "employees": []}
        calendar = ProductionCalendar({})
        draft = service.new_draft(dept, 2026, 11, calendar)
        draft.update(speaker="Примерова Анна Сергеевна", other="Согласовали график\nУточнили сроки",
                     people=[{"name": "Примерова Анна Сергеевна", "present": True, "reason": ""},
                             {"name": "Тестовый Иван Иванович", "present": False, "reason": "Отпуск"}])
        original_speaker = draft["planned_report"]
        with tempfile.TemporaryDirectory() as directory, patch(
            "app.core.storage.app_base_dir", return_value=directory
        ):
            storage.save_draft(dept, 2026, 11, draft)
            reloaded = storage.load_draft(dept, 2026, 11)
            self.assertEqual(reloaded, draft)
            self.assertIsNone(storage.load_draft(dept, 2026, 12))
            self.assertIsNone(storage.load_draft(dict(dept, _db_id=16), 2026, 11))
            out = Path(directory) / "test.odt"
            service.generate(str(out), dept, 2026, 11, reloaded)
            lines = [extractText(p) for p in load(str(out)).getElementsByType(P)]
            for line in ("Протокол № 11", "Отсутствовали:", "Тестовый Иван Иванович — отпуск",
                         "Докладчик: Примерова Анна Сергеевна.", "Разное:",
                         "Согласовали график", "Уточнили сроки"):
                self.assertIn(line, lines)
            self.assertNotIn(original_speaker, lines)
            reloaded["speaker"] = ""
            service.generate(str(out), dept, 2026, 11, reloaded)
            lines = [extractText(p) for p in load(str(out)).getElementsByType(P)]
            self.assertIn(original_speaker, lines)
