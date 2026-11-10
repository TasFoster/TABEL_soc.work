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
