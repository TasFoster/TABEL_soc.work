"""Проверки эквивалентности результатов и объёма операций после оптимизаций."""
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.core import db, documents
from app.features.timesheet import storage


class DatabaseOptimizations(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for p in (patch.object(db, 'db_path', return_value=temp.name+'/test.db'),
                  patch.object(db, 'ensure_seeded')):
            p.start(); self.addCleanup(p.stop)
        db.init_db()
        self.conn = db.get_conn()
        self.addCleanup(self.conn.close)
        with self.conn:
            self.conn.executemany('INSERT INTO departments(id,name,sort_order) VALUES(?,?,?)',
                                  [(1, 'Первое', 2), (2, 'Второе', 1), (3, 'Пустое', 3)])
            self.conn.executemany('INSERT INTO employees(id,dept_id,n,fio,sort_order,oklad) VALUES(?,?,?,?,?,?)',
                                  [(1, 1, 5, 'Один', 2, 262.2), (2, 1, 3, 'Два', 1, 100), (3, 2, None, 'Три', 1, None)])

    def test_department_read_is_two_queries_and_keeps_order_ids_and_empty(self):
        queries=[];self.conn.set_trace_callback(queries.append)
        deps=db._departments_to_dict(self.conn)['departments']
        self.assertEqual([d['_db_id'] for d in deps], [2, 1, 3])
        self.assertEqual([e['_db_id'] for e in deps[1]['employees']], [2, 1])
        self.assertEqual(deps[0]['employees'][0]['n'], 1)
        self.assertEqual(deps[1]['employees'][1]['oklad'], 262.2)
        self.assertEqual(deps[2]['employees'], [])
        self.assertEqual(len([q for q in queries if q.startswith('SELECT')]), 2)

    def test_latest_params_matches_archive_order_and_index_is_repeatable(self):
        with self.conn:
            self.conn.executemany('INSERT INTO documents(feature,created_at,params,content) VALUES(?,?,?,?)',
                [('timesheet', '2026-11-01', '{"month":10}', b'old'),
                 ('timesheet', '2026-11-01', '{"month":11}', b'new'),
                 ('proezd', '2026-12-01', '{"month":12}', b'other')])
        self.assertEqual(documents.last_params('timesheet'), {'month':11})
        self.assertEqual(documents.last_params('missing'), {})
        db.init_db(self.conn); db.init_db(self.conn)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0], 3)
        plan=str([tuple(r) for r in self.conn.execute('EXPLAIN QUERY PLAN SELECT params FROM documents WHERE feature=? ORDER BY created_at DESC,id DESC LIMIT 1', ('timesheet',))])
        self.assertIn('idx_documents_feature_latest', plan)
        self.assertNotIn('TEMP B-TREE', plan)

    def test_batch_reads_chunk_at_sqlite_parameter_limit_and_isolate_keys(self):
        dept={'employees':[{'_db_id':i, 'n':i+100} for i in range(1,1002)]}
        with self.conn:
            self.conn.executemany('INSERT INTO settings_kv(key,value) VALUES(?,?)',
                [(storage.indicators_key(i,2026,11),'{"rate":0.5}') for i in range(1,1002)])
        queries=[]
        connect=db.get_conn
        def traced():
            conn=connect();conn.set_trace_callback(queries.append);return conn
        with patch.object(db,'get_conn',side_effect=traced):
            values=storage.load_department_indicators(dept,2026,11)
        self.assertEqual(len(values),1001)
        self.assertEqual(values[1101],{'rate':0.5})
        self.assertEqual(len([q for q in queries if q.startswith('SELECT')]),2)
        self.assertEqual(storage.load_department_indicators(dept,2026,12),{})


class OdsRepeatedRows(unittest.TestCase):
    def test_large_repetition_remains_compressed_and_edits_are_independent(self):
        from odf.table import Table, TableRow, TableCell
        from odf.text import P
        from app.features.reestr import ods_build as ob
        table=Table(name='Test');row=TableRow(numberrowsrepeated=1000000)
        cell=TableCell(valuetype='string');cell.addElement(P(text='original'))
        row.addElement(cell);table.addElement(row)
        middle=ob.row_at(table,500000)
        self.assertEqual(len(table.childNodes),3)
        self.assertEqual([rep for _,_,rep in ob.logical_rows(table)],[500000,1,499999])
        ob.put_row(middle,{0:'changed'})
        for index in (0,1,499999,500001,999999):
            got=ob.row_at(table,index)
            self.assertEqual(ob.cell_text(ob.logical_cells(got,0)[0]),'original')
        self.assertIs(ob.row_at(table,500000),middle)
        self.assertEqual(sum(rep for _,_,rep in ob.logical_rows(table)),1000000)
        self.assertIsNone(ob.row_at(table,1000000))
        self.assertLessEqual(len(table.childNodes),13)

    def test_small_repetitions_and_nested_rows_preserve_neighbors(self):
        from odf.table import Table, TableRow, TableCell, TableRowGroup
        from odf.text import P
        from app.features.reestr import ods_build as ob
        for repeat in (2,3,10):
            for wanted in range(repeat):
                table=Table(name='Test');group=TableRowGroup();table.addElement(group)
                row=TableRow(numberrowsrepeated=repeat);cell=TableCell();cell.addElement(P(text='x'))
                row.addElement(cell);group.addElement(row)
                target=ob.row_at(table,wanted)
                self.assertIs(target.parentNode,group)
                self.assertEqual(ob._row_rep(target),1)
                self.assertEqual(sum(r for _,_,r in ob.logical_rows(table)),repeat)
                self.assertEqual(ob.cell_text(ob.logical_cells(target,0)[0]),'x')
