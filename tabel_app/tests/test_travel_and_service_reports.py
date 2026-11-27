"""Регрессии импорта поездок и накопительного отчёта по услугам."""
import datetime
import pathlib
import sys
import tempfile
import unittest
from collections import Counter
from unittest.mock import patch
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import openpyxl
import xlwt
from odf.opendocument import OpenDocumentSpreadsheet
from odf.table import Table, TableCell, TableRow
from odf.text import P

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.features.proezd import service as travel
from app.features.proezd import storage as travel_storage
from app.features.timesheet.calendar_ru import ProductionCalendar

from app.features.proezd.ods_writer import APPL_SHEET, REPORT_SHEET
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

    def test_travel_export_replaces_full_size_tail_and_removes_backgrounds(self):
        rows = [{'date': '02.11.2026', 'frm': 'Пункт А', 'to': 'Пункт Б',
                 'purpose': '=работа с документами', 'number': '001234',
                 'series': 'ВА-996', 'price': 43}] * 46
        header = {'worker_full': 'Петрова Мария Ивановна'}
        ods = self.folder / 'travel.ods'
        xlsx = self.folder / 'travel.xlsx'
        with patch.object(travel, 'update_lexicon'):
            for target in (ods, xlsx):
                travel.generate(rows, header, 2026, 11, target)

        ns = {
            'table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
            'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
            'style': 'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
            'fo': 'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
        }
        with ZipFile(ods) as archive:
            self.assertIsNone(archive.testzip())
            content = ET.fromstring(archive.read('content.xml'))
            styles = ET.fromstring(archive.read('styles.xml'))
        for root in (content, styles):
            for props in root.findall('.//style:table-cell-properties', ns):
                self.assertNotIn(f'{{{ns["fo"]}}}background-color', props.attrib)
        tables = content.findall('.//table:table', ns)
        self.assertEqual([t.get(f'{{{ns["table"]}}}name') for t in tables],
                         [REPORT_SHEET, APPL_SHEET])
        for table, row_count, last_col in zip(tables, (58, 15), ('F', 'B')):
            self.assertEqual(sum(int(r.get(f'{{{ns["table"]}}}number-rows-repeated', 1))
                                 for r in table.findall('.//table:table-row', ns)), row_count)
            self.assertTrue(table.get(f'{{{ns["table"]}}}print-ranges').endswith(f'.{last_col}{row_count}'))
            for cell in table.findall('.//table:table-cell', ns):
                if cell.get(f'{{{ns["office"]}}}value-type') == 'string':
                    self.assertNotIn(f'{{{ns["office"]}}}date-value', cell.attrib)
        trips, _ = travel.parser.read_trips(ods)
        self.assertEqual([r['date'] for r in trips], [r['date'] for r in rows])
        self.assertIn('1978,00', ''.join(tables[1].itertext()))

        workbook = openpyxl.load_workbook(xlsx)
        self.addCleanup(workbook.close)
        self.assertEqual(workbook.sheetnames, [REPORT_SHEET, APPL_SHEET])
        report, application = workbook.worksheets
        self.assertEqual(report['F53'].value, '001234 ВА-996')
        self.assertEqual(report['E53'].value, '=работа с документами')
        self.assertEqual(report['E53'].data_type, 's')
        self.assertEqual(report['B53'].value, '02.11.2026')
        self.assertIn('1978,00', application['A9'].value)
        for sheet, bounds, merge, orientation in (
            (report, '$A$1:$F$58', 'A1:F1', 'landscape'),
            (application, '$A$1:$B$15', 'A1:B1', 'portrait'),
        ):
            self.assertTrue(sheet.print_area.endswith(bounds))
            self.assertIn(merge, sheet.merged_cells)
            self.assertEqual(sheet.page_setup.orientation, orientation)
            self.assertEqual(sheet.page_setup.fitToWidth, 1)
            self.assertTrue(all(cell.fill.patternType is None for row in sheet for cell in row))

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
