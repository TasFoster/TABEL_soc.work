"""Синтетические замеры, медиана трёх запусков. Рабочая БД не используется."""
import sys,time,statistics,tempfile,json,sqlite3
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.features.timesheet import excel_writer as w,storage as ts
from app.core import db,documents
from app.features.reestr import ods_build as ob
from odf.table import Table,TableRow,TableCell
from odf.text import P

def measure(f, n=3):
 vals=[]
 for _ in range(n):
  start=time.perf_counter();f();vals.append(time.perf_counter()-start)
 return round(statistics.median(vals)*1000,2)
with tempfile.TemporaryDirectory() as tmp:
 ctx={'ndays':31,'nonworking_days':[1,7,8,14,15,21,22,28,29],'employees':[{'n':i,'fio':'Тестовый '+str(i),'marks':{d:8 for d in range(1,32)},'worked_days':31,'worked_hours':248} for i in range(100)]}
 result={'xls_100_employees_ms':measure(lambda:w.generate(ts.template_path(),tmp+'/test.xls',ctx))}
 with patch.object(db,'db_path',return_value=tmp+'/test.db'),patch.object(db,'ensure_seeded'):
  db.init_db();conn=db.get_conn()
  with conn:
   conn.executemany('INSERT INTO departments(id,name,sort_order) VALUES(?,?,?)',[(i,'Отделение '+str(i),i) for i in range(1,101)])
   conn.executemany('INSERT INTO employees(dept_id,n,fio) VALUES(?,?,?)',[(i,j,'Тестовый') for i in range(1,101) for j in range(1,21)])
   conn.executemany('INSERT INTO documents(feature,created_at,params) VALUES(?,?,?)',[('timesheet' if i%2 else 'proezd','2026-11-01','{"month":11}') for i in range(20000)])
  result['departments_100_ms']=measure(lambda:db._departments_to_dict(conn))
  result['last_params_20000_ms']=measure(lambda:documents.last_params('timesheet'))
  queries=[];conn.set_trace_callback(queries.append);db._departments_to_dict(conn);result['department_selects']=len([q for q in queries if q.startswith('SELECT')]);conn.close()
 def ods():
  t=Table(name='Test');r=TableRow(numberrowsrepeated=2000);c=TableCell();c.addElement(P(text='test'));r.addElement(c);t.addElement(r)
  ob.row_at(t,1000)
  return len(t.childNodes)
 result['ods_2000_repeated_ms']=measure(ods);result['ods_nodes_after_edit']=ods()
 print(json.dumps(result))
