"""Регрессии импорта поездок и накопительного отчёта по услугам."""
import datetime
import pathlib
import sys
import tempfile
import unittest
from collections import Counter
from unittest.mock import patch

import openpyxl
import xlwt
from odf.opendocument import OpenDocumentSpreadsheet
from odf.table import Table, TableCell, TableRow
from odf.text import P

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.features.proezd import service as travel
from app.features.proezd import storage as travel_storage
from app.features.timesheet.calendar_ru import ProductionCalendar
from app.features.uslugi_dengi import parser, service


class TravelAndServiceReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = pathlib.Path(temp.name)

    def test_travel_remembers_manual_prices_by_full_series(self):
        with patch.object(travel_storage._core, "feature_data_dir", return_value=self.folder):
            travel_storage.save_settings({
                "series_prices": {"ВА": 43}, "default_price": 35, "custom_key": "сохранить",
            })
            settings = travel_storage.load_settings()
            self.assertEqual(travel.remember_series_price(" ба – 996 ", "47,50", settings), 47.5)
            self.assertEqual(travel.remember_series_price(" BA – 997 ", "0", settings), 0)
            with self.assertRaises(ValueError):
                travel.remember_series_price("ВА-997", "NaN", settings)
            loaded = travel_storage.load_settings()
            self.assertEqual(travel.default_price_for("БА-996", loaded), 47.5)
            self.assertEqual(travel.default_price_for("ВА-997", loaded), 0)
            self.assertEqual(travel.default_price_for("ВА-999", loaded), 43)
            self.assertEqual(travel.default_price_for("БА-999", loaded), 35)
            self.assertEqual(loaded["custom_key"], "сохранить")

    def test_travel_source_dates_from_ods_and_excel(self):
        date = datetime.date(2026, 11, 7)
        rows = [
            ['За НОЯБРЬ 2026 года'], [], [], [], [], [],
            [1, date, 'Пункт А', 'Пункт Б', 'Цель'],
            [2, date, 'Пункт Б', 'Пункт А', 'Цель'],
            [3, None, 'Пункт А', 'Пункт Б', 'Цель'],
        ]
        xlsx = openpyxl.Workbook()
        xlsx.create_sheet('Отчёт')
        xls = xlwt.Workbook()
        xls.add_sheet('Лист1')
        sheet = xls.add_sheet('Отчёт')
        style = xlwt.easyxf(num_format_str='DD.MM.YYYY')
        ods = OpenDocumentSpreadsheet()
        ods.spreadsheet.addElement(Table(name='Лист1'))
        table = Table(name='Отчёт')
        ods.spreadsheet.addElement(table)
        for r, values in enumerate(rows):
            xlsx['Отчёт'].append(values)
            row = TableRow()
            table.addElement(row)
            for c, value in enumerate(values):
                if isinstance(value, datetime.date):
                    sheet.write(r, c, value, style)
                    cell = TableCell(valuetype='date', datevalue=value.isoformat())
                else:
                    if value is not None:
                        sheet.write(r, c, value)
                    cell = TableCell()
                    if value is not None:
                        cell.addElement(P(text=str(value)))
                row.addElement(cell)
        for ext, book in [('xlsx', xlsx), ('xls', xls), ('ods', ods)]:
            with self.subTest(format=ext):
                src = self.folder / f'travel.{ext}'
                book.save(str(src))
                prepared = travel.prepare(src)
                self.assertEqual(prepared['header']['year'], '2026')
                actual, note = travel.build_rows(prepared, 2027, 1, {'default_price': 35})
                self.assertEqual([row['date'] for row in actual], ['07.11.2026', '07.11.2026', ''])
                self.assertEqual(actual[1]['frm'], 'Пункт Б')
                self.assertIn('Без даты: 1', note)

    def test_travel_monthly_schedule_pairs_and_cadences(self):
        cal = ProductionCalendar({'2026': {}})
        rows, note = travel.build_monthly_rows(2026, 9, cal=cal, settings={'default_price': 35})
        by_date = {}
        for row in rows:
            date = datetime.datetime.strptime(row['date'], '%d.%m.%Y').date()
            self.assertEqual(date.month, 9)
            self.assertIn(date.weekday(), (0, 1, 3, 4))
            by_date.setdefault(date, Counter())[row['purpose']] += 1

        self.assertEqual(len(by_date), 17)
        self.assertEqual([row['num'] for row in rows], list(range(1, len(rows) + 1)))
        for trips in by_date.values():
            self.assertEqual(trips['Покупка и доставка продуктов'], 2)
            self.assertEqual(trips['Получение подарка от спонсоров'],
                             trips['Доставка подарка от спонсоров'])
            self.assertEqual(trips['Оформление рецептов'] + trips['Заказ медикаментов'],
                             trips['Доставка медикаментов'])
        weekly = ('Оплата коммунальных платежей', 'Оформление рецептов',
                  'Получение подарка от спонсоров')
        weeks = {}
        orders = []
        for day, trips in by_date.items():
            weeks.setdefault(day.isocalendar().week, Counter()).update(trips)
            orders.extend([day.day] * trips['Заказ медикаментов'])
        self.assertEqual(len(weeks), 5)
        for counts in weeks.values():
            self.assertEqual([counts[purpose] for purpose in weekly], [1, 1, 1])
        self.assertEqual(orders, [4, 18])
        self.assertIn('17 дат', note)

    def test_travel_shift_preserves_trips_and_ignores_other_weekdays(self):
        cal = ProductionCalendar({
            '2026': {'holidays': ['09-01', '09-10', '09-11'], 'work_days': ['09-09', '09-12']},
        })
        source = [
            {'purpose': ' Покупка и доставка продуктов. ', 'frm': 'А', 'to': 'Б',
             'number': '0123', 'series': '4МН-575', 'date': '05.08.2026'},
            {'purpose': 'Оплата коммунальных платежей', 'frm': 'Б', 'to': 'В'},
            {'purpose': 'Оплата коммунальных платежей', 'frm': 'Б', 'to': 'Г'},
        ]
        settings = {'default_price': 35}
        rows, note = travel.build_monthly_rows(2026, 9, cal=cal, settings=settings,
                                               source_rows=source)
        unshifted, _ = travel.build_monthly_rows(2026, 9, cal=ProductionCalendar({}),
                                                 settings=settings)
        self.assertEqual(Counter(row['purpose'] for row in rows),
                         Counter(row['purpose'] for row in unshifted))
        self.assertIn('3 визитов', note)
        self.assertIn('предыдущего месяца', note)
        self.assertEqual(rows[0]['date'], '31.08.2026')
        self.assertEqual({row['date'] for row in rows} &
                         {'01.09.2026', '09.09.2026', '10.09.2026', '11.09.2026', '12.09.2026'},
                         set())
        groceries = [row for row in rows if row['purpose'] == 'Покупка и доставка продуктов']
        self.assertEqual(sum(row['date'] == '08.09.2026' for row in groceries), 6)
        self.assertTrue(all((row['frm'], row['to']) == ('А', 'Б') for row in groceries))
        self.assertTrue(all((row['number'], row['series']) == ('', '') for row in rows))
        utilities = [row for row in rows if row['purpose'] == 'Оплата коммунальных платежей']
        self.assertTrue(all((row['frm'], row['to']) == ('', '') for row in utilities))
        self.assertEqual(source[0]['date'], '05.08.2026')

    def test_empty_quantities_block_does_not_read_money_as_quantities(self):
        source = self.folder / 'benefit.xlsx'
        wb = openpyxl.Workbook()
        sheet = wb.active
        sheet.title = 'Частичники'
        header = ['№', 'ФИО', 'Покупка продуктов питания', 'Доставка книг', 'Уборка жилых помещений']
        sheet.append(header)
        sheet.append(['Итого'])
        sheet.append(header)
        sheet.append([1, 'Получатель', 13.25, None, None])
        wb.save(source)

        data = parser.read_benefit(str(source))
        self.assertEqual(data['part_cnt_clients'], [])
        self.assertEqual(data['part_money_agg']['prod'], 13.25)
        data['prev_ud'] = {'prod': {'H': 7, 'I': 51.5, 'J': 3}}
        data['free_agg'] = {'prod': 2}
        data['counts071'] = {'prod': 14}

        for month, expected in [(1, [None, 13.25, 2]), (2, [7, 64.75, 5])]:
            with self.subTest(month=month):
                result = self.folder / f'report-{month}.xlsx'
                service.generate(data, result, month, 2026)
                report = openpyxl.load_workbook(result)
                self.addCleanup(report.close)
                sheet = report['Услуги-Деньги']
                self.assertEqual([sheet[f'{col}7'].value for col in 'HIJ'], expected)
                self.assertEqual(sheet['C7'].value, 14)
                self.assertTrue(all(sheet[f'{col}7'].data_type == 'f' for col in 'DFG'))
