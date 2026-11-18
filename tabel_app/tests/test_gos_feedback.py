"""Состав получателей и читаемость шапки по обратной связи."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from odf.opendocument import load
from odf.table import Table,TableRow,TableCell
from odf.text import P
from odf.teletype import extractText
from odf.style import Style,TableRowProperties
from app.features.gos_zadanie import writer
from app.features.gos_zadanie.model import Client
from app.features.timesheet.timesheet import display_code,build_marks
from app.features.timesheet.calendar_ru import ProductionCalendar

class GosFeedbackTest(unittest.TestCase):
    def test_each_category_filters_and_renumbers_clients(self):
        main='Государственная услуга с очень длинным полным наименованием для проверки высоты шапки'
        dop='Дополнительная услуга'
        clients=[Client('Только основные',total=3,counts={main:3}),
                 Client('Только дополнительные',total=4,counts={dop:4}),
                 Client('Обе категории',total=7,counts={main:2,dop:5}),
                 Client('Без услуг',total=0,counts={}),
                 Client('Только пропускаемые',total=1,counts={'Пропуск':1})]
        with tempfile.TemporaryDirectory() as directory:
            out=str(Path(directory)/'report.ods')
            writer.generate(out,{},clients,[main],[dop])
            doc=load(out)
            sheets=doc.spreadsheet.getElementsByType(Table)
            for sheet,expected,total in ((sheets[0],['Только основные','Обе категории'],10),
                                         (sheets[1],['Только дополнительные','Обе категории'],9)):
                rows=sheet.getElementsByType(TableRow)
                data=rows[3:5]
                self.assertEqual([extractText(r.getElementsByType(TableCell)[1]) for r in data],expected)
                self.assertEqual([extractText(r.getElementsByType(TableCell)[0]) for r in data],['1','2'])
                # Сохраняем действующую трактовку основного итога из источника.
                self.assertEqual(float(rows[5].getElementsByType(TableCell)[3].getAttribute('value')),total)
                text=' '.join(extractText(p) for p in sheet.getElementsByType(P))
                self.assertNotIn('Без услуг',text)
                self.assertNotIn('Только пропускаемые',text)
            heights={s.getAttribute('name'):s.getElementsByType(TableRowProperties)[0].getAttribute('minrowheight')
                     for s in doc.automaticstyles.getElementsByType(Style)
                     if s.getAttribute('name').startswith('HeaderHeight_')}
            self.assertGreater(float(heights['HeaderHeight_Лист1'][:-2]),2)
            self.assertIn(main,' '.join(extractText(p) for p in sheets[0].getElementsByType(P)))

    def test_historical_and_new_parental_leave_codes(self):
        for code in ('ОЖ','Р'):
            result=build_marks(2026,11,ProductionCalendar({}),[{'start':1,'end':3,'code':code}])
            self.assertEqual([display_code(result['marks'][d]) for d in (1,2,3)],['Р']*3)
            self.assertEqual(display_code(result['reasons'][0]['code']),'Р')
        self.assertEqual(display_code('Б'),'Б')
        self.assertEqual(display_code('ОТ'),'О')
