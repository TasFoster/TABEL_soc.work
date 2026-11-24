"""Регрессии импорта поездок и накопительного отчёта по услугам."""
import datetime
import pathlib
import sys
import tempfile
import unittest

import openpyxl
import xlwt
from odf.opendocument import OpenDocumentSpreadsheet
from odf.table import Table, TableCell, TableRow
from odf.text import P

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.features.proezd import service as travel
from app.features.uslugi_dengi import parser, service


class TravelAndServiceReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = pathlib.Path(temp.name)

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
