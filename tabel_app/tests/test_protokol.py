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
        self.assertIn("заслуш", first["planned_report"].lower())
        self.assertNotEqual(first["planned_report"], second["planned_report"])

    def test_draft_and_export_preserve_edited_rows(self):
        dept = {"number": "5", "_db_id": 15, "employees": []}
        calendar = ProductionCalendar({})
        draft = service.new_draft(dept, 2026, 11, calendar)
        draft.update(speaker="Примерова Анна Сергеевна", other="Согласовали график\nУточнили сроки",
                     people=[{"name": "Примерова Анна Сергеевна", "present": True, "reason": ""},
                             {"name": "Тестовый Иван Иванович", "present": False, "reason": "Отпуск"}])
        draft["planned_report"] = "Отчёт социального работника Тестовой А. Б."
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


    def test_current_plan_and_history(self):
        dept = {"number": "5", "employees": []}
        plan = {"sections": [{"rows": [["1", "Заслушивание отчёта Тестовой А. Б."],
                                       ["2", "Заслушивание отчёта Примерова В. Г."],
                                       ["3", "Другой пункт"]]}]}
        with patch.object(service.plans, "build_plan", return_value=plan) as build:
            draft = service.new_draft(dept, 2026, 11, ProductionCalendar({}))
            build.assert_called_once_with("5", 11, 2026)
            self.assertEqual(len(draft["planned_report"].splitlines()), 2)
        with tempfile.TemporaryDirectory() as directory, patch("app.core.storage.app_base_dir", return_value=directory):
            storage.save_history(dept, 2026, 11, draft)
            draft["agenda"] = "Изменение"
            storage.save_history(dept, 2026, 11, draft)
            entries = storage.load_history(dept)
            self.assertEqual(len(entries), 2)
            self.assertEqual(sum(e["draft"]["agenda"] == "Изменение" for e in entries), 1)
            self.assertEqual(storage.load_history({"number": "9"}), [])

    def test_preview_matches_export_and_comparison(self):
        draft = {"number": "1", "date": "25.11.2026", "head": "Тестовая А. Б.",
                 "speaker": "", "agenda": "Пункт", "planned_report": "Отчёт",
                 "decisions": "Решение", "other": "Обсуждение",
                 "people": [{"name": "Примеров А. Б.", "present": True, "reason": ""}]}
        dept = {"number": "5"}
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "preview.odt"
            service.generate(str(out), dept, 2026, 11, draft)
            self.assertEqual([text for text, style in service.preview(dept, 2026, 11, draft)],
                             [extractText(p) for p in load(str(out)).getElementsByType(P)])
        self.assertEqual(service.compare_drafts(draft, draft), [])
        changed = dict(draft, other="Новый текст", people=[])
        diff = service.compare_drafts(draft, changed)
        self.assertIn("-Обсуждение", diff)
        self.assertIn("+Новый текст", diff)
        self.assertTrue(any(line.startswith("-Примеров") for line in diff))
