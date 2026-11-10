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
        self.assertEqual(s.cell_value(4, 38), '0504421')
        self.assertEqual(s.cell_value(5, 13), 'за период с 1 по 30 ноября 2026 г.')
        self.assertEqual(s.cell_value(14, 3), '0000-001')
        self.assertEqual([s.cell_value(r, 21) for r in (14, 15)], [9, 71])
        self.assertEqual([s.cell_value(r, 40) for r in (14, 15)], [20, 159])
        self.assertEqual([s.cell_value(r, 40) for r in (18, 19)], [18, 143])
        self.assertEqual(s.cell_value(14, 8), 7)  # 3 ноября
        self.assertEqual(s.cell_value(15, 8), 'Я')
        self.assertEqual(s.cell_value(14, 9), '')
        self.assertEqual(s.cell_value(15, 9), 'В')
        self.assertEqual(s.cell_value(19, 26), 'ОТ')
        self.assertEqual(s.cell_value(19, 33), 'Б')
        self.assertEqual(s.cell_value(12, 39), '')  # 31 ноября не существует
        self.assertEqual(s.cell_value(21, 11), 'Кадровик Т. Т.')
        self.assertEqual(s.cell_value(24, 11), 'Исполнитель Т. Т.')
        self.assertEqual(s.cell_value(23, 37), 'Бухгалтер Т. Т.')
        for i in range(3):
            self.assertIn((14+2*i, 16+2*i, 1, 3), s.merged_cells)
            self.assertIn((14+2*i, 15+2*i, 40, 45), s.merged_cells)
        self.assertEqual(s.nrows, 27)

    def test_half_months_sum_to_whole(self):
        full, _ = self.generate(count=1)
        first, _ = self.generate(period=(1, 15), count=1)
        second, _ = self.generate(period=(16, 30), count=1)
        a, b, c = [x.sheet_by_index(0) for x in (full, first, second)]
        for r in (14, 15):
            self.assertEqual(a.cell_value(r, 40), b.cell_value(r, 40) + c.cell_value(r, 40))
        self.assertEqual(b.cell_value(15, 24), '')
        self.assertEqual(c.cell_value(15, 6), '')
        self.assertEqual(c.cell_value(14, 21), 0)
        self.assertIn('за период', c.cell_value(12, 40))

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
        self.assertEqual(s.cell_value(17, 11), '')

    def test_shading_uses_selected_calendar_not_november_template(self):
        book, _ = self.generate(2027, 2, count=1)
        s = book.sheet_by_index(0)
        # 1 февраля — понедельник, 6 февраля — суббота.
        for r in (12, 13, 14, 15):
            for day, expected in ((1, 0), (6, 1), (29, 0)):
                xf = book.xf_list[s.cell_xf_index(r, excel_writer.day_column(day))]
                self.assertEqual(xf.background.fill_pattern, expected)

    def test_new_indicator_columns_and_all_absence_codes(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = pathlib.Path(tmp.name) / 'indicators.xls'
        excel_writer.generate(storage.template_path(), str(out), {'employees': [{
            'n': 1, 'fio': 'Тестовый', 'oklad': 262.2, 'marks': {},
            'worked_days': 0, 'worked_hours': 0,
            'indicators': {'rate': 0.5, 'holiday_days': 1, 'holiday_hours': 4,
                           'night_days': 2, 'night_hours': 6.5},
            'reasons': [{'code': 'Б', 'days': 2}, {'code': 'ОТ', 'days': 3},
                        {'code': 'ОЖ', 'days': 4}]}]})
        b = xlrd.open_workbook(str(out))
        self.addCleanup(b.release_resources)
        s = b.sheet_by_index(0)
        self.assertEqual(s.ncols, 49)
        self.assertEqual(s.cell_value(12, 4), 'Оклад/ставка')
        self.assertEqual([s.cell_value(r, 4) for r in (14, 15)], [262.2, 0.5])
        self.assertEqual([s.cell_value(r, 45) for r in (14, 15)], [1, 4])
        self.assertEqual([s.cell_value(r, 46) for r in (14, 15)], [2, 6.5])
        self.assertEqual([s.cell_value(r, 47) for r in (14, 15)], ['Б', '2'])
        self.assertEqual([s.cell_value(r, 48) for r in (14, 15)], ['ОТ\nОЖ', '3\n4'])

    def test_indicator_validation(self):
        from app.features.timesheet.indicators import parse_indicators
        self.assertEqual(parse_indicators({'rate': '0,5', 'night_hours': '2.5'}, 15),
                         {'rate': 0.5, 'night_hours': 2.5})
        self.assertEqual(parse_indicators({}, 15), {})
        for values in ({'rate': 'nan'}, {'night_hours': '-1'}, {'holiday_days': '1.5'},
                       {'holiday_days': '16'}, {'night_hours': '361'}):
            with self.assertRaises(ValueError):
                parse_indicators(values, 15)
