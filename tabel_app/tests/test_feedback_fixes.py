"""Регрессии по обращениям: данные, номера договоров и печатные настройки."""
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import openpyxl
import xlrd
from app.core import db
from app.features.timesheet import storage as ts, excel_writer as tw
from app.features.prilozhenie import model as pm, calc, service as ps, excel_writer as pw
from app.features.reestr_oplata import model as rm, service as rs, ods_editor as ed
from app.features.plany import service as plans, storage as plan_store
from app.features.uslugi_dengi.writer import _fill_ud
from odf.table import TableRow, TableCell
from odf.text import P

class FeedbackFixes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = pathlib.Path(self.tmp.name)
        for patcher in (patch.object(db, 'db_path', return_value=str(self.path/'test.db')),
                        patch.object(db, 'ensure_seeded')):
            patcher.start(); self.addCleanup(patcher.stop)
        db.init_db()
        with db.get_conn() as c:
            c.execute("INSERT INTO departments(id,name,responsible_fio) VALUES(1,'ОСОД №2','Тестовая')")
            c.execute("INSERT INTO employees(id,dept_id,n,fio,position) VALUES(1,1,1,'Тестовый','социальный работник')")

    def test_absences_survive_renumbering_and_month_switch(self):
        d=ts.load_departments()['departments'][0]
        value=[{'start':2,'end':5,'code':'ОТ'}]
        ts.save_absences(d,2026,10,{1:value})
        d['employees'][0]['n']=7
        self.assertEqual(ts.load_absences(d,2026,10),{7:value})
        self.assertEqual(ts.load_absences(d,2026,11),{})
        ts.save_absences(d,2026,10,{})
        self.assertEqual(ts.load_absences(d,2026,10),{7:[]})

    def test_contract_only_change_is_separate_operation(self):
        row=TableRow()
        for _ in range(10):
            cell=TableCell(valuetype='string');cell.addElement(P(text=''));row.addElement(cell)
        client=rm.GosClient(row,False,1,'Тестовый','тестовый','Договор №OLD','OLD',100,100,'',None)
        block=rm.GosBlock('Работник',None,None,None,[client],[])
        model=rm.RegistryModel(None,None,None,None,gos_blocks=[block])
        journal={'by_fio':{'тестовый':{'fio':'Тестовый','gos':{'NEW':100},'dop':{}}},'period':('01.10.2026','31.10.2026')}
        plan=rs.compute_plan(model,journal)
        self.assertEqual(len(plan.changes),1)
        self.assertEqual(plan.changes[0].category,rs.CAT_CONTRACT)
        with patch.object(ed,'rebuild_formulas'):
            rs.apply_plan(model,plan,journal)
        self.assertEqual(client.contract,'NEW')
        self.assertIn('NEW',ed.ob.cell_text(ed.ob.logical_cells(row,3)[3]))

    def test_timesheet_print_titles(self):
        out=self.path/'t.xls'
        tw.generate(ts.template_path(),str(out),{'employees':[{'n':1,'fio':'Тестовый','marks':{},'worked_days':0,'worked_hours':0}]})
        book=xlrd.open_workbook(str(out))
        title=next(n for n in book.name_obj_list if n.name=='Print_Titles')
        self.assertEqual(title.scope,0)
        self.assertIn('$20',title.result.text)

    def test_appendix_hidden_columns_and_second_signature(self):
        worker=pm.Worker(1,1,'Тестовый Сотрудник',30000,5,3)
        result=calc.compute([worker],[1,2,5],31,[],[],[])
        ctx=ps.build_context({'responsible_fio':'Тестовая'},2026,10,[worker],result)
        out=self.path/'p.xls';pw.generate(str(out),ctx)
        sh=xlrd.open_workbook(str(out),formatting_info=True).sheet_by_index(0)
        for label in ('Оклад','Норма чел/дней','Начислено, руб.'):
            col=next(c for c in range(sh.ncols) if sh.cell_value(3,c)==label)
            self.assertTrue(sh.colinfo_map[col].hidden)
        self.assertTrue(any(sh.cell_value(r,c)==ctx['zav_line'] for r in range(6,sh.nrows) for c in range(36,sh.ncols)))

    def test_plan_department_and_saved_content(self):
        self.assertIn('2',plan_store.departments())
        plan=plans.build_plan('2',1,2026)
        self.assertIn('Тестовая',str(plan['footer']))
        plan['footer']=['Другая подпись']
        plan_store.plan_save('2',2026,1,plan)
        self.assertEqual(plans.build_plan('2',1,2026)['footer'],['Другая подпись'])
        self.assertEqual(plans.effective_worker('2',2026,1),'Тестовый')

    def test_zero_services_clear_stale_cells(self):
        sheet=openpyxl.Workbook().active
        for c in (8,9,10):sheet.cell(7,c).value=999
        _fill_ud(sheet,{},None)
        self.assertEqual([sheet.cell(7,c).value for c in (8,9,10)],[None,None,None])

    def test_print_cleanup_preserves_formula_namespaces(self):
        from app.core.printing import remove_headers_footers
        from odf.opendocument import OpenDocumentSpreadsheet,load
        from odf.table import Table
        from odf.style import MasterPage,PageLayout,Header
        doc=OpenDocumentSpreadsheet();layout=PageLayout(name='layout');doc.automaticstyles.addElement(layout)
        master=MasterPage(name='Standard',pagelayoutname=layout)
        header=Header();header.addElement(P(text='remove'));master.addElement(header);doc.masterstyles.addElement(master)
        doc.spreadsheet.addElement(Table(name='test'))
        out=self.path/'print.ods';doc.save(str(out));remove_headers_footers(str(out))
        self.assertEqual(len(load(str(out)).masterstyles.getElementsByType(Header)),0)
