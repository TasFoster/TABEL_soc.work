"""Проверки формы 0504421 на обезличенных данных."""
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

import xlrd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.features.timesheet import service, storage, excel_writer
from app.features.timesheet.calendar_ru import ProductionCalendar


class TimesheetFormTests(unittest.TestCase):
    def generate(self, year=2026, month=11, period=None, count=3, absences=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = pathlib.Path(tmp.name) / 'form.xls'
        dept = {'name': 'Тестовое отделение № 1', 'organization': 'Тестовая организация',
                'responsible_fio': 'Исполнитель Т. Т.', 'responsible_position': 'Заведующий',
                'employees': [{'n': i + 1, 'fio': f'Тестовый сотрудник {i + 1}',
                               'tab_number': '0000-001', 'position': 'Социальный работник'}
                              for i in range(count)]}
        settings = {'timesheet_hr_fio': 'Кадровик Т. Т.', 'timesheet_accountant_fio': 'Бухгалтер Т. Т.'}
        cal = ProductionCalendar({'2026': {'holidays': ['11-04'], 'short_days': ['11-03']}})
        with patch.object(service, 'get_calendar', return_value=cal):
            ctx = service.build_context(dept, year, month, absences or {}, settings, period)
        excel_writer.generate(storage.template_path(), str(out), ctx)
        book = xlrd.open_workbook(str(out), formatting_info=True)
        self.addCleanup(book.release_resources)
        return book, ctx

    def test_november_layout_totals_and_signatures(self):
        book, ctx = self.generate(absences={3: [{'start': 18, 'end': 18, 'code': 'ОТ'},
                                                {'start': 25, 'end': 25, 'code': 'Б'}]})
        s = book.sheet_by_index(0)
        self.assertEqual(s.cell_value(4, 39), '0504421')
        self.assertEqual(s.cell_value(5, 14), 'за период с 1 по 30 ноября 2026 г.')
        self.assertEqual(s.cell_value(14, 3), '0000-001')
        self.assertEqual([s.cell_value(r, 22) for r in (14, 15)], [9, 71])
        self.assertEqual([s.cell_value(r, 41) for r in (14, 15)], [20, 159])
        self.assertEqual([s.cell_value(r, 41) for r in (18, 19)], [18, 143])
        self.assertEqual(s.cell_value(14, 9), 7)  # 3 ноября
        self.assertEqual(s.cell_value(15, 9), 'Я')
        self.assertEqual(s.cell_value(14, 10), '')
        self.assertEqual(s.cell_value(15, 10), 'В')
        self.assertEqual(s.cell_value(19, 27), 'ОТ')
        self.assertEqual(s.cell_value(19, 34), 'Б')
        self.assertEqual(s.cell_value(12, 40), '')  # 31 ноября не существует
        self.assertEqual(s.cell_value(21, 12), 'Кадровик Т. Т.')
        self.assertEqual(s.cell_value(24, 12), 'Исполнитель Т. Т.')
        self.assertEqual(s.cell_value(23, 38), 'Бухгалтер Т. Т.')
        for i in range(3):
            self.assertIn((14+2*i, 16+2*i, 1, 3), s.merged_cells)
            self.assertIn((14+2*i, 15+2*i, 41, 46), s.merged_cells)
        self.assertEqual(s.nrows, 27)

    def test_half_months_sum_to_whole(self):
        full, _ = self.generate(count=1)
        first, _ = self.generate(period=(1, 15), count=1)
        second, _ = self.generate(period=(16, 30), count=1)
        a, b, c = [x.sheet_by_index(0) for x in (full, first, second)]
        for r in (14, 15):
            self.assertEqual(a.cell_value(r, 41), b.cell_value(r, 41) + c.cell_value(r, 41))
        self.assertEqual(b.cell_value(15, 25), '')
        self.assertEqual(c.cell_value(15, 7), '')
        self.assertEqual(c.cell_value(14, 22), 0)
        self.assertIn('за период', c.cell_value(12, 41))

    def test_month_lengths_and_employee_counts(self):
        for year, month, ndays, count in ((2027, 2, 28, 1), (2028, 2, 29, 12), (2026, 12, 31, 30)):
            with self.subTest(year=year, month=month):
                book, ctx = self.generate(year, month, count=count)
                s = book.sheet_by_index(0)
                self.assertEqual(s.nrows, 21+2*count)
                for day in range(ndays+1, 32):
                    c = excel_writer.day_column(day)
                    self.assertEqual(s.cell_value(12, c), '')
                    self.assertEqual(s.cell_value(14, c), '')
                    self.assertEqual(s.cell_value(15, c), '')
                self.assertEqual(s.cell_value(14+2*(count-1), 1), f'Тестовый сотрудник {count}')

    def test_empty_department_rejected(self):
        with self.assertRaises(excel_writer.ExcelWriterError):
            self.generate(count=0)

    def test_template_contains_no_employee_or_signature_data(self):
        b = xlrd.open_workbook(storage.template_path())
        self.addCleanup(b.release_resources)
        s = b.sheet_by_index(0)
        self.assertTrue(all(v == '' for r in (14, 15) for v in s.row_values(r)))
        self.assertEqual(s.cell_value(17, 12), '')

    def test_shading_uses_selected_calendar_not_november_template(self):
        book, _ = self.generate(2027, 2, count=1)
        s = book.sheet_by_index(0)
        # 1 февраля — понедельник, 6 февраля — суббота.
        for r in (12, 13, 14, 15):
            for day, expected in ((1, 0), (6, 1), (29, 0)):
                xf = book.xf_list[s.cell_xf_index(r, excel_writer.day_column(day))]
                self.assertEqual(xf.background.fill_pattern, expected)
